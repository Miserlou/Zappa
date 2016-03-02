# -*- coding: utf8 -*-
import collections
import json
import os
import unittest
import mock

from werkzeug.wrappers import Response

from .utils import placebo_session

from zappa.wsgi import create_wsgi_request, common_log
from zappa.zappa import Zappa, ASSUME_POLICY, ATTACH_POLICY
from zappa.middleware import ZappaWSGIMiddleware


class TestZappa(unittest.TestCase):
    ##
    # Sanity Tests
    ##

    def test_test(self):
        self.assertTrue(True)
    ##
    # Basic Tests
    ##

    def test_zappa(self):
        self.assertTrue(True)
        Zappa()

    def test_create_lambda_package(self):
        self.assertTrue(True)
        z = Zappa()
        path = z.create_lambda_zip()
        self.assertTrue(os.path.isfile(path))
        os.remove(path)

    def test_load_credentials(self):
        z = Zappa()
        z.aws_region = 'us-east-1'
        z.load_credentials()
        self.assertEqual(z.boto_session.region_name, 'us-east-1')
        self.assertEqual(z.aws_region, 'us-east-1')

        z.aws_region = 'eu-west-1'
        z.load_credentials()
        self.assertEqual(z.boto_session.region_name, 'eu-west-1')
        self.assertEqual(z.aws_region, 'eu-west-1')

        creds = {
            'AWS_ACCESS_KEY_ID': 'AK123',
            'AWS_SECRET_ACCESS_KEY': 'JKL456',
            'AWS_DEFAULT_REGION': 'us-west-1'
        }
        with mock.patch.dict('os.environ', creds):
            z.aws_region = None
            z.load_credentials()
            loaded_creds = z.boto_session._session.get_credentials()

        self.assertEqual(loaded_creds.access_key, 'AK123')
        self.assertEqual(loaded_creds.secret_key, 'JKL456')
        self.assertEqual(z.boto_session.region_name, 'us-west-1')

    @placebo_session
    def test_upload_remove_s3(self, session):
        bucket_name = 'test_zappa_upload_s3'
        z = Zappa(session)
        zip_path = z.create_lambda_zip()
        res = z.upload_to_s3(zip_path, bucket_name)
        os.remove(zip_path)
        self.assertTrue(res)
        s3 = session.resource('s3')

        # will throw ClientError with 404 if bucket doesn't exist
        s3.meta.client.head_bucket(Bucket=bucket_name)

        # will throw ClientError with 404 if object doesn't exist
        s3.meta.client.head_object(
            Bucket=bucket_name,
            Key=zip_path,
        )
        res = z.remove_from_s3(zip_path, bucket_name)
        self.assertTrue(res)

    @placebo_session
    def test_create_iam_roles(self, session):
        z = Zappa(session)
        arn = z.create_iam_roles()
        self.assertEqual(arn, "arn:aws:iam::123:role/{}".format(z.role_name))

    @placebo_session
    def test_create_api_gateway_routes(self, session):
        z = Zappa(session)
        z.parameter_depth = 1
        z.integration_response_codes = [200]
        z.method_response_codes = [200]
        z.http_methods = ['GET']
        z.credentials_arn = 'arn:aws:iam::12345:role/ZappaLambdaExecution'
        lambda_arn = 'arn:aws:lambda:us-east-1:12345:function:helloworld'
        with mock.patch('time.time', return_value=123.456):
            api_id = z.create_api_gateway_routes(lambda_arn)
        self.assertEqual(api_id, 'j27idab94h')

    def test_policy_json(self):
        # ensure the policy docs are valid JSON
        json.loads(ASSUME_POLICY)
        json.loads(ATTACH_POLICY)

    ##
    # Logging
    ##

    def test_logging(self):
        """
        TODO
        """
        Zappa()

    ##
    # WSGI
    ##

    def test_wsgi_event(self):

        event = {
            "body": {},
            "headers": {
                "Via": "1.1 e604e934e9195aaf3e36195adbcb3e18.cloudfront.net (CloudFront)",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip",
                "CloudFront-Is-SmartTV-Viewer": "false",
                "CloudFront-Forwarded-Proto": "https",
                "X-Forwarded-For": "109.81.209.118, 216.137.58.43",
                "CloudFront-Viewer-Country": "CZ",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "X-Forwarded-Proto": "https",
                "X-Amz-Cf-Id": "LZeP_TZxBgkDt56slNUr_H9CHu1Us5cqhmRSswOh1_3dEGpks5uW-g==",
                "CloudFront-Is-Tablet-Viewer": "false",
                "X-Forwarded-Port": "443",
                "CloudFront-Is-Mobile-Viewer": "false",
                "CloudFront-Is-Desktop-Viewer": "true"
            },
            "params": {
                "parameter_1": "asdf1",
                "parameter_2": "asdf2",
            },
            "method": "GET",
            "query": {
                "dead": "beef"
            }
        }
        request = create_wsgi_request(event)

    def test_wsgi_path_info(self):
        # Test no parameters (site.com/)
        event = {
            "body": {},
            "headers": {},
            "params": {},
            "method": "GET",
            "query": {}
        }

        request = create_wsgi_request(event, trailing_slash=True)
        self.assertEqual("/", request['PATH_INFO'])

        request = create_wsgi_request(event, trailing_slash=False)
        self.assertEqual("/", request['PATH_INFO'])

        # Test parameters (site.com/asdf1/asdf2 or site.com/asdf1/asdf2/)
        event = {
            "body": {},
            "headers": {},
            "params": {
                "parameter_1": "asdf1",
                "parameter_2": "asdf2",
            },
            "method": "GET",
            "query": {}
        }

        request = create_wsgi_request(event, trailing_slash=True)
        self.assertEqual("/asdf1/asdf2/", request['PATH_INFO'])

        request = create_wsgi_request(event, trailing_slash=False)
        self.assertEqual("/asdf1/asdf2", request['PATH_INFO'])

    def test_wsgi_logging(self):
        event = {
            "body": {},
            "headers": {},
            "params": {
                "parameter_1": "asdf1",
                "parameter_2": "asdf2",
            },
            "method": "GET",
            "query": {}
        }
        environ = create_wsgi_request(event, trailing_slash=False)
        response_tuple = collections.namedtuple('Response', ['status_code', 'content'])
        response = response_tuple(200, 'hello')
        le = common_log(environ, response, response_time=True)
        le = common_log(environ, response, response_time=False)


