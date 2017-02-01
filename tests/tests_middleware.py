# -*- coding: utf8 -*-
import unittest
import base58
import json

from werkzeug.wrappers import Response
from werkzeug.http import parse_cookie

from zappa.wsgi import create_wsgi_request
from zappa.middleware import ZappaWSGIMiddleware, all_casings


class TestWSGIMockMiddleWare(unittest.TestCase):
    """
    These tests can cheat and have access to the inner status and headers,
    through _start_response.
    """
    def setUp(self):
        """
        Set the test up with default headers and status codes.
        """
        self.headers = list()
        self.status = list()

    def _start_response(self, status, headers, exc_info=None):
        self.status[:] = [status]
        self.headers[:] = headers

    def test_all_casings(self):

        # 2^9
        input_string = "Set-Cookie"
        x = 0
        for casing in all_casings(input_string):
            x = x + 1
        self.assertEqual(x, 512)

        # 2^0
        input_string = ""
        x = 0
        for casing in all_casings(input_string):
            x = x + 1
        self.assertEqual(x, 1)

    def test_wsgi_middleware_uglystring(self):
        ugly_string = unicode("˝ÓÔÒÚÆ☃ЗИЙКЛМФХЦЧШ차를 타고 온 펲시맨(╯°□°）╯︵ ┻━┻)"
                              "לֹהִים, אֵת הַשָּׁמַיִם, וְאֵת הָt͔̦h̞̲e̢̤ ͍̬̲͖f̴̘͕̣è͖ẹ̥̩l͖͔͚i͓͚̦͠n͖͍̗͓̳̮g͍ ̨ 𝕢𝕦𝕚𝕔𝕜 𝕓𝕣𝕠𝕨",
                              encoding='utf8')

        # Pass some unicode through the middleware body
        def simple_app(environ, start_response):
            # String of weird characters
            status = '200 OK'
            response_headers = []
            start_response(status, response_headers)
            return [ugly_string]

        # Wrap the app with the middleware
        app = ZappaWSGIMiddleware(simple_app)

        # Call with empty WSGI Environment
        resp = app(dict(), self._start_response)
        print(''.join(resp))

        # Pass some unicode through the middleware headers
        def simple_app(environ, start_response):
            # String of weird characters
            status = '301 Moved Permanently'
            response_headers = [('Location', 'http://zappa.com/elsewhere' + ugly_string)]
            start_response(status, response_headers)
            return [ugly_string]

        # Wrap the app with the middleware
        app = ZappaWSGIMiddleware(simple_app)

        # Call with empty WSGI Environment
        resp = app(dict(), self._start_response)
        print(''.join(resp))

    def test_wsgi_authorizer_handling(self):
        # With user
        event = {
            u'httpMethod': u'GET',
            u'queryStringParameters': None,
            u'path': u'/v1/runs',
            u'params': {},
            u'body': {},
            u'headers': {
                u'Content-Type': u'application/json'
            },
            u'pathParameters': {
                u'proxy': 'v1/runs'
            },
            u'requestContext': {
                u'authorizer': {
                    u'principalId': u'user1'
                }
            },
            u'query': {}
        }

        environ = create_wsgi_request(event, script_name='http://zappa.com/',
                                      trailing_slash=False)
        self.assertEqual(environ['REMOTE_USER'], u'user1')

        # With empty authorizer, should not include REMOTE_USER
        event = {
            u'httpMethod': u'GET',
            u'queryStringParameters': None,
            u'path': u'/v1/runs',
            u'params': {},
            u'body': {},
            u'headers': {
                u'Content-Type': u'application/json'
            },
            u'pathParameters': {
                u'proxy': 'v1/runs'
            },
            u'requestContext': {
                u'authorizer': {
                    u'principalId': u''
                }
            },
            u'query': {}
        }

        environ = create_wsgi_request(event, script_name='http://zappa.com/',
                                      trailing_slash=False)
        user = environ.get('REMOTE_USER', u'no_user')
        self.assertEqual(user, u'no_user')

        # With missing authorizer, should not include REMOTE_USER
        event = {
            u'httpMethod': u'GET',
            u'queryStringParameters': None,
            u'path': u'/v1/runs',
            u'params': {},
            u'body': {},
            u'headers': {
                u'Content-Type': u'application/json'
            },
            u'pathParameters': {
                u'proxy': 'v1/runs'
            },
            u'requestContext': {},
            u'query': {}
        }

        environ = create_wsgi_request(event, script_name='http://zappa.com/',
                                      trailing_slash=False)
        user = environ.get('REMOTE_USER', u'no_user')
        self.assertEqual(user, u'no_user')

        # With empty authorizer, should not include REMOTE_USER
        event = {
            u'httpMethod': u'GET',
            u'queryStringParameters': None,
            u'path': u'/v1/runs',
            u'params': {},
            u'body': {},
            u'headers': {
                u'Content-Type': u'application/json'
            },
            u'pathParameters': {
                u'proxy': 'v1/runs'
            },
            u'requestContext': {
                u'authorizer': {}
            },
            u'query': {}
        }

        environ = create_wsgi_request(event, script_name='http://zappa.com/',
                                      trailing_slash=False)
        user = environ.get('REMOTE_USER', u'no_user')
        self.assertEqual(user, u'no_user')
