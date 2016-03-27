from __future__ import unicode_literals

import base64
import datetime
import importlib
import logging
import os

from urllib import urlencode
from StringIO import StringIO
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
logger.setLevel(logging.INFO)

class LambdaHandler(object):
    """
    Singleton for avoiding duplicate setup.

    Pattern provided by @benbangert.
    """

    __instance = None

    def __new__(cls, settings_name="zappa_settings"):
        """Singleton instance to avoid repeat setup"""

        if LambdaHandler.__instance is None:
            LambdaHandler.__instance = object.__new__(cls)
        return LambdaHandler.__instance

    def __init__(self, settings_name="zappa_settings"):

        # Loading settings from a python module
        self.settings = importlib.import_module(settings_name)
        self.settings_name = settings_name

    @classmethod
    def lambda_handler(cls, event, context): # pragma: no cover
        return cls().handler(event, context)

    def handler(self, event, context):
        """ 
        An AWS Lambda function which parses specific API Gateway input into a
        WSGI request, feeds it to our WSGI app, procceses the response, and returns
        that back to the API Gateway.
        
        """

        time_start = datetime.datetime.now()

        settings = self.settings

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
            if event_echo:
                if 'event_echo' in list(event['params'].values()):
                    return {'Content': str(event) + '\n' + str(context), 'Status': 200}

            # Create the environment for WSGI and handle the request
            environ = create_wsgi_request(event, script_name='',
                                          trailing_slash=False)

            # We are always on https on Lambda, so tell our wsgi app that.
            environ['wsgi.url_scheme'] = 'https'

            response = Response.from_app(app, environ)

            zappa_returndict = dict()

            if response.data:
                zappa_returndict['Content'] = response.data

            # Pack the WSGI response into our special dictionary.
            for (header_name, header_value) in response.headers:
                zappa_returndict[header_name] = header_value
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
                raise Exception(exception)
            else:
                return zappa_returndict

def lambda_handler(event, context): # pragma: no cover
    return LambdaHandler.lambda_handler(event, context)