class TestWSGIMiddleWare(unittest.TestCase):

    def setUp(self):
        print "setting up"
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
                                ('Set-Cookie', 'baz=789'),
                                ('Set-Cookie', 'xyz=zappalicious')]
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
        excpected = {'foo': '123', 'bar': '456', 'baz': '789',
                     'xyz': 'zappalicious'}
        received = ''.join(resp)
        # Split the response on ';', then on '=', then convert to dict for
        # comparison
        received = dict([cookie.split('=') for cookie in received.split(';')])
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
                                ('Set-Cookie', 'baz=789'),
                                ('Set-Cookie', 'xyz=zappalicious')]
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
                                ('Set-Cookie', 'xyz=jkl')]
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
        excpected = {'foo': 'sdf', 'bar': '456', 'baz': '789',
                     'xyz': 'jkl'}
        received = ''.join(resp)
        # Split the response on ';', then on '=', then convert to dict for
        # comparison
        received = dict([cookie.split('=') for cookie in received.split(';')])
        self.assertDictEqual(received, excpected)

        # Call the app with the encoded cookie in the environment
        resp = app({'HTTP_COOKIE': zappa_cookie}, self._start_response)

        # Assert that read_cookies received the decoded cookies
        received = ''.join(resp)
        # Split the response on ';', then on '=', then convert to dict for
        # comparison
        received = dict([cookie.split('=') for cookie in received.split(';')])
        self.assertDictEqual(received, excpected)

    def test_wsgi_middleware_realcall(self):
        print("1: Setting the cookies.")
        event = {
            u'method': u'POST',
            u'params': {u'parameter_1': u'set_cookie'},
            u'body': u'foo=xxx&bar=yyy',
            u'headers': {
                # u'Cookie': u'zappa=8fFdF9whnxFRZaZbRgqvyb2wupbHuAjFLY21u5ukqvL4qCte6XJgduJU4edADwNwpZ2cwmizh7SQ4VhTuXy76KDaHVmAt4J4Pch1ZTjUHBmKmU52yoCpWYD', u'Accept': u'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                # u'Content-Type': u'application/x-www-form-urlencoded'
            },
            u'query': {}}

        def set_cookies(environ, start_response):
            status = '200 OK'
            print environ
            response_headers = [('Set-Cookie', 'foo=123'),
                                ('Set-Cookie', 'bar=456'),
                                ('Set-Cookie', 'baz=789'),
                                ('Set-Cookie', 'xyz=zappalicious')]
            start_response(status, response_headers)
            return ['Set cookies!']

        app = ZappaWSGIMiddleware(set_cookies)

        environ = create_wsgi_request(event, script_name='http://zappa.com/',
                                      trailing_slash=False)

        response = Response.from_app(app, environ)

        # for (header, value) in response.headers:
        #     print header, value

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
                # u'Content-Type': u'application/x-www-form-urlencoded'
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
        # raise Exception("stop")
        # Filter the headers for Set-Cookie header
        zappa_cookie = [x[1] for x in response.headers if x[0] == 'Set-Cookie']
        self.assertEqual(len(zappa_cookie), 1)
        zappa_cookie1 = zappa_cookie[0]
        self.assertTrue(zappa_cookie1.startswith('zappa='))

        # We have changed foo, so they should be different
        print zappa_cookie0
        print zappa_cookie1
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
        cookies = dict([x.split('=') for x in response.data.split(';')])
        self.assertEqual(cookies['foo'], 'new_value')
        print cookies

        print("4: zappa cookie")


        raise Exception("the end")


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

        self.assertEqual(self.status[0], '301 Moved Permanently')

        # Assert there is only one zappa cookie
        self.assertEqual(len(self.headers), 2)

        self.assertEqual(self.headers[0][0], 'Location')
        self.assertEqual(self.headers[0][1], url)

        self.assertEqual(self.headers[1][0], 'Set-Cookie')
        self.assertTrue(self.headers[1][1].startswith('zappa='))

        self.assertEqual(''.join(resp), body)

        # Same as above but with 302
        def simple_app(environ, start_response):
            status = '302 Found'
            response_headers = [('Location', url),
                                ('Set-Cookie', 'foo=456')]
            start_response(status, response_headers)
            return [body]

        # Wrap the app with the middleware
        app = ZappaWSGIMiddleware(simple_app)

        # Call with empty WSGI Environment
        resp = app(dict(), self._start_response)

        self.assertEqual(self.status[0], '302 Found')

        # Assert there is only one zappa cookie
        self.assertEqual(len(self.headers), 2)

        self.assertEqual(self.headers[0][0], 'Location')
        self.assertEqual(self.headers[0][1], url)

        self.assertEqual(self.headers[1][0], 'Set-Cookie')
        self.assertTrue(self.headers[1][1].startswith('zappa='))

        self.assertEqual(''.join(resp), body)

    # TODO: This test breaks in the middleware with weird unicode chars
    def test_wsgi_middleware_unicode(self):
        # Pass some unicode through the middleware
        def simple_app(environ, start_response):
            # String of weird characters
            status = '200 OK'
            response_headers = []
            start_response(status, response_headers)
            return [unicode('asåøæd', encoding='utf8')]

        # Wrap the app with the middleware
        app = ZappaWSGIMiddleware(simple_app)

        # Call with empty WSGI Environment
        _ = app(dict(), self._start_response)


if __name__ == '__main__':
    unittest.main()
