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
                                ('Set-Cookie', 'foo=456')]
            start_response(status, response_headers)
            return [body]

        # Wrap the app with the middleware
        app = ZappaWSGIMiddleware(simple_app)

        # Call with empty WSGI Environment
        resp = app(dict(), self._start_response)

        #self.assertEqual(self.status[0], '301 Moved Permanently')
        self.assertEqual(self.status[0], '200 OK')

        # Assert there is only one zappa cookie
        self.assertEqual(len(self.headers), 2)

        self.assertEqual(self.headers[0][0], 'Location')
        self.assertEqual(self.headers[0][1], url)

        self.assertEqual(self.headers[1][0], 'Set-Cookie')
        self.assertTrue(self.headers[1][1].startswith('zappa='))

        self.assertNotEqual(''.join(resp), body)

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

        #self.assertEqual(self.status[0], '302 Found')
        self.assertEqual(self.status[0], '200 OK')
        self.assertEqual(len(self.headers), 3)

        self.assertEqual(self.headers[1][0], 'Location')
        self.assertEqual(self.headers[1][1], url)

        self.assertEqual(self.headers[2][0], 'Set-Cookie')
        self.assertTrue(self.headers[2][1].startswith('zappa='))

        self.assertNotEqual(''.join(resp), body)

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

class TestWSGIMiddleWare(unittest.TestCase):
    """ These tests call the app as it is called in a handler, and can only
        access the returned status, body, and headers.
    """
    def test_wsgi_middleware_realcall(self):
        print("1: Setting the cookies.")
        event = {
            u'method': u'POST',
            u'params': {u'parameter_1': u'set_cookie'},
            u'body': u'foo=xxx&bar=yyy',
            u'headers': {},
            u'query': {}}

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
        event = {
            u'method': u'POST',
            u'params': {u'parameter_1': u'set_cookie'},
            u'body': u'foo=qwe',
            u'headers': {
                u'Cookie': zappa_cookie0
            },
            u'query': {}
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

