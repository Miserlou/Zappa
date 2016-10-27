# -*- coding: utf8 -*-
import unittest
import base58
import json

from werkzeug.wrappers import Response
from werkzeug.http import parse_cookie

from zappa.wsgi import create_wsgi_request
from zappa.middleware import ZappaWSGIMiddleware


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

    def test_wsgi_middleware_multiplecookies(self):
        def simple_app(environ, start_response):
            status = '200 OK'
            response_headers = [('Set-Cookie', 'foo=123'),
                                ('Set-Cookie', 'bar=456')]
            start_response(status, response_headers)
            return ['Hello zappa!']

        # Wrap the app with the middleware
        app = ZappaWSGIMiddleware(simple_app)

        # Call with empty WSGI Environment
        resp = app(dict(), self._start_response)

        self.assertEqual(self.status[0], '200 OK')

        # Assert there is only one zappa cookie
        self.assertEqual(len(self.headers), 1)
        self.assertEqual(self.headers[0][0], 'Set-Cookie')
        self.assertTrue(self.headers[0][1].startswith('zappa='))

        self.assertEqual(''.join(resp), 'Hello zappa!')

    def test_wsgi_middleware_unpackcookies(self):
        # Setting the cookies
        def simple_app(environ, start_response):
            status = '200 OK'
            response_headers = [('Set-Cookie', 'foo=123'),
                                ('Set-Cookie', 'bar=456'),
                                ('Set-Cookie', 'baz=789')]
            start_response(status, response_headers)
            return ['Set cookies!']

        # Wrap the app with the middleware
        app = ZappaWSGIMiddleware(simple_app)

        # Call with empty WSGI Environment
        resp = app(dict(), self._start_response)

        # Ensure the encoded zappa cookie is set
        self.assertEqual(self.headers[0][0], 'Set-Cookie')
        zappa_cookie = self.headers[0][1]
        self.assertTrue(zappa_cookie.startswith('zappa='))

        # Reads the hopefully decoded cookies
        def simple_app(environ, start_response):
            status = '200 OK'
            response_headers = []
            start_response(status, response_headers)
            return [environ['HTTP_COOKIE']]

        # Wrap the app with the middleware
        app = ZappaWSGIMiddleware(simple_app)

        # Call the app with the encoded cookie in the environment
        resp = app({'HTTP_COOKIE': zappa_cookie}, self._start_response)

        # Assert that the simple_app, received the decoded cookies
        excpected = {'foo': '123', 'bar': '456', 'baz': '789'}
        received = parse_cookie(''.join(resp))
        self.assertDictEqual(received, excpected)

    def test_wsgi_middleware_cookieoverwrite(self):
        """ This method do:
            * Sets a bunch of cookies.
            * Fetches the zappa cookie from the response
            * Overwrites only some of the cookies.
            * Fetches the zappa cookie from the response
            * Reads the cookie
        """
        # Setting the cookies
        def set_cookies(environ, start_response):
            status = '200 OK'
            response_headers = [('Set-Cookie', 'foo=123'),
                                ('Set-Cookie', 'bar=456'),
                                ('Set-Cookie', 'baz=789; Expires=Wed, 09-Jun-2001 10:18:14 GMT;')]
            start_response(status, response_headers)
            return ['Set cookies!']

        # Wrap the app with the middleware
        app = ZappaWSGIMiddleware(set_cookies)

        # Call with empty WSGI Environment
        resp = app(dict(), self._start_response)

        # Retrieve the cookie
        zappa_cookie = self.headers[0][1]

        def change_cookies(environ, start_response):
            status = '200 OK'
            response_headers = [('Set-Cookie', 'foo=sdf'),
                                ('Set-Cookie', 'baz=jkl')]
            start_response(status, response_headers)
            return ['Set cookies!']

        # Wrap the app with the middleware
        app = ZappaWSGIMiddleware(change_cookies)

        # Call the app with the encoded cookie in the environment
        resp = app({'HTTP_COOKIE': zappa_cookie}, self._start_response)

        # Retrieve the cookie
        zappa_cookie = self.headers[0][1]

        # Reads the hopefully decoded cookies
        def read_cookies(environ, start_response):
            status = '200 OK'
            response_headers = []
            start_response(status, response_headers)
            return [environ['HTTP_COOKIE']]

        # Wrap the app with the middleware
        app = ZappaWSGIMiddleware(read_cookies)

        # Call the app with the encoded cookie in the environment
        resp = app({'HTTP_COOKIE': zappa_cookie}, self._start_response)

        # Assert that read_cookies received the corrected decoded cookies
        excpected = {'foo': 'sdf', 'bar': '456', 'baz': 'jkl'}
        received = parse_cookie(''.join(resp))

        self.assertDictEqual(received, excpected)

        # Call the app with the encoded cookie in the environment
        resp = app({'HTTP_COOKIE': zappa_cookie}, self._start_response)
        received = parse_cookie(''.join(resp))
        self.assertDictEqual(received, excpected)

    def test_wsgi_middleware_redirect(self):
        url = 'http://bogus.com/target'
        body = 'Moved. Click <a href="' + url + '">here</a>!'

        # 301
        def simple_app(environ, start_response):
            status = '301 Moved Permanently'
            response_headers = [('Location', url),
                                ('Set-Cookie', 'foo=456'),
                                ('Content-Type', 'text/html; charset blahblah')]
            start_response(status, response_headers)
            return [body]

        # Wrap the app with the middleware
        app = ZappaWSGIMiddleware(simple_app)

        # Call with empty WSGI Environment
        resp = app(dict(), self._start_response)

        self.assertEqual(self.status[0], '301 Moved Permanently')
        self.assertNotEqual(self.status[0], '200 OK')

        # Assert there is only one zappa cookie
        self.assertEqual(len(self.headers), 3)

        self.assertEqual(self.headers[0][0], 'Location')
        self.assertEqual(self.headers[0][1], url)

        self.assertEqual(self.headers[2][0], 'Set-Cookie')
        self.assertTrue(self.headers[2][1].startswith('zappa='))

        # Same as above but with 302f
        def simple_app(environ, start_response):
            status = '302 Found'
            response_headers = [('Derp', 'Max-Squirt'),
                                ('Location', url),
                                ('Set-Cookie', 'foo=456')]
            start_response(status, response_headers)
            return [body]

        # Wrap the app with the middleware
        app = ZappaWSGIMiddleware(simple_app)

        # Call with empty WSGI Environment
        resp = app(dict(), self._start_response)

        self.assertEqual(self.status[0], '302 Found')
        #self.assertEqual(self.status[0], '200 OK')
        self.assertEqual(len(self.headers), 3)

        self.assertEqual(self.headers[1][0], 'Location')
        self.assertEqual(self.headers[1][1], url)

        self.assertEqual(self.headers[2][0], 'Set-Cookie')
        self.assertTrue(self.headers[2][1].startswith('zappa='))

        self.assertEqual(''.join(resp), body)

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

    def test_wsgi_middleware_expiry(self):
        # Setting the cookies
        def simple_app(environ, start_response):
            status = '200 OK'
            response_headers = [('Set-Cookie', 'boss=hogg; Expires=Wed, 09-Jun-2021 10:18:14 GMT;'),
                                ('Set-Cookie', 'spank=stank; Expires=Wed, 09-Jun-2010 10:18:14 GMT;'),
                                ('Set-Cookie', 'out=lawz; Expires=Wed, 09-Jun-2001 10:18:14 GMT;')]
            start_response(status, response_headers)
            return ['Stale cookies!']

        # Wrap the app with the middleware
        app = ZappaWSGIMiddleware(simple_app)

        # Call with empty WSGI Environment
        resp = app(dict(), self._start_response)

        # Ensure the encoded zappa cookie is set
        self.assertEqual(self.headers[0][0], 'Set-Cookie')
        zappa_cookie = self.headers[0][1]
        self.assertTrue(zappa_cookie.startswith('zappa='))

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

