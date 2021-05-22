import base64
import collections
import datetime
import importlib
import inspect
import json
import logging
import os
import sys
import tarfile
import traceback
from builtins import str

import boto3
from werkzeug.wrappers import Response

# This file may be copied into a project's root,
# so handle both scenarios.
try:
    from zappa.middleware import ZappaWSGIMiddleware
    from zappa.utilities import merge_headers, parse_s3_url
    from zappa.wsgi import common_log, create_wsgi_request
except ImportError as e:  # pragma: no cover
    from .middleware import ZappaWSGIMiddleware
    from .utilities import merge_headers, parse_s3_url
    from .wsgi import common_log, create_wsgi_request


# Set up logging
logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.INFO)


class LambdaHandler:
    """
    Singleton for avoiding duplicate setup.

    Pattern provided by @benbangert.
    """

    __instance = None
    settings = None
    settings_name = None
    session = None

    # Application
    app_module = None
    wsgi_app = None
    trailing_slash = False

    def __new__(cls, settings_name="zappa_settings", session=None):
        """Singleton instance to avoid repeat setup"""
        if LambdaHandler.__instance is None:
            print("Instancing..")
            LambdaHandler.__instance = object.__new__(cls)
        return LambdaHandler.__instance

    def __init__(self, settings_name="zappa_settings", session=None):

        # We haven't cached our settings yet, load the settings and app.
        if not self.settings:
            # Loading settings from a python module
            self.settings = importlib.import_module(settings_name)
            self.settings_name = settings_name
            self.session = session

            # Custom log level
            if self.settings.LOG_LEVEL:
                level = logging.getLevelName(self.settings.LOG_LEVEL)
                logger.setLevel(level)

            remote_env = getattr(self.settings, "REMOTE_ENV", None)
            remote_bucket, remote_file = parse_s3_url(remote_env)

            if remote_bucket and remote_file:
                self.load_remote_settings(remote_bucket, remote_file)

            # Let the system know that this will be a Lambda/Zappa/Stack
            os.environ["SERVERTYPE"] = "AWS Lambda"
            os.environ["FRAMEWORK"] = "Zappa"
            try:
                os.environ["PROJECT"] = self.settings.PROJECT_NAME
                os.environ["STAGE"] = self.settings.API_STAGE
            except Exception:  # pragma: no cover
                pass

            # Set any locally defined env vars
            # Environment variable keys can't be Unicode
            # https://github.com/Miserlou/Zappa/issues/604
            for key in self.settings.ENVIRONMENT_VARIABLES.keys():
                os.environ[str(key)] = self.settings.ENVIRONMENT_VARIABLES[key]

            # Pulling from S3 if given a zip path
            project_archive_path = getattr(self.settings, "ARCHIVE_PATH", None)
            if project_archive_path:
                self.load_remote_project_archive(project_archive_path)

            # Load compiled library to the PythonPath
            # checks if we are the slim_handler since this is not needed otherwise
            # https://github.com/Miserlou/Zappa/issues/776
            is_slim_handler = getattr(self.settings, "SLIM_HANDLER", False)
            if is_slim_handler:
                included_libraries = getattr(
                    self.settings, "INCLUDE", ["libmysqlclient.so.18"]
                )
                try:
                    from ctypes import cdll, util

                    for library in included_libraries:
                        try:
                            cdll.LoadLibrary(os.path.join(os.getcwd(), library))
                        except OSError:
                            print(
                                "Failed to find library: {}...right filename?".format(
                                    library
                                )
                            )
                except ImportError:
                    print("Failed to import cytpes library")

            # This is a non-WSGI application
            # https://github.com/Miserlou/Zappa/pull/748
            if (
                not hasattr(self.settings, "APP_MODULE")
                and not self.settings.DJANGO_SETTINGS
            ):
                self.app_module = None
                wsgi_app_function = None
            # This is probably a normal WSGI app (Or django with overloaded wsgi application)
            # https://github.com/Miserlou/Zappa/issues/1164
            elif hasattr(self.settings, "APP_MODULE"):
                if self.settings.DJANGO_SETTINGS:
                    sys.path.append("/var/task")
                    from django.conf import (
                        ENVIRONMENT_VARIABLE as SETTINGS_ENVIRONMENT_VARIABLE,
                    )

                    # add the Lambda root path into the sys.path
                    self.trailing_slash = True
                    os.environ[
                        SETTINGS_ENVIRONMENT_VARIABLE
                    ] = self.settings.DJANGO_SETTINGS
                else:
                    self.trailing_slash = False

                # The app module
                self.app_module = importlib.import_module(self.settings.APP_MODULE)

                # The application
                wsgi_app_function = getattr(self.app_module, self.settings.APP_FUNCTION)
            # Django gets special treatment.
            else:
                try:  # Support both for tests
                    from zappa.ext.django_zappa import get_django_wsgi
                except ImportError:  # pragma: no cover
                    from django_zappa_app import get_django_wsgi

                # Get the Django WSGI app from our extension
                wsgi_app_function = get_django_wsgi(self.settings.DJANGO_SETTINGS)
                self.trailing_slash = True

            self.wsgi_app = ZappaWSGIMiddleware(wsgi_app_function)

    def load_remote_project_archive(self, project_zip_path):
        """
        Puts the project files from S3 in /tmp and adds to path
        """
        project_folder = "/tmp/{0!s}".format(self.settings.PROJECT_NAME)
        if not os.path.isdir(project_folder):
            # The project folder doesn't exist in this cold lambda, get it from S3
            if not self.session:
                boto_session = boto3.Session()
            else:
                boto_session = self.session

            # Download zip file from S3
            remote_bucket, remote_file = parse_s3_url(project_zip_path)
            s3 = boto_session.resource("s3")
            archive_on_s3 = s3.Object(remote_bucket, remote_file).get()

            with tarfile.open(fileobj=archive_on_s3["Body"], mode="r|gz") as t:
                t.extractall(project_folder)

        # Add to project path
        sys.path.insert(0, project_folder)

        # Change working directory to project folder
        # Related: https://github.com/Miserlou/Zappa/issues/702
        os.chdir(project_folder)
        return True

    def load_remote_settings(self, remote_bucket, remote_file):
        """
        Attempt to read a file from s3 containing a flat json object. Adds each
        key->value pair as environment variables. Helpful for keeping
        sensitiZve or stage-specific configuration variables in s3 instead of
        version control.
        """
        if not self.session:
            boto_session = boto3.Session()
        else:
            boto_session = self.session

        s3 = boto_session.resource("s3")
        try:
            remote_env_object = s3.Object(remote_bucket, remote_file).get()
        except Exception as e:  # pragma: no cover
            # catch everything aws might decide to raise
            print("Could not load remote settings file.", e)
            return

        try:
            content = remote_env_object["Body"].read()
        except Exception as e:  # pragma: no cover
            # catch everything aws might decide to raise
            print("Exception while reading remote settings file.", e)
            return

        try:
            settings_dict = json.loads(content)
        except (ValueError, TypeError):  # pragma: no cover
            print("Failed to parse remote settings!")
            return

        # add each key-value to environment - overwrites existing keys!
        for key, value in settings_dict.items():
            if self.settings.LOG_LEVEL == "DEBUG":
                print("Adding {} -> {} to environment".format(key, value))
            # Environment variable keys can't be Unicode
            # https://github.com/Miserlou/Zappa/issues/604
            try:
                os.environ[str(key)] = value
            except Exception:
                if self.settings.LOG_LEVEL == "DEBUG":
                    print("Environment variable keys must be non-unicode!")

    @staticmethod
    def import_module_and_get_function(whole_function):
        """
        Given a modular path to a function, import that module
        and return the function.
        """
        module, function = whole_function.rsplit(".", 1)
        app_module = importlib.import_module(module)
        app_function = getattr(app_module, function)
        return app_function

    @classmethod
    def lambda_handler(cls, event, context):  # pragma: no cover
        handler = cls()
        exception_handler = handler.settings.EXCEPTION_HANDLER
        try:
            return handler.handler(event, context)
        except Exception as ex:
            exception_processed = cls._process_exception(
                exception_handler=exception_handler,
                event=event,
                context=context,
                exception=ex,
            )
            if not exception_processed:
                # Only re-raise exception if handler directed so. Allows handler to control if lambda has to retry
                # an event execution in case of failure.
                raise

    @classmethod
    def _process_exception(cls, exception_handler, event, context, exception):
        exception_processed = False
        if exception_handler:
            try:
                handler_function = cls.import_module_and_get_function(exception_handler)
                exception_processed = handler_function(exception, event, context)
            except Exception as cex:
                logger.error(msg="Failed to process exception via custom handler.")
                print(cex)
        return exception_processed

    @staticmethod
    def run_function(app_function, event, context):
        """
        Given a function and event context,
        detect signature and execute, returning any result.
        """
        # getargspec does not support python 3 method with type hints
        # Related issue: https://github.com/Miserlou/Zappa/issues/1452
        if hasattr(inspect, "getfullargspec"):  # Python 3
            args, varargs, keywords, defaults, _, _, _ = inspect.getfullargspec(
                app_function
            )
        else:  # Python 2
            args, varargs, keywords, defaults = inspect.getargspec(app_function)
        num_args = len(args)
        if num_args == 0:
            result = app_function(event, context) if varargs else app_function()
        elif num_args == 1:
            result = app_function(event, context) if varargs else app_function(event)
        elif num_args == 2:
            result = app_function(event, context)
        else:
            raise RuntimeError(
                "Function signature is invalid. Expected a function that accepts at most "
                "2 arguments or varargs."
            )
        return result

    def get_function_for_aws_event(self, record):
        """
        Get the associated function to execute for a triggered AWS event

        Support S3, SNS, DynamoDB, kinesis and SQS events
        """
        if "s3" in record:
            if ":" in record["s3"]["configurationId"]:
                return record["s3"]["configurationId"].split(":")[-1]

        arn = None
        if "Sns" in record:
            try:
                message = json.loads(record["Sns"]["Message"])
                if message.get("command"):
                    return message["command"]
            except ValueError:
                pass
            arn = record["Sns"].get("TopicArn")
        elif "dynamodb" in record or "kinesis" in record:
            arn = record.get("eventSourceARN")
        elif "eventSource" in record and record.get("eventSource") == "aws:sqs":
            arn = record.get("eventSourceARN")
        elif "s3" in record:
            arn = record["s3"]["bucket"]["arn"]

        if arn:
            return self.settings.AWS_EVENT_MAPPING.get(arn)

        return None

    def get_function_from_bot_intent_trigger(self, event):
        """
        For the given event build ARN and return the configured function
        """
        intent = event.get("currentIntent")
        if intent:
            intent = intent.get("name")
            if intent:
                return self.settings.AWS_BOT_EVENT_MAPPING.get(
                    "{}:{}".format(intent, event.get("invocationSource"))
                )

    def get_function_for_cognito_trigger(self, trigger):
        """
        Get the associated function to execute for a cognito trigger
        """
        print(
            "get_function_for_cognito_trigger",
            self.settings.COGNITO_TRIGGER_MAPPING,
            trigger,
            self.settings.COGNITO_TRIGGER_MAPPING.get(trigger),
        )
        return self.settings.COGNITO_TRIGGER_MAPPING.get(trigger)

    def handler(self, event, context):
        """
        An AWS Lambda function which parses specific API Gateway input into a
        WSGI request, feeds it to our WSGI app, processes the response, and returns
        that back to the API Gateway.

        """
        settings = self.settings

        # If in DEBUG mode, log all raw incoming events.
        if settings.DEBUG:
            logger.debug("Zappa Event: {}".format(event))

        # Set any API Gateway defined Stage Variables
        # as env vars
        if event.get("stageVariables"):
            for key in event["stageVariables"].keys():
                os.environ[str(key)] = event["stageVariables"][key]

        # This is the result of a keep alive, recertify
        # or scheduled event.
        if event.get("detail-type") == "Scheduled Event":

            whole_function = event["resources"][0].split("/")[-1].split("-")[-1]

            # This is a scheduled function.
            if "." in whole_function:
                app_function = self.import_module_and_get_function(whole_function)

                # Execute the function!
                return self.run_function(app_function, event, context)

            # Else, let this execute as it were.

        # This is a direct command invocation.
        elif event.get("command", None):

            whole_function = event["command"]
            app_function = self.import_module_and_get_function(whole_function)
            result = self.run_function(app_function, event, context)
            print("Result of %s:" % whole_function)
            print(result)
            return result

        # This is a direct, raw python invocation.
        # It's _extremely_ important we don't allow this event source
        # to be overridden by unsanitized, non-admin user input.
        elif event.get("raw_command", None):

            raw_command = event["raw_command"]
            exec(raw_command)
            return

        # This is a Django management command invocation.
        elif event.get("manage", None):

            from django.core import management

            try:  # Support both for tests
                from zappa.ext.django_zappa import get_django_wsgi
            except ImportError as e:  # pragma: no cover
                from django_zappa_app import get_django_wsgi

            # Get the Django WSGI app from our extension
            # We don't actually need the function,
            # but we do need to do all of the required setup for it.
            app_function = get_django_wsgi(self.settings.DJANGO_SETTINGS)

            # Couldn't figure out how to get the value into stdout with StringIO..
            # Read the log for now. :[]
            management.call_command(*event["manage"].split(" "))
            return {}

        # This is an AWS-event triggered invocation.
        elif event.get("Records", None):

            records = event.get("Records")
            result = None
            whole_function = self.get_function_for_aws_event(records[0])
            if whole_function:
                app_function = self.import_module_and_get_function(whole_function)
                result = self.run_function(app_function, event, context)
                logger.debug(result)
            else:
                logger.error("Cannot find a function to process the triggered event.")
            return result

        # this is an AWS-event triggered from Lex bot's intent
        elif event.get("bot"):
            result = None
            whole_function = self.get_function_from_bot_intent_trigger(event)
            if whole_function:
                app_function = self.import_module_and_get_function(whole_function)
                result = self.run_function(app_function, event, context)
                logger.debug(result)
            else:
                logger.error("Cannot find a function to process the triggered event.")
            return result

        # This is an API Gateway authorizer event
        elif event.get("type") == "TOKEN":
            whole_function = self.settings.AUTHORIZER_FUNCTION
            if whole_function:
                app_function = self.import_module_and_get_function(whole_function)
                policy = self.run_function(app_function, event, context)
                return policy
            else:
                logger.error(
                    "Cannot find a function to process the authorization request."
                )
                raise Exception("Unauthorized")

        # This is an AWS Cognito Trigger Event
        elif event.get("triggerSource", None):
            triggerSource = event.get("triggerSource")
            whole_function = self.get_function_for_cognito_trigger(triggerSource)
            result = event
            if whole_function:
                app_function = self.import_module_and_get_function(whole_function)
                result = self.run_function(app_function, event, context)
                logger.debug(result)
            else:
                logger.error(
                    "Cannot find a function to handle cognito trigger {}".format(
                        triggerSource
                    )
                )
            return result

        # This is a CloudWatch event
        # Related: https://github.com/Miserlou/Zappa/issues/1924
        elif event.get("awslogs", None):
            result = None
            whole_function = "{}.{}".format(settings.APP_MODULE, settings.APP_FUNCTION)
            app_function = self.import_module_and_get_function(whole_function)
            if app_function:
                result = self.run_function(app_function, event, context)
                logger.debug("Result of %s:" % whole_function)
                logger.debug(result)
            else:
                logger.error("Cannot find a function to process the triggered event.")
            return result

        # Normal web app flow
        try:
            # Timing
            time_start = datetime.datetime.now()

            # This is a normal HTTP request
            if event.get("httpMethod", None):
                script_name = ""
                is_elb_context = False
                headers = merge_headers(event)
                if event.get("requestContext", None) and event["requestContext"].get(
                    "elb", None
                ):
                    # Related: https://github.com/Miserlou/Zappa/issues/1715
                    # inputs/outputs for lambda loadbalancer
                    # https://docs.aws.amazon.com/elasticloadbalancing/latest/application/lambda-functions.html
                    is_elb_context = True
                    # host is lower-case when forwarded from ELB
                    host = headers.get("host")
                    # TODO: pathParameters is a first-class citizen in apigateway but not available without
                    # some parsing work for ELB (is this parameter used for anything?)
                    event["pathParameters"] = ""
                else:
                    if headers:
                        host = headers.get("Host")
                    else:
                        host = None
                    logger.debug("host found: [{}]".format(host))

                    if host:
                        if "amazonaws.com" in host:
                            logger.debug("amazonaws found in host")
                            # The path provided in th event doesn't include the
                            # stage, so we must tell Flask to include the API
                            # stage in the url it calculates. See https://github.com/Miserlou/Zappa/issues/1014
                            script_name = "/" + settings.API_STAGE
                    else:
                        # This is a test request sent from the AWS console
                        if settings.DOMAIN:
                            # Assume the requests received will be on the specified
                            # domain. No special handling is required
                            pass
                        else:
                            # Assume the requests received will be to the
                            # amazonaws.com endpoint, so tell Flask to include the
                            # API stage
                            script_name = "/" + settings.API_STAGE

                base_path = getattr(settings, "BASE_PATH", None)

                # Create the environment for WSGI and handle the request
                environ = create_wsgi_request(
                    event,
                    script_name=script_name,
                    base_path=base_path,
                    trailing_slash=self.trailing_slash,
                    binary_support=settings.BINARY_SUPPORT,
                    context_header_mappings=settings.CONTEXT_HEADER_MAPPINGS,
                )

                # We are always on https on Lambda, so tell our wsgi app that.
                environ["HTTPS"] = "on"
                environ["wsgi.url_scheme"] = "https"
                environ["lambda.context"] = context
                environ["lambda.event"] = event

                # Execute the application
                with Response.from_app(self.wsgi_app, environ) as response:
                    # This is the object we're going to return.
                    # Pack the WSGI response into our special dictionary.
                    zappa_returndict = dict()

                    # Issue #1715: ALB support. ALB responses must always include
                    # base64 encoding and status description
                    if is_elb_context:
                        zappa_returndict.setdefault("isBase64Encoded", False)
                        zappa_returndict.setdefault(
                            "statusDescription", response.status
                        )

                    if response.data:
                        if (
                            settings.BINARY_SUPPORT
                            and not response.mimetype.startswith("text/")
                            and response.mimetype != "application/json"
                        ):
                            zappa_returndict["body"] = base64.b64encode(
                                response.data
                            ).decode("utf-8")
                            zappa_returndict["isBase64Encoded"] = True
                        else:
                            zappa_returndict["body"] = response.get_data(as_text=True)

                    zappa_returndict["statusCode"] = response.status_code
                    if "headers" in event:
                        zappa_returndict["headers"] = {}
                        for key, value in response.headers:
                            zappa_returndict["headers"][key] = value
                    if "multiValueHeaders" in event:
                        zappa_returndict["multiValueHeaders"] = {}
                        for key, value in response.headers:
                            zappa_returndict["multiValueHeaders"][
                                key
                            ] = response.headers.getlist(key)

                    # Calculate the total response time,
                    # and log it in the Common Log format.
                    time_end = datetime.datetime.now()
                    delta = time_end - time_start
                    response_time_ms = delta.total_seconds() * 1000
                    response.content = response.data
                    common_log(environ, response, response_time=response_time_ms)

                    return zappa_returndict
        except Exception as e:  # pragma: no cover
            # Print statements are visible in the logs either way
            print(e)
            exc_info = sys.exc_info()
            message = (
                "An uncaught exception happened while servicing this request. "
                "You can investigate this with the `zappa tail` command."
            )

            # If we didn't even build an app_module, just raise.
            if not settings.DJANGO_SETTINGS:
                try:
                    self.app_module
                except NameError as ne:
                    message = "Failed to import module: {}".format(ne.message)

            # Call exception handler for unhandled exceptions
            exception_handler = self.settings.EXCEPTION_HANDLER
            self._process_exception(
                exception_handler=exception_handler,
                event=event,
                context=context,
                exception=e,
            )

            # Return this unspecified exception as a 500, using template that API Gateway expects.
            content = collections.OrderedDict()
            content["statusCode"] = 500
            body = {"message": message}
            if settings.DEBUG:  # only include traceback if debug is on.
                body["traceback"] = traceback.format_exception(
                    *exc_info
                )  # traceback as a list for readability.
            content["body"] = json.dumps(str(body), sort_keys=True, indent=4)
            return content


def lambda_handler(event, context):  # pragma: no cover
    return LambdaHandler.lambda_handler(event, context)


def keep_warm_callback(event, context):
    """Method is triggered by the CloudWatch event scheduled when keep_warm setting is set to true."""
    lambda_handler(
        event={}, context=context
    )  # overriding event with an empty one so that web app initialization will
    # be triggered.
