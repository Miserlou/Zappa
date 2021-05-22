# -*- coding: utf8 -*-
import sys
import unittest

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
        ugly_string = "˝ÓÔÒÚÆ☃ЗИЙКЛМФХЦЧШ차를 타고 온 펲시맨(╯°□°）╯︵ ┻━┻)"

        # Pass some unicode through the middleware body
        def simple_app(environ, start_response):
            # String of weird characters
            status = "200 OK"
            response_headers = []
            start_response(status, response_headers)
            return [ugly_string]

        # Wrap the app with the middleware
        app = ZappaWSGIMiddleware(simple_app)

        # Call with empty WSGI Environment
        resp = app(dict(), self._start_response)
        print("".join(resp))

        # Pass some unicode through the middleware headers
        def simple_app(environ, start_response):
            # String of weird characters
            status = "301 Moved Permanently"
            response_headers = [
                ("Location", f"http://zappa.com/elsewhere{ugly_string}")
            ]
            start_response(status, response_headers)
            return [ugly_string]

        # Wrap the app with the middleware
        app = ZappaWSGIMiddleware(simple_app)

        # Call with empty WSGI Environment
        resp = app(dict(), self._start_response)
        print("".join(resp))

    def test_wsgi_authorizer_handling(self):
        # With user
        event = {
            "httpMethod": "GET",
            "queryStringParameters": None,
            "path": "/v1/runs",
            "params": {},
            "body": {},
            "headers": {"Content-Type": "application/json"},
            "pathParameters": {"proxy": "v1/runs"},
            "requestContext": {"authorizer": {"principalId": "user1"}},
            "query": {},
        }

        environ = create_wsgi_request(
            event, script_name="http://zappa.com/", trailing_slash=False
        )
        self.assertEqual(environ["REMOTE_USER"], "user1")

        # With empty authorizer, should not include REMOTE_USER
        event = {
            "httpMethod": "GET",
            "queryStringParameters": None,
            "path": "/v1/runs",
            "params": {},
            "body": {},
            "headers": {"Content-Type": "application/json"},
            "pathParameters": {"proxy": "v1/runs"},
            "requestContext": {"authorizer": {"principalId": ""}},
            "query": {},
        }

        environ = create_wsgi_request(
            event, script_name="http://zappa.com/", trailing_slash=False
        )
        user = environ.get("REMOTE_USER", "no_user")
        self.assertEqual(user, "no_user")

        # With missing authorizer, should not include REMOTE_USER
        event = {
            "httpMethod": "GET",
            "queryStringParameters": None,
            "path": "/v1/runs",
            "params": {},
            "body": {},
            "headers": {"Content-Type": "application/json"},
            "pathParameters": {"proxy": "v1/runs"},
            "requestContext": {},
            "query": {},
        }

        environ = create_wsgi_request(
            event, script_name="http://zappa.com/", trailing_slash=False
        )
        user = environ.get("REMOTE_USER", "no_user")
        self.assertEqual(user, "no_user")

        # With empty authorizer, should not include REMOTE_USER
        event = {
            "httpMethod": "GET",
            "queryStringParameters": None,
            "path": "/v1/runs",
            "params": {},
            "body": {},
            "headers": {"Content-Type": "application/json"},
            "pathParameters": {"proxy": "v1/runs"},
            "requestContext": {"authorizer": {}},
            "query": {},
        }

        environ = create_wsgi_request(
            event, script_name="http://zappa.com/", trailing_slash=False
        )
        user = environ.get("REMOTE_USER", "no_user")
        self.assertEqual(user, "no_user")

    def test_wsgi_map_context_headers_handling(self):

        # Validate a single context value mapping is translated into a HTTP header
        event = {
            "httpMethod": "GET",
            "queryStringParameters": None,
            "path": "/v1/runs",
            "params": {},
            "body": {},
            "headers": {"Content-Type": "application/json"},
            "pathParameters": {"proxy": "v1/runs"},
            "requestContext": {
                "authorizer": {"principalId": "user1"},
            },
            "query": {},
        }

        environ = create_wsgi_request(
            event,
            script_name="http://zappa.com/",
            trailing_slash=False,
            context_header_mappings={"PrincipalId": "authorizer.principalId"},
        )
        self.assertEqual(environ["HTTP_PRINCIPALID"], "user1")

        # Validate multiple mappings with an invalid mapping
        # Invalid mapping should be ignored
        event = {
            "httpMethod": "GET",
            "queryStringParameters": None,
            "path": "/v1/runs",
            "params": {},
            "body": {},
            "headers": {"Content-Type": "application/json"},
            "pathParameters": {"proxy": "v1/runs"},
            "requestContext": {
                "resourceId": "123456",
                "apiId": "1234567890",
                "resourcePath": "/{proxy+}",
                "httpMethod": "POST",
                "requestId": "c6af9ac6-7b61-11e6-9a41-93e8deadbeef",
                "accountId": "123456789012",
                "identity": {
                    "userAgent": "Custom User Agent String",
                    "cognitoIdentityPoolId": "userpoolID",
                    "cognitoIdentityId": "myCognitoID",
                    "sourceIp": "127.0.0.1",
                },
                "stage": "prod",
            },
            "query": {},
        }

        environ = create_wsgi_request(
            event,
            script_name="http://zappa.com/",
            trailing_slash=False,
            context_header_mappings={
                "CognitoIdentityID": "identity.cognitoIdentityId",
                "APIStage": "stage",
                "InvalidValue": "identity.cognitoAuthenticationType",
                "OtherInvalid": "nothinghere",
            },
        )
        self.assertEqual(environ["HTTP_COGNITOIDENTITYID"], "myCognitoID")
        self.assertEqual(environ["HTTP_APISTAGE"], "prod")
        self.assertNotIn("HTTP_INVALIDVALUE", environ)
        self.assertNotIn("HTTP_OTHERINVALID", environ)

    def test_should_allow_empty_query_params(self):
        event = {
            "httpMethod": "GET",
            "queryStringParameters": {},
            "multiValueQueryStringParameters": {},
            "path": "/v1/runs",
            "params": {},
            "body": {},
            "headers": {"Content-Type": "application/json"},
            "pathParameters": {"proxy": "v1/runs"},
            "requestContext": {
                "resourceId": "123456",
                "apiId": "1234567890",
                "resourcePath": "/{proxy+}",
                "httpMethod": "POST",
                "requestId": "c6af9ac6-7b61-11e6-9a41-93e8deadbeef",
                "accountId": "123456789012",
                "identity": {
                    "userAgent": "Custom User Agent String",
                    "cognitoIdentityPoolId": "userpoolID",
                    "cognitoIdentityId": "myCognitoID",
                    "sourceIp": "127.0.0.1",
                },
                "stage": "prod",
            },
            "query": {},
        }
        environ = create_wsgi_request(
            event, script_name="http://zappa.com/", trailing_slash=False
        )
        self.assertEqual(environ["QUERY_STRING"], "")

    def test_should_handle_multi_value_query_string_params(self):
        event = {
            "httpMethod": "GET",
            "queryStringParameters": {},
            "multiValueQueryStringParameters": {"foo": [1, 2]},
            "path": "/v1/runs",
            "params": {},
            "body": {},
            "headers": {"Content-Type": "application/json"},
            "pathParameters": {"proxy": "v1/runs"},
            "requestContext": {
                "resourceId": "123456",
                "apiId": "1234567890",
                "resourcePath": "/{proxy+}",
                "httpMethod": "POST",
                "requestId": "c6af9ac6-7b61-11e6-9a41-93e8deadbeef",
                "accountId": "123456789012",
                "identity": {
                    "userAgent": "Custom User Agent String",
                    "cognitoIdentityPoolId": "userpoolID",
                    "cognitoIdentityId": "myCognitoID",
                    "sourceIp": "127.0.0.1",
                },
                "stage": "prod",
            },
            "query": {},
        }
        environ = create_wsgi_request(
            event, script_name="http://zappa.com/", trailing_slash=False
        )
        self.assertEqual(environ["QUERY_STRING"], "foo=1&foo=2")