class TestWSGIMiddleWare(unittest.TestCase):
    """ These tests call the app as it is called in a handler, and can only
        access the returned status, body, and headers.
    """
    def test_wsgi_middleware_realcall(self):
        print("1: Setting the cookies.")
        event = {u'body': None, u'resource': u'/{proxy+}', u'requestContext': {u'resourceId': u'dg451y', u'apiId': u'79gqbxq31c', u'resourcePath': u'/{proxy+}', u'httpMethod': u'GET', u'requestId': u'766df67f-8991-11e6-b2c4-d120fedb94e5', u'accountId': u'724336686645', u'identity': {u'apiKey': None, u'userArn': None, u'cognitoAuthenticationType': None, u'caller': None, u'userAgent': u'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:49.0) Gecko/20100101 Firefox/49.0', u'user': None, u'cognitoIdentityPoolId': None, u'cognitoIdentityId': None, u'cognitoAuthenticationProvider': None, u'sourceIp': u'96.90.37.59', u'accountId': None}, u'stage': u'devorr'}, u'queryStringParameters': None, u'httpMethod': u'GET', u'pathParameters': {u'proxy': u'asdf1/asdf2'}, u'headers': {u'Via': u'1.1 b2aeb492548a8a2d4036401355f928dd.cloudfront.net (CloudFront)', u'Accept-Language': u'en-US,en;q=0.5', u'Accept-Encoding': u'gzip, deflate, br', u'X-Forwarded-Port': u'443', u'X-Forwarded-For': u'96.90.37.59, 54.240.144.50', u'CloudFront-Viewer-Country': u'US', u'Accept': u'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', u'Upgrade-Insecure-Requests': u'1', u'Host': u'79gqbxq31c.execute-api.us-east-1.amazonaws.com', u'X-Forwarded-Proto': u'https', u'X-Amz-Cf-Id': u'BBFP-RhGDrQGOzoCqjnfB2I_YzWt_dac9S5vBcSAEaoM4NfYhAQy7Q==', u'User-Agent': u'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:49.0) Gecko/20100101 Firefox/49.0', u'CloudFront-Forwarded-Proto': u'https'}, u'stageVariables': None, u'path': u'/asdf1/asdf2'}

        def set_cookies(environ, start_response):
            status = '200 OK'
            print environ
            response_headers = [('Set-Cookie', 'foo=123'),
                                ('Set-Cookie', 'bar=456'),
                                ('Set-Cookie', 'baz=789')]
            start_response(status, response_headers)
            return ['Set cookies!']

        app = ZappaWSGIMiddleware(set_cookies)

        environ = create_wsgi_request(event, script_name='http://zappa.com/',
                                      trailing_slash=False)

        response = Response.from_app(app, environ)

        # Filter the headers for Set-Cookie header
        zappa_cookie = [x[1] for x in response.headers if x[0] == 'Set-Cookie']
        self.assertEqual(len(zappa_cookie), 1)
        zappa_cookie0 = zappa_cookie[0]
        self.assertTrue(zappa_cookie0.startswith('zappa='))

        print("2: Changing 1 cookie")
        # event = {
        #     u'httpMethod': u'POST',
        #     u'params': {u'parameter_1': u'set_cookie'},
        #     u'body': u'foo=qwe',
        #     u'headers': {
        #         u'Cookie': zappa_cookie0
        #     },
        #     u'query': {}
        # }

        event = {
            u'body': u'LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS03Njk1MjI4NDg0Njc4MTc2NTgwNjMwOTYxDQpDb250ZW50LURpc3Bvc2l0aW9uOiBmb3JtLWRhdGE7IG5hbWU9Im15c3RyaW5nIg0KDQpkZGQNCi0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tNzY5NTIyODQ4NDY3ODE3NjU4MDYzMDk2MS0tDQo=',
            u'resource': u'/',
            u'requestContext': {
                u'resourceId': u'6cqjw9qu0b',
                u'apiId': u'9itr2lba55',
                u'resourcePath': u'/',
                u'httpMethod': u'POST',
                u'requestId': u'c17cb1bf-867c-11e6-b938-ed697406e3b5',
                u'accountId': u'724336686645',
                u'identity': {
                    u'apiKey': None,
                    u'userArn': None,
                    u'cognitoAuthenticationType': None,
                    u'caller': None,
                    u'userAgent': u'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:48.0) Gecko/20100101 Firefox/48.0',
                    u'user': None,
                    u'cognitoIdentityPoolId': None,
                    u'cognitoIdentityId': None,
                    u'cognitoAuthenticationProvider': None,
                    u'sourceIp': u'50.191.225.98',
                    u'accountId': None,
                    },
                u'stage': u'devorr',
                },
            u'queryStringParameters': None,
            u'httpMethod': u'POST',
            u'pathParameters': None,
            u'headers': {u'Content-Type': u'multipart/form-data; boundary=---------------------------7695228484678176580630961', u'Via': u'1.1 38205a04d96d60185e88658d3185ccee.cloudfront.net (CloudFront)', u'Accept-Language': u'en-US,en;q=0.5', u'Accept-Encoding': u'gzip, deflate, br', u'CloudFront-Is-SmartTV-Viewer': u'false', u'CloudFront-Forwarded-Proto': u'https', u'X-Forwarded-For': u'71.231.27.57, 104.246.180.51', u'CloudFront-Viewer-Country': u'US', u'Accept': u'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', u'User-Agent': u'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:45.0) Gecko/20100101 Firefox/45.0', u'Host': u'xo2z7zafjh.execute-api.us-east-1.amazonaws.com', u'X-Forwarded-Proto': u'https', u'Cookie': zappa_cookie0, u'CloudFront-Is-Tablet-Viewer': u'false', u'X-Forwarded-Port': u'443', u'Referer': u'https://xo8z7zafjh.execute-api.us-east-1.amazonaws.com/former/post', u'CloudFront-Is-Mobile-Viewer': u'false', u'X-Amz-Cf-Id': u'31zxcUcVyUxBOMk320yh5NOhihn5knqrlYQYpGGyOngKKwJb0J0BAQ==', u'CloudFront-Is-Desktop-Viewer': u'true'},
            u'stageVariables': None,
            u'path': u'/',
            }

        environ = create_wsgi_request(event, script_name='http://zappa.com/',
                                      trailing_slash=False)

        def change_cookie(environ, start_response):
            status = '200 OK'
            print 'environ', environ
            response_headers = [('Set-Cookie', 'foo=new_value')]
            start_response(status, response_headers)
            return ['Set cookies!']

        app = ZappaWSGIMiddleware(change_cookie)

        response = Response.from_app(app, environ)

        # Filter the headers for Set-Cookie header
        zappa_cookie = [x[1] for x in response.headers if x[0] == 'Set-Cookie']
        self.assertEqual(len(zappa_cookie), 1)
        zappa_cookie1 = zappa_cookie[0]
        self.assertTrue(zappa_cookie1.startswith('zappa='))
        zdict = parse_cookie(zappa_cookie1)
        print 'zdict', zdict
        zdict2 = json.loads(base58.b58decode(zdict['zappa']))
        print 'zdict2', zdict2
        self.assertEqual(len(zdict2), 3)
        self.assertEqual(zdict2['foo'], 'new_value')
        self.assertEqual(zdict2['bar'], '456')
        self.assertEqual(zdict2['baz'], '789')

        # We have changed foo, so they should be different
        self.assertNotEqual(zappa_cookie0, zappa_cookie1)

        print("3: Reading the cookies")
        event['headers']['Cookie'] = zappa_cookie1

        def read_cookies(environ, start_response):
            status = '200 OK'
            print 'environ', environ
            response_headers = []
            start_response(status, response_headers)
            return [environ['HTTP_COOKIE']]

        app = ZappaWSGIMiddleware(read_cookies)

        environ = create_wsgi_request(event, script_name='http://zappa.com/',
                                      trailing_slash=False)

        response = Response.from_app(app, environ)
        print "response", response
        # Filter the headers for Set-Cookie header
        zappa_cookie = [x[1] for x in response.headers if x[0] == 'Set-Cookie']
        self.assertEqual(len(zappa_cookie), 1)
        zappa_cookie1 = zappa_cookie[0]
        self.assertTrue(zappa_cookie1.startswith('zappa='))
        zdict = parse_cookie(zappa_cookie1)
        print 'zdict', zdict
        cookies = json.loads(base58.b58decode(zdict['zappa']))
        self.assertEqual(cookies['foo'], 'new_value')
        self.assertEqual(cookies['bar'], '456')
        self.assertEqual(cookies['baz'], '789')

