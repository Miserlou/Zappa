from __future__ import unicode_literals

import base64
import datetime
import importlib
import logging
import traceback
import os
import json
import inspect
import collections

import boto3
import sys
from werkzeug.wrappers import Response

# This file may be copied into a project's root,
# so handle both scenarios.
try:
    from zappa.cli import ZappaCLI
    from zappa.middleware import ZappaWSGIMiddleware
    from zappa.wsgi import create_wsgi_request, common_log
except ImportError as e:  # pragma: no cover
    from .cli import ZappaCLI
    from .middleware import ZappaWSGIMiddleware
    from .wsgi import create_wsgi_request, common_log

# Set up logging
logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.INFO)

ERROR_CODES = [400, 401, 403, 404, 500]


class WSGIException(Exception):
    """
    This exception is used by the handler to indicate that underlying WSGI app has returned a non-2xx(3xx) code.
    """

    pass


class UncaughtWSGIException(Exception):
    """
    Indicates a problem that happened outside of WSGI app context (and thus wasn't handled by the WSGI app itself)
    while processing a request from API Gateway.
    """

    def __init__(self, message, original=None):
        super(UncaughtWSGIException, self).__init__(message)
        self.original = original


class LambdaHandler(object):
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
            LambdaHandler.__instance = object.__new__(cls, settings_name, session)
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

            remote_bucket = getattr(self.settings, 'REMOTE_ENV_BUCKET', None)
            remote_file = getattr(self.settings, 'REMOTE_ENV_FILE', None)

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
            for key in self.settings.ENVIRONMENT_VARIABLES.keys():
                os.environ[key] = self.settings.ENVIRONMENT_VARIABLES[key]

            # Django gets special treatment.
            if not self.settings.DJANGO_SETTINGS:
                # The app module
                self.app_module = importlib.import_module(self.settings.APP_MODULE)

                # The application
                wsgi_app_function = getattr(self.app_module, self.settings.APP_FUNCTION)
                self.trailing_slash = False
            else:

                try:  # Support both for tests
                    from zappa.ext.django import get_django_wsgi
                except ImportError as e:  # pragma: no cover
                    from django_zappa_app import get_django_wsgi

                # Get the Django WSGI app from our extension
                wsgi_app_function = get_django_wsgi(self.settings.DJANGO_SETTINGS)
                self.trailing_slash = True

            self.wsgi_app = ZappaWSGIMiddleware(wsgi_app_function)

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

        s3 = boto_session.resource('s3')
        try:
            remote_env_object = s3.Object(remote_bucket, remote_file).get()
        except Exception as e:  # pragma: no cover
            # catch everything aws might decide to raise
            print('Could not load remote settings file.', e)
            return

        try:
            content = remote_env_object['Body'].read().decode('utf-8')
        except Exception as e:  # pragma: no cover
            # catch everything aws might decide to raise
            print('Exception while reading remote settings file.', e)
            return

        try:
            settings_dict = json.loads(content)
        except (ValueError, TypeError):  # pragma: no cover
            print('Failed to parse remote settings!')
            return

        # add each key-value to environment - overwrites existing keys!
        for key, value in settings_dict.items():
            if self.settings.LOG_LEVEL == "DEBUG":
                print('Adding {} -> {} to environment'.format(
                    key,
                    value
                ))
            os.environ[key] = value

    @staticmethod
    def import_module_and_get_function(whole_function):
        """
        Given a modular path to a function, import that module
        and return the function.
        """
        module, function = whole_function.rsplit('.', 1)
        app_module = importlib.import_module(module)
        app_function = getattr(app_module, function)
        return app_function

    @classmethod
    def lambda_handler(cls, event, context):  # pragma: no cover
        handler = cls()
        exception_handler = handler.settings.EXCEPTION_HANDLER
        try:
            return handler.handler(event, context)
        except WSGIException as wsgi_ex:
            # do nothing about LambdaExceptions since those are already handled (or should be handled by the WSGI app).
            raise wsgi_ex
        except UncaughtWSGIException as u_wsgi_ex:
            # hand over original error to exception handler, since the exception happened outside of WSGI app context
            # (it wasn't propertly processed by the app itself)
            cls._process_exception(exception_handler=exception_handler,
                                   event=event, context=context, exception=u_wsgi_ex.original)
            # raise unconditionally since it's an API gateway error (i.e. client expects to see a 500 and execution
            # won't be retried).
            raise u_wsgi_ex
        except Exception as ex:
            exception_processed = cls._process_exception(exception_handler=exception_handler,
                                                         event=event, context=context, exception=ex)
            if not exception_processed:
                # Only re-raise exception if handler directed so. Allows handler to control if lambda has to retry
                # an event execution in case of failure.
                raise ex

    @classmethod
    def _process_exception(cls, exception_handler, event, context, exception):
        exception_processed = False
        if exception_handler:
            try:
                handler_function = cls.import_module_and_get_function(exception_handler)
                exception_processed = handler_function(exception, event, context)
            except Exception as cex:
                logger.error(msg='Failed to process exception via custom handler.')
                print(cex)
        return exception_processed

    @staticmethod
    def run_function(app_function, event, context):
        """
        Given a function and event context,
        detect signature and execute, returning any result.
        """
        args, varargs, keywords, defaults = inspect.getargspec(app_function)
        num_args = len(args)
        if num_args == 0:
            result = app_function(event, context) if varargs else app_function()
        elif num_args == 1:
            result = app_function(event, context) if varargs else app_function(event)
        elif num_args == 2:
            result = app_function(event, context)
        else:
            raise RuntimeError("Function signature is invalid. Expected a function that accepts at most "
                               "2 arguments or varargs.")
        return result

    def update_certificate(self):
        """
        Call 'certify' locally.
        """
        import boto3
        session = boto3.Session()

        z_cli = ZappaCLI()
        z_cli.api_stage = self.settings.API_STAGE
        z_cli.load_settings(session=session)
        z_cli.certify()

        return

    def get_function_for_aws_event(self, record):
        """
        Get the associated function to execute for a triggered AWS event

        Support S3, SNS, DynamoDB and kinesis events
        """
        if 's3' in record:
            return record['s3']['configurationId']

        arn = None
        if 'Sns' in record:
            arn = record['Sns'].get('TopicArn')
        elif 'dynamodb' in record or 'kinesis' in record:
            arn = record.get('eventSourceARN')

        if arn:
            return self.settings.AWS_EVENT_MAPPING.get(arn)

        return None

    def handler(self, event, context):
        """
        An AWS Lambda function which parses specific API Gateway input into a
        WSGI request, feeds it to our WSGI app, procceses the response, and returns
        that back to the API Gateway.

        """
        settings = self.settings

        # If in DEBUG mode, log all raw incoming events.
        if settings.DEBUG:
            print('Zappa Event: {}'.format(event))
            logger.debug('Zappa Event: {}'.format(event))

        # This is the result of a keep alive, recertify
        # or scheduled event.
        if event.get('detail-type') == u'Scheduled Event':

            whole_function = event['resources'][0].split('/')[-1].split('-')[-1]

            # This is a scheduled function.
            if '.' in whole_function:
                app_function = self.import_module_and_get_function(whole_function)

                # Execute the function!
                return self.run_function(app_function, event, context)

            # Else, let this execute as it were.

        # This is a direct command invocation.
        elif event.get('command', None):

            whole_function = event['command']
            app_function = self.import_module_and_get_function(whole_function)
            result = self.run_function(app_function, event, context)
            print("Result of %s:" % whole_function)
            print(result)
            return result

        # This is a direct, raw python invocation.
        # It's _extremely_ important we don't allow this event source
        # to be overriden by unsanitized, non-admin user input.
        elif event.get('raw_command', None):

            raw_command = event['raw_command']
            exec(raw_command)
            return

        # This is a Django management command invocation.
        elif event.get('manage', None):

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
            management.call_command(*event['manage'].split(' '))
            return {}

        # This is an AWS-event triggered invokation.
        elif event.get('Records', None):

            records = event.get('Records')
            result = None
            whole_function = self.get_function_for_aws_event(records[0])
            if whole_function:
                app_function = self.import_module_and_get_function(whole_function)
                result = self.run_function(app_function, event, context)
                logger.debug(result)
            else:
                logger.error("Cannot find a function to process the triggered event.")
            return result

        # This is an API Gateway authorizer event
        elif event.get('type') == u'TOKEN':
            whole_function = self.settings.AUTHORIZER_FUNCTION
            if whole_function:
                app_function = self.import_module_and_get_function(whole_function)
                policy = self.run_function(app_function, event, context)
                return policy
            else:
                logger.error("Cannot find a function to process the authorization request.")
                raise Exception('Unauthorized')

        # Normal web app flow
        try:
            # Timing
            time_start = datetime.datetime.now()

            # This is a normal HTTP request
            if event.get('httpMethod', None):
                # If we just want to inspect this,
                # return this event instead of processing the request
                # https://your_api.aws-api.com/?event_echo=true
                # event_echo = getattr(settings, "EVENT_ECHO", True)
                # if event_echo and 'event_echo' in event['params'].values():
                #     return {'Content': str(event) + '\n' + str(context), 'Status': 200}

                if settings.DOMAIN:
                    # If we're on a domain, we operate normally
                    script_name = ''
                else:
                    # But if we're not, then our base URL
                    # will be something like
                    # https://blahblahblah.execute-api.us-east-1.amazonaws.com/dev
                    # So, we need to make sure the WSGI app knows this.
                    script_name = '/' + settings.API_STAGE

                # Create the environment for WSGI and handle the request
                environ = create_wsgi_request(
                    event,
                    script_name=script_name,
                    trailing_slash=self.trailing_slash
                )

                # We are always on https on Lambda, so tell our wsgi app that.
                environ['HTTPS'] = 'on'
                environ['wsgi.url_scheme'] = 'https'
                environ['lambda.context'] = context

                # Execute the application
                response = Response.from_app(self.wsgi_app, environ)

                # This is the object we're going to return.
                # Pack the WSGI response into our special dictionary.
                zappa_returndict = dict()

                if response.data:
                    zappa_returndict['body'] = response.data

                zappa_returndict['statusCode'] = response.status_code
                zappa_returndict['headers'] = {}
                for key, value in response.headers:
                    zappa_returndict['headers'][key] = value

                # To ensure correct status codes, we need to
                # pack the response as a deterministic B64 string and raise it
                # as an error to match our APIGW regex.
                # The DOCTYPE ensures that the page still renders in the browser.
                exception = None
                # if response.status_code in ERROR_CODES:
                #     content = collections.OrderedDict()
                #     content['http_status'] = response.status_code
                #     content['content'] = base64.b64encode(response.data.encode('utf-8'))
                #     exception = json.dumps(content)
                # # Internal are changed to become relative redirects
                # # so they still work for apps on raw APIGW and on a domain.
                # elif 300 <= response.status_code < 400 and hasattr(response, 'Location'):
                #     # Location is by default relative on Flask. Location is by default
                #     # absolute on Werkzeug. We can set autocorrect_location_header on
                #     # the response to False, but it doesn't work. We have to manually
                #     # remove the host part.
                #     location = response.location
                #     hostname = 'https://' + environ['HTTP_HOST']
                #     if location.startswith(hostname):
                #         exception = location[len(hostname):]
                #     else:
                #         exception = location

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
            message = 'An uncaught exception happened while servicing this request. You can investigate this with the `zappa tail` command.'

            # If we didn't even build an app_module, just raise.
            if not settings.DJANGO_SETTINGS:
                try:
                    self.app_module
                except NameError as ne:
                    message = 'Failed to import module: {}'.format(ne.message)

            # Return this unspecified exception as a 500, using template that API Gateway expects.
            content = collections.OrderedDict()
            content['statusCode'] = 500
            body = {'message': message}
            if settings.DEBUG:  # only include traceback if debug is on.
                body['traceback'] = traceback.format_exception(*exc_info)  # traceback as a list for readability.
            content['body'] = json.dumps(body, sort_keys=True, indent=4).encode('utf-8')
            return content

def lambda_handler(event, context):  # pragma: no cover
    return LambdaHandler.lambda_handler(event, context)


def keep_warm_callback(event, context):
    """Method is triggered by the CloudWatch event scheduled when keep_warm setting is set to true."""
    lambda_handler(event={}, context=context)  # overriding event with an empty one so that web app initialization will
    # be triggered.


def certify_callback(event, context):
    """
    Load our LH settings and update our cert.
    """
    lh = LambdaHandler()
    return lh.update_certificate()
