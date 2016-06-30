from __future__ import unicode_literals

import base64
import datetime
import importlib
import logging
import traceback
import os
import json

import boto3
from werkzeug.wrappers import Response

# This file may be copied into a project's root,
# so handle both scenarios.
try:
    from zappa.wsgi import create_wsgi_request, common_log
    from zappa.middleware import ZappaWSGIMiddleware
except ImportError as e: # pragma: no cover
    from .wsgi import create_wsgi_request, common_log
    from .middleware import ZappaWSGIMiddleware

# Set up logging
logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

class LambdaException(Exception):
    pass

class LambdaHandler(object):
    """
    Singleton for avoiding duplicate setup.

    Pattern provided by @benbangert.
    """

    __instance = None
    settings = None
    settings_name = None
    session = None

    def __new__(cls, settings_name="zappa_settings", session=None):
        """Singleton instance to avoid repeat setup"""

        if LambdaHandler.__instance is None:
            LambdaHandler.__instance = object.__new__(cls, settings_name, session)
        return LambdaHandler.__instance

    def __init__(self, settings_name="zappa_settings", session=None):

        # Loading settings from a python module
        self.settings = importlib.import_module(settings_name)
        self.settings_name = settings_name
        self.session = session

        remote_bucket = getattr(self.settings, 'REMOTE_ENV_BUCKET', None)
        remote_file = getattr(self.settings, 'REMOTE_ENV_FILE', None)

        if remote_bucket and remote_file:
            self.load_remote_settings(remote_bucket, remote_file)

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
        except Exception as e: # pragma: no cover
            # catch everything aws might decide to raise
            print('Exception while reading remote settings file.', e)
            return

        try:
            settings_dict = json.loads(content)
        except (ValueError, TypeError): # pragma: no cover
            print('Failed to parse remote settings!')
            return

        # add each key-value to environment - overwrites existing keys!
        for key, value in settings_dict.items():
            print('Adding {} -> {} to environment'.format(
                key,
                value
            ))
            os.environ[key] = value

    @classmethod
    def lambda_handler(cls, event, context): # pragma: no cover
        return cls().handler(event, context)

    def handler(self, event, context):
        """ 
        An AWS Lambda function which parses specific API Gateway input into a
        WSGI request, feeds it to our WSGI app, procceses the response, and returns
        that back to the API Gateway.
        
        """

        # TODO If this is invoked from a non-APIGW/Scheduled event source,
        # extract the method and process separately.

        if event.get('detail-type') == u'Scheduled Event':
            
            whole_function = event['resources'][0].split('/')[-1]
            module, function = whole_function.rsplit('.', 1)

            app_module = importlib.import_module(module)
            app_function = getattr(app_module, function)

            # Execute the function!
            app_function()
            return

        try:
            # Timing
            time_start = datetime.datetime.now()

            settings = self.settings

            # Custom log level
            if settings.LOG_LEVEL:
                level = logging.getLevelName(settings.LOG_LEVEL)
                logger.setLevel(level)

            # The app module
            app_module = importlib.import_module(settings.APP_MODULE)

            # The application
            app_function = getattr(app_module, settings.APP_FUNCTION)
            app = ZappaWSGIMiddleware(app_function)

            # This is a normal HTTP request
            if event.get('method', None):
                # If we just want to inspect this,
                # return this event instead of processing the request
                # https://your_api.aws-api.com/?event_echo=true
                event_echo = getattr(settings, "EVENT_ECHO", True)
                if event_echo and 'event_echo' in event['params'].values():
                    return {'Content': str(event) + '\n' + str(context), 'Status': 200}

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
                environ = create_wsgi_request(event, 
                                                script_name=script_name,
                                                trailing_slash=False
                                            )

                # We are always on https on Lambda, so tell our wsgi app that.
                environ['wsgi.url_scheme'] = 'https'

                # Execute the application
                response = Response.from_app(app, environ)

                # This is the object we're going to return.
                # Pack the WSGI response into our special dictionary.
                zappa_returndict = dict(response.headers)

                if 'Content' not in zappa_returndict and response.data:
                    zappa_returndict['Content'] = response.data

                zappa_returndict['Status'] = response.status_code

                # To ensure correct status codes, we need to
                # pack the response as a deterministic B64 string and raise it
                # as an error to match our APIGW regex.
                # The DOCTYPE ensures that the page still renders in the browser.
                exception = None
                if response.status_code in [400, 401, 403, 404, 500]:
                    content = "<!DOCTYPE html>" + str(response.status_code) + response.data
                    exception = base64.b64encode(content)
                # Internal are changed to become relative redirects
                # so they still work for apps on raw APIGW and on a domain.
                elif response.status_code in [301, 302]:
                    # Location is by default relative on Flask. Location is by default
                    # absolute on Werkzeug. We can set autocorrect_location_header on
                    # the response to False, but it doesn't work. We have to manually
                    # remove the host part.
                    location = response.location
                    hostname = 'https://' + environ['HTTP_HOST']
                    if location.startswith(hostname):
                        exception = location[len(hostname):]

                # Calculate the total response time,
                # and log it in the Common Log format.
                time_end = datetime.datetime.now()
                delta = time_end - time_start
                response_time_ms = delta.total_seconds() * 1000
                response.content = response.data
                common_log(environ, response, response_time=response_time_ms)

                # Finally, return the response to API Gateway.
                if exception: # pragma: no cover
                    raise LambdaException(exception)
                else:
                    return zappa_returndict
        except LambdaException as e: # pragma: no cover
            raise e
        except Exception as e: # pragma: no cover

            # Print statements are visible in the logs either way
            print(e)

            # Print the error to the browser upon failure?
            debug = bool(getattr(app_module, settings.DEBUG, True))
            if debug:
                # Return this unspecified exception as a 500.
                content = "<!DOCTYPE html>500. From Zappa: <pre>" + str(e) + "</pre><br /><pre>" + traceback.format_exc().replace('\n', '<br />') + "</pre>"
                exception = base64.b64encode(content)
                raise Exception(exception)
            else:
                raise e


def lambda_handler(event, context): # pragma: no cover

    return LambdaHandler.lambda_handler(event, context)
