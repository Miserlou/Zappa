import logging

import base64
from urllib import urlencode
from requestlogger import ApacheFormatter
from StringIO import StringIO


def create_wsgi_request(event_info, server_name='zappa', script_name=None,
                        trailing_slash=True):
        """
        Given some event_info,
        create and return a valid WSGI request environ.
        """

        method = event_info['httpMethod']
        params = event_info['pathParameters']
        query = event_info['queryStringParameters']
        headers = event_info['headers']

        # Extract remote user from context if Authorizer is enabled
        remote_user = None
        if event_info['requestContext'].get('authorizer'):
            remote_user = event_info['requestContext']['authorizer'].get('principalId')

        # Non-GET data is B64'd through the APIGW.
        # if method in ["POST", "PUT", "PATCH"]:
        #     encoded_body = event_info['body']
        #     body = base64.b64decode(encoded_body)
        # else:

        body = event_info['body']
        # Will this generate unicode errors?
        # Early experiments indicate no, but this still looks unsafe to me.
        body = str(body)

        # Make header names canonical, e.g. content-type => Content-Type
        for header in headers.keys():
            canonical = header.title()
            if canonical != header:
                headers[canonical] = headers.pop(header)

        path = event_info['path']

        # if 'url' in params:
        #     # new style
        #     path = '/' + params.get('url') + "/"
        # else:
        #     # old style
        #     path = "/"
        #     for key in sorted(params.keys()):
        #         path = path + params[key] + "/"

        #     # This determines if we should return
        #     # site.com/resource/ : site.com/resource
        #     # site.com/resource : site.com/resource
        #     # vs.
        #     # site.com/resource/ : site.com/resource/
        #     # site.com/resource : site.com/resource/
        #     # If no params are present, keep the slash.
        # if not trailing_slash and params.keys():
        #     path = path[:-1]

        if query:
            query_string = urlencode(query)
        else:
            query_string = ""

        x_forwarded_for = headers.get('X-Forwarded-For', '')
        if ',' in x_forwarded_for:
            remote_addr = x_forwarded_for.split(', ')[0]
        else:
            remote_addr = '127.0.0.1'

        environ = {
            'PATH_INFO': path,
            'QUERY_STRING': query_string,
            'REMOTE_ADDR': remote_addr,
            'REQUEST_METHOD': method,
            'SCRIPT_NAME': str(script_name) if script_name else '',
            'SERVER_NAME': str(server_name),
            'SERVER_PORT': str('80'),
            'SERVER_PROTOCOL': str('HTTP/1.1'),
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': str('http'),
            'wsgi.input': body,
            'wsgi.errors': str(''),
            'wsgi.multiprocess': False,
            'wsgi.multithread': False,
            'wsgi.run_once': False,
        }

        # Input processing
        if method in ["POST", "PUT", "PATCH"]:
            if 'Content-Type' in headers:
                environ['CONTENT_TYPE'] = headers['Content-Type']

            environ['wsgi.input'] = StringIO(body)
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

        return environ


def common_log(environ, response, response_time=None):
    """
    Given the WSGI environ and the response,
    log this event in Common Log Format.

    """

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

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
