from __future__ import unicode_literals

import base64
import logging
import six
import sys

from requestlogger import ApacheFormatter
from sys import stderr
from werkzeug import urls

# The joy of version splintering.
if sys.version_info[0] < 3:
    from urllib import urlencode
else:
    from urllib.parse import urlencode

BINARY_METHODS = [
                    "POST",
                    "PUT",
                    "PATCH",
                    "DELETE",
                    "CONNECT",
                    "OPTIONS"
                ]


def create_wsgi_request(event_info,
                        server_name='zappa',
                        script_name=None,
                        trailing_slash=True,
                        binary_support=False,
                        context_header_mappings={}
                        ):
        """
        Given some event_info via API Gateway,
        create and return a valid WSGI request environ.
        """
        method = event_info['httpMethod']
        params = event_info['pathParameters']
        query = event_info['queryStringParameters'] # APIGW won't allow multiple entries, ex ?id=a&id=b
        headers = event_info['headers'] or {} # Allow for the AGW console 'Test' button to work (Pull #735)

        if context_header_mappings:
            for key, value in context_header_mappings.items():
                parts = value.split('.')
                header_val = event_info['requestContext']
                for part in parts:
                    if part not in header_val:
                        header_val = None
                        break
                    else:
                        header_val = header_val[part]
                if header_val is not None:
                    headers[key] = header_val

        # Extract remote user from context if Authorizer is enabled
        remote_user = None
        if event_info['requestContext'].get('authorizer'):
            remote_user = event_info['requestContext']['authorizer'].get('principalId')
        elif event_info['requestContext'].get('identity'):
            remote_user = event_info['requestContext']['identity'].get('userArn')

        # Related:  https://github.com/Miserlou/Zappa/issues/677
        #           https://github.com/Miserlou/Zappa/issues/683
        #           https://github.com/Miserlou/Zappa/issues/696
        #           https://github.com/Miserlou/Zappa/issues/836
        #           https://en.wikipedia.org/wiki/Hypertext_Transfer_Protocol#Summary_table
        if binary_support and (method in BINARY_METHODS):
            if event_info.get('isBase64Encoded', False):
                encoded_body = event_info['body']
                body = base64.b64decode(encoded_body)
            else:
                body = event_info['body']
                if isinstance(body, six.string_types):
                    body = body.encode("utf-8")

        else:
            body = event_info['body']
            if isinstance(body, six.string_types):
                body = body.encode("utf-8")

        # Make header names canonical, e.g. content-type => Content-Type
        for header in headers.keys():
            canonical = header.title()
            if canonical != header:
                headers[canonical] = headers.pop(header)

        path = urls.url_unquote(event_info['path'])

        if query:
            query_string = urlencode(query)
        else:
            query_string = ""

        x_forwarded_for = headers.get('X-Forwarded-For', '')
        if ',' in x_forwarded_for:
            # The last one is the cloudfront proxy ip. The second to last is the real client ip.
            # Everything else is user supplied and untrustworthy.
            remote_addr = x_forwarded_for.split(', ')[-2]
        else:
            remote_addr = '127.0.0.1'

        environ = {
            'PATH_INFO': path,
            'QUERY_STRING': query_string,
            'REMOTE_ADDR': remote_addr,
            'REQUEST_METHOD': method,
            'SCRIPT_NAME': str(script_name) if script_name else '',
            'SERVER_NAME': str(server_name),
            'SERVER_PORT': headers.get('X-Forwarded-Port', '80'),
            'SERVER_PROTOCOL': str('HTTP/1.1'),
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': headers.get('X-Forwarded-Proto', 'http'),
            'wsgi.input': body,
            'wsgi.errors': stderr,
            'wsgi.multiprocess': False,
            'wsgi.multithread': False,
            'wsgi.run_once': False,
        }

        # Input processing
        if method in ["POST", "PUT", "PATCH", "DELETE"]:
            if 'Content-Type' in headers:
                environ['CONTENT_TYPE'] = headers['Content-Type']

            # This must be Bytes or None
            environ['wsgi.input'] = six.BytesIO(body)
            if body:
                environ['CONTENT_LENGTH'] = str(len(body))
            else:
                environ['CONTENT_LENGTH'] = '0'

        for header in headers:
            wsgi_name = "HTTP_" + header.upper().replace('-', '_')
            environ[wsgi_name] = str(headers[header])

        if script_name:
            environ['SCRIPT_NAME'] = script_name
            path_info = environ['PATH_INFO']

            if script_name in path_info:
                environ['PATH_INFO'].replace(script_name, '')

        if remote_user:
            environ['REMOTE_USER'] = remote_user

        if event_info['requestContext'].get('authorizer'):
            environ['API_GATEWAY_AUTHORIZER'] = event_info['requestContext']['authorizer']

        return environ


def common_log(environ, response, response_time=None):
    """
    Given the WSGI environ and the response,
    log this event in Common Log Format.

    """

    logger = logging.getLogger()

    if response_time:
        formatter = ApacheFormatter(with_response_time=True)
        try:
            log_entry = formatter(response.status_code, environ,
                                  len(response.content), rt_us=response_time)
        except TypeError:
            # Upstream introduced a very annoying breaking change on the rt_ms/rt_us kwarg.
            log_entry = formatter(response.status_code, environ,
                                  len(response.content), rt_ms=response_time)
    else:
        formatter = ApacheFormatter(with_response_time=False)
        log_entry = formatter(response.status_code, environ,
                              len(response.content))

    logger.info(log_entry)

    return log_entry
