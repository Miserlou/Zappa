# -*- coding: utf8 -*-
import base64
import collections
import json
import mock
import os
import random
import string
import unittest

from lambda_packages import lambda_packages

from .utils import placebo_session

from zappa.cli import ZappaCLI, shamelessly_promote
from zappa.ext.django_zappa import get_django_wsgi
from zappa.handler import LambdaHandler, lambda_handler
from zappa.letsencrypt import get_cert_and_update_domain, create_domain_key, create_domain_csr, create_chained_certificate, get_cert, cleanup, parse_account_key, parse_csr, sign_certificate, encode_certificate, register_account, verify_challenge
from zappa.util import detect_django_settings, copytree, detect_flask_apps, add_event_source, remove_event_source, get_event_source_status
from zappa.wsgi import create_wsgi_request, common_log
from zappa.zappa import Zappa, ASSUME_POLICY, ATTACH_POLICY

def random_string(length):
    return ''.join(random.choice(string.printable) for _ in range(length))


class TestZappa(unittest.TestCase):
    def setUp(self):
        self.sleep_patch = mock.patch('time.sleep', return_value=None)
        # Tests expect us-east-1.
        # If the user has set a different region in env variables, we set it aside for now and use us-east-1
        self.users_current_region_name = os.environ.get('AWS_DEFAULT_REGION', None)
        os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
        if not os.environ.get('PLACEBO_MODE') == 'record':
            self.sleep_patch.start()

    def tearDown(self):
        if not os.environ.get('PLACEBO_MODE') == 'record':
            self.sleep_patch.stop()
        del os.environ['AWS_DEFAULT_REGION']
        if self.users_current_region_name is not None:
            # Give the user their AWS region back, we're done testing with us-east-1.
            os.environ['AWS_DEFAULT_REGION'] = self.users_current_region_name

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
        # mock the pip.get_installed_distributions() to include a package in lambda_packages so that the code
        # for zipping pre-compiled packages gets called
        mock_named_tuple = collections.namedtuple('mock_named_tuple', ['project_name'])
        mock_return_val = [mock_named_tuple(lambda_packages.keys()[0])]  # choose name of 1st package in lambda_packages
        with mock.patch('pip.get_installed_distributions', return_value=mock_return_val):
            z = Zappa()
            path = z.create_lambda_zip(handler_file=os.path.realpath(__file__))
            self.assertTrue(os.path.isfile(path))
            os.remove(path)

    def test_load_credentials(self):
        z = Zappa()
        z.aws_region = 'us-east-1'
        z.load_credentials()
        self.assertEqual(z.boto_session.region_name, 'us-east-1')
        self.assertEqual(z.aws_region, 'us-east-1')

        z.aws_region = 'eu-west-1'
        z.profile_name = 'default'
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
        zip_path = z.create_lambda_zip(minify=False)
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

        fail = z.upload_to_s3('/tmp/this_isnt_real', bucket_name)
        self.assertFalse(fail)

    @placebo_session
    def test_create_lambda_function(self, session):
        bucket_name = 'lmbda'
        zip_path = 'Spheres-dev-1454694878.zip'

        z = Zappa(session)
        z.aws_region = 'us-east-1'
        z.load_credentials(session)
        z.credentials_arn = 'arn:aws:iam::12345:role/ZappaLambdaExecution'

        arn = z.create_lambda_function(
            bucket=bucket_name,
            s3_key=zip_path,
            function_name='test_lmbda_function55',
            handler='runme.lambda_handler'
        )

        arn = z.update_lambda_function(
            bucket=bucket_name,
            s3_key=zip_path,
            function_name='test_lmbda_function55',
        )

    @placebo_session
    def test_rollback_lambda_function_version(self, session):
        z = Zappa(session)
        z.credentials_arn = 'arn:aws:iam::724336686645:role/ZappaLambdaExecution'

        function_name = 'django-helloworld-unicode'
        too_many_versions = z.rollback_lambda_function_version(function_name, 99999)
        self.assertFalse(too_many_versions)

        function_arn = z.rollback_lambda_function_version(function_name, 1)

    @placebo_session
    def test_invoke_lambda_function(self, session):
        z = Zappa(session)
        z.credentials_arn = 'arn:aws:iam::724336686645:role/ZappaLambdaExecution'

        function_name = 'django-helloworld-unicode'
        payload = '{"event": "hello"}'
        response = z.invoke_lambda_function(function_name, payload)

    @placebo_session
    def test_create_iam_roles(self, session):
        z = Zappa(session)
        arn, updated = z.create_iam_roles()
        self.assertEqual(arn, "arn:aws:iam::123:role/{}".format(z.role_name))

    def test_create_api_gateway_routes_with_different_auth_methods(self):
        z = Zappa()
        z.parameter_depth = 1
        z.integration_response_codes = [200]
        z.method_response_codes = [200]
        z.http_methods = ['GET']
        z.credentials_arn = 'arn:aws:iam::12345:role/ZappaLambdaExecution'
        lambda_arn = 'arn:aws:lambda:us-east-1:12345:function:helloworld'

        # No auth at all
        z.create_stack_template(lambda_arn, 'helloworld', False, {}, False, None)
        parsable_template = json.loads(z.cf_template.to_json())
        self.assertEqual("NONE", parsable_template["Resources"]["GET0"]["Properties"]["AuthorizationType"])
        self.assertEqual("NONE", parsable_template["Resources"]["GET1"]["Properties"]["AuthorizationType"])
        self.assertEqual(False, parsable_template["Resources"]["GET0"]["Properties"]["ApiKeyRequired"])
        self.assertEqual(False, parsable_template["Resources"]["GET1"]["Properties"]["ApiKeyRequired"])

        # IAM auth
        z.create_stack_template(lambda_arn, 'helloworld', False, {}, True, None)
        parsable_template = json.loads(z.cf_template.to_json())
        self.assertEqual("AWS_IAM", parsable_template["Resources"]["GET0"]["Properties"]["AuthorizationType"])
        self.assertEqual("AWS_IAM", parsable_template["Resources"]["GET1"]["Properties"]["AuthorizationType"])
        self.assertEqual(False, parsable_template["Resources"]["GET0"]["Properties"]["ApiKeyRequired"])
        self.assertEqual(False, parsable_template["Resources"]["GET1"]["Properties"]["ApiKeyRequired"])

        # API Key auth
        z.create_stack_template(lambda_arn, 'helloworld', True, {}, True, None)
        parsable_template = json.loads(z.cf_template.to_json())
        self.assertEqual("AWS_IAM", parsable_template["Resources"]["GET0"]["Properties"]["AuthorizationType"])
        self.assertEqual("AWS_IAM", parsable_template["Resources"]["GET1"]["Properties"]["AuthorizationType"])
        self.assertEqual(True, parsable_template["Resources"]["GET0"]["Properties"]["ApiKeyRequired"])
        self.assertEqual(True, parsable_template["Resources"]["GET1"]["Properties"]["ApiKeyRequired"])

        # Authorizer and IAM
        authorizer = {
            "function": "runapi.authorization.gateway_authorizer.evaluate_token",
            "result_ttl": 300,
            "token_header": "Authorization",
            "validation_expression": "xxx"
        }
        z.create_stack_template(lambda_arn, 'helloworld', False, {}, True, authorizer)
        parsable_template = json.loads(z.cf_template.to_json())
        self.assertEqual("AWS_IAM", parsable_template["Resources"]["GET0"]["Properties"]["AuthorizationType"])
        self.assertEqual("AWS_IAM", parsable_template["Resources"]["GET1"]["Properties"]["AuthorizationType"])
        with self.assertRaises(KeyError):
            parsable_template["Resources"]["Authorizer"]

        # Authorizer with validation expression
        invocations_uri = 'arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/' + lambda_arn + '/invocations'
        z.create_stack_template(lambda_arn, 'helloworld', False, {}, False, authorizer)
        parsable_template = json.loads(z.cf_template.to_json())
        self.assertEqual("CUSTOM", parsable_template["Resources"]["GET0"]["Properties"]["AuthorizationType"])
        self.assertEqual("CUSTOM", parsable_template["Resources"]["GET1"]["Properties"]["AuthorizationType"])
        self.assertEqual("TOKEN", parsable_template["Resources"]["Authorizer"]["Properties"]["Type"])
        self.assertEqual("ZappaAuthorizer", parsable_template["Resources"]["Authorizer"]["Properties"]["Name"])
        self.assertEqual(300, parsable_template["Resources"]["Authorizer"]["Properties"]["AuthorizerResultTtlInSeconds"])
        self.assertEqual(invocations_uri, parsable_template["Resources"]["Authorizer"]["Properties"]["AuthorizerUri"])
        self.assertEqual(z.credentials_arn, parsable_template["Resources"]["Authorizer"]["Properties"]["AuthorizerCredentials"])
        self.assertEqual("xxx", parsable_template["Resources"]["Authorizer"]["Properties"]["IdentityValidationExpression"])

        # Authorizer without validation expression
        authorizer.pop('validation_expression', None)
        z.create_stack_template(lambda_arn, 'helloworld', False, {}, False, authorizer)
        parsable_template = json.loads(z.cf_template.to_json())
        self.assertEqual("CUSTOM", parsable_template["Resources"]["GET0"]["Properties"]["AuthorizationType"])
        self.assertEqual("CUSTOM", parsable_template["Resources"]["GET1"]["Properties"]["AuthorizationType"])
        self.assertEqual("TOKEN", parsable_template["Resources"]["Authorizer"]["Properties"]["Type"])
        with self.assertRaises(KeyError):
            parsable_template["Resources"]["Authorizer"]["Properties"]["IdentityValidationExpression"]

        # Authorizer with arn
        authorizer = {
            "arn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
        }
        z.create_stack_template(lambda_arn, 'helloworld', False, {}, False, authorizer)
        parsable_template = json.loads(z.cf_template.to_json())
        self.assertEqual('arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1:123456789012:function:my-function/invocations', parsable_template["Resources"]["Authorizer"]["Properties"]["AuthorizerUri"])


    @placebo_session
    def test_get_api_url(self, session):
        z = Zappa(session)
        z.credentials_arn = 'arn:aws:iam::724336686645:role/ZappaLambdaExecution'
        url = z.get_api_url('Spheres-demonstration', 'demonstration')

    @placebo_session
    def test_fetch_logs(self, session):
        z = Zappa(session)
        z.credentials_arn = 'arn:aws:iam::12345:role/ZappaLambdaExecution'
        events = z.fetch_logs('Spheres-demonstration')
        self.assertTrue(events is not None)

    def test_policy_json(self):
        # ensure the policy docs are valid JSON
        json.loads(ASSUME_POLICY)
        json.loads(ATTACH_POLICY)

    def test_schedule_events(self):
        z = Zappa()
        path = os.getcwd()
      # z.schedule_events # TODO

    ##
    # Logging
    ##

    def test_logging(self):
        """
        TODO
        """
        Zappa()

    ##
    # Mapping and pattern tests
    ##

    def test_redirect_pattern(self):
        test_urls = [
            # a regular endpoint url
            'https://asdf1234.execute-api.us-east-1.amazonaws.com/env/path/to/thing',
            # an external url (outside AWS)
            'https://github.com/Miserlou/zappa/issues?q=is%3Aissue+is%3Aclosed',
            # a local url
            '/env/path/to/thing'
        ]

        for code in ['301', '302']:
            pattern = Zappa.selection_pattern(code)

            for url in test_urls:
                self.assertRegexpMatches(url, pattern)

    def test_b64_pattern(self):
        head = '\{"http_status": '

        for code in ['400', '401', '402', '403', '404', '500']:
            pattern = Zappa.selection_pattern(code)

            document = head + code + random_string(50)
            self.assertRegexpMatches(document, pattern)

            for bad_code in ['200', '301', '302']:
                document = base64.b64encode(head + bad_code + random_string(50))
                self.assertNotRegexpMatches(document, pattern)

    def test_200_pattern(self):
        pattern = Zappa.selection_pattern('200')
        self.assertEqual(pattern, '')

    ##
    # WSGI
    ##

    def test_wsgi_event(self):

        ## This is a pre-proxy+ event
        # event = {
        #     "body": "",
        #     "headers": {
        #         "Via": "1.1 e604e934e9195aaf3e36195adbcb3e18.cloudfront.net (CloudFront)",
        #         "Accept-Language": "en-US,en;q=0.5",
        #         "Accept-Encoding": "gzip",
        #         "CloudFront-Is-SmartTV-Viewer": "false",
        #         "CloudFront-Forwarded-Proto": "https",
        #         "X-Forwarded-For": "109.81.209.118, 216.137.58.43",
        #         "CloudFront-Viewer-Country": "CZ",
        #         "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        #         "X-Forwarded-Proto": "https",
        #         "X-Amz-Cf-Id": "LZeP_TZxBgkDt56slNUr_H9CHu1Us5cqhmRSswOh1_3dEGpks5uW-g==",
        #         "CloudFront-Is-Tablet-Viewer": "false",
        #         "X-Forwarded-Port": "443",
        #         "CloudFront-Is-Mobile-Viewer": "false",
        #         "CloudFront-Is-Desktop-Viewer": "true",
        #         "Content-Type": "application/json"
        #     },
        #     "params": {
        #         "parameter_1": "asdf1",
        #         "parameter_2": "asdf2",
        #     },
        #     "method": "POST",
        #     "query": {
        #         "dead": "beef"
        #     }
        # }

        event = {
            u'body': None,
            u'resource': u'/',
            u'requestContext': {
                u'resourceId': u'6cqjw9qu0b',
                u'apiId': u'9itr2lba55',
                u'resourcePath': u'/',
                u'httpMethod': u'GET',
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
            u'httpMethod': u'GET',
            u'pathParameters': None,
            u'headers': {
                u'Via': u'1.1 6801928d54163af944bf854db8d5520e.cloudfront.net (CloudFront)',
                u'Accept-Language': u'en-US,en;q=0.5',
                u'Accept-Encoding': u'gzip, deflate, br',
                u'CloudFront-Is-SmartTV-Viewer': u'false',
                u'CloudFront-Forwarded-Proto': u'https',
                u'X-Forwarded-For': u'50.191.225.98, 204.246.168.101',
                u'CloudFront-Viewer-Country': u'US',
                u'Accept': u'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                u'Upgrade-Insecure-Requests': u'1',
                u'Host': u'9itr2lba55.execute-api.us-east-1.amazonaws.com',
                u'X-Forwarded-Proto': u'https',
                u'X-Amz-Cf-Id': u'qgNdqKT0_3RMttu5KjUdnvHI3OKm1BWF8mGD2lX8_rVrJQhhp-MLDw==',
                u'CloudFront-Is-Tablet-Viewer': u'false',
                u'X-Forwarded-Port': u'443',
                u'User-Agent': u'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:48.0) Gecko/20100101 Firefox/48.0',
                u'CloudFront-Is-Mobile-Viewer': u'false',
                u'CloudFront-Is-Desktop-Viewer': u'true',
                },
            u'stageVariables': None,
            u'path': u'/',
            }

        request = create_wsgi_request(event)

    # def test_wsgi_path_info(self):
    #     # Test no parameters (site.com/)
    #     event = {
    #         "body": {},
    #         "headers": {},
    #         "pathParameters": {},
    #         "path": u'/',
    #         "httpMethod": "GET",
    #         "queryStringParameters": {}
    #     }

    #     request = create_wsgi_request(event, trailing_slash=True)
    #     self.assertEqual("/", request['PATH_INFO'])

    #     request = create_wsgi_request(event, trailing_slash=False)
    #     self.assertEqual("/", request['PATH_INFO'])

    #     # Test parameters (site.com/asdf1/asdf2 or site.com/asdf1/asdf2/)
    #     event_asdf2 = {u'body': None, u'resource': u'/{proxy+}', u'requestContext': {u'resourceId': u'dg451y', u'apiId': u'79gqbxq31c', u'resourcePath': u'/{proxy+}', u'httpMethod': u'GET', u'requestId': u'766df67f-8991-11e6-b2c4-d120fedb94e5', u'accountId': u'724336686645', u'identity': {u'apiKey': None, u'userArn': None, u'cognitoAuthenticationType': None, u'caller': None, u'userAgent': u'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:49.0) Gecko/20100101 Firefox/49.0', u'user': None, u'cognitoIdentityPoolId': None, u'cognitoIdentityId': None, u'cognitoAuthenticationProvider': None, u'sourceIp': u'96.90.37.59', u'accountId': None}, u'stage': u'devorr'}, u'queryStringParameters': None, u'httpMethod': u'GET', u'pathParameters': {u'proxy': u'asdf1/asdf2'}, u'headers': {u'Via': u'1.1 b2aeb492548a8a2d4036401355f928dd.cloudfront.net (CloudFront)', u'Accept-Language': u'en-US,en;q=0.5', u'Accept-Encoding': u'gzip, deflate, br', u'X-Forwarded-Port': u'443', u'X-Forwarded-For': u'96.90.37.59, 54.240.144.50', u'CloudFront-Viewer-Country': u'US', u'Accept': u'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', u'Upgrade-Insecure-Requests': u'1', u'Host': u'79gqbxq31c.execute-api.us-east-1.amazonaws.com', u'X-Forwarded-Proto': u'https', u'X-Amz-Cf-Id': u'BBFP-RhGDrQGOzoCqjnfB2I_YzWt_dac9S5vBcSAEaoM4NfYhAQy7Q==', u'User-Agent': u'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:49.0) Gecko/20100101 Firefox/49.0', u'CloudFront-Forwarded-Proto': u'https'}, u'stageVariables': None, u'path': u'/asdf1/asdf2'}
    #     event_asdf2_slash = {u'body': None, u'resource': u'/{proxy+}', u'requestContext': {u'resourceId': u'dg451y', u'apiId': u'79gqbxq31c', u'resourcePath': u'/{proxy+}', u'httpMethod': u'GET', u'requestId': u'd6fda925-8991-11e6-8bd8-b5ec6db19d57', u'accountId': u'724336686645', u'identity': {u'apiKey': None, u'userArn': None, u'cognitoAuthenticationType': None, u'caller': None, u'userAgent': u'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:49.0) Gecko/20100101 Firefox/49.0', u'user': None, u'cognitoIdentityPoolId': None, u'cognitoIdentityId': None, u'cognitoAuthenticationProvider': None, u'sourceIp': u'96.90.37.59', u'accountId': None}, u'stage': u'devorr'}, u'queryStringParameters': None, u'httpMethod': u'GET', u'pathParameters': {u'proxy': u'asdf1/asdf2'}, u'headers': {u'Via': u'1.1 c70173a50d0076c99b5e680eb32d40bb.cloudfront.net (CloudFront)', u'Accept-Language': u'en-US,en;q=0.5', u'Accept-Encoding': u'gzip, deflate, br', u'X-Forwarded-Port': u'443', u'X-Forwarded-For': u'96.90.37.59, 54.240.144.53', u'CloudFront-Viewer-Country': u'US', u'Accept': u'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', u'Upgrade-Insecure-Requests': u'1', u'Host': u'79gqbxq31c.execute-api.us-east-1.amazonaws.com', u'X-Forwarded-Proto': u'https', u'Cookie': u'zappa=AQ4', u'X-Amz-Cf-Id': u'aU_i-iuT3llVUfXv2zv6uU-m77Oga7ANhd5ZYrCoqXBy4K7I2x3FZQ==', u'User-Agent': u'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:49.0) Gecko/20100101 Firefox/49.0', u'CloudFront-Forwarded-Proto': u'https'}, u'stageVariables': None, u'path': u'/asdf1/asdf2/'}

    #     request = create_wsgi_request(event, trailing_slash=True)
    #     self.assertEqual("/asdf1/asdf2/", request['PATH_INFO'])

    #     request = create_wsgi_request(event, trailing_slash=False)
    #     self.assertEqual("/asdf1/asdf2", request['PATH_INFO'])

    #     request = create_wsgi_request(event, trailing_slash=False, script_name='asdf1')
    #     self.assertEqual("/asdf1/asdf2", request['PATH_INFO'])

    def test_wsgi_logging(self):
        # event = {
        #     "body": {},
        #     "headers": {},
        #     "params": {
        #         "parameter_1": "asdf1",
        #         "parameter_2": "asdf2",
        #     },
        #     "httpMethod": "GET",
        #     "query": {}
        # }

        event = {u'body': None, u'resource': u'/{proxy+}', u'requestContext': {u'resourceId': u'dg451y', u'apiId': u'79gqbxq31c', u'resourcePath': u'/{proxy+}', u'httpMethod': u'GET', u'requestId': u'766df67f-8991-11e6-b2c4-d120fedb94e5', u'accountId': u'724336686645', u'identity': {u'apiKey': None, u'userArn': None, u'cognitoAuthenticationType': None, u'caller': None, u'userAgent': u'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:49.0) Gecko/20100101 Firefox/49.0', u'user': None, u'cognitoIdentityPoolId': None, u'cognitoIdentityId': None, u'cognitoAuthenticationProvider': None, u'sourceIp': u'96.90.37.59', u'accountId': None}, u'stage': u'devorr'}, u'queryStringParameters': None, u'httpMethod': u'GET', u'pathParameters': {u'proxy': u'asdf1/asdf2'}, u'headers': {u'Via': u'1.1 b2aeb492548a8a2d4036401355f928dd.cloudfront.net (CloudFront)', u'Accept-Language': u'en-US,en;q=0.5', u'Accept-Encoding': u'gzip, deflate, br', u'X-Forwarded-Port': u'443', u'X-Forwarded-For': u'96.90.37.59, 54.240.144.50', u'CloudFront-Viewer-Country': u'US', u'Accept': u'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', u'Upgrade-Insecure-Requests': u'1', u'Host': u'79gqbxq31c.execute-api.us-east-1.amazonaws.com', u'X-Forwarded-Proto': u'https', u'X-Amz-Cf-Id': u'BBFP-RhGDrQGOzoCqjnfB2I_YzWt_dac9S5vBcSAEaoM4NfYhAQy7Q==', u'User-Agent': u'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:49.0) Gecko/20100101 Firefox/49.0', u'CloudFront-Forwarded-Proto': u'https'}, u'stageVariables': None, u'path': u'/asdf1/asdf2'}

        environ = create_wsgi_request(event, trailing_slash=False)
        response_tuple = collections.namedtuple('Response', ['status_code', 'content'])
        response = response_tuple(200, 'hello')
        le = common_log(environ, response, response_time=True)
        le = common_log(environ, response, response_time=False)

    def test_wsgi_multipart(self):
        #event = {u'body': u'LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS03Njk1MjI4NDg0Njc4MTc2NTgwNjMwOTYxDQpDb250ZW50LURpc3Bvc2l0aW9uOiBmb3JtLWRhdGE7IG5hbWU9Im15c3RyaW5nIg0KDQpkZGQNCi0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tNzY5NTIyODQ4NDY3ODE3NjU4MDYzMDk2MS0tDQo=', u'headers': {u'Content-Type': u'multipart/form-data; boundary=---------------------------7695228484678176580630961', u'Via': u'1.1 38205a04d96d60185e88658d3185ccee.cloudfront.net (CloudFront)', u'Accept-Language': u'en-US,en;q=0.5', u'Accept-Encoding': u'gzip, deflate, br', u'CloudFront-Is-SmartTV-Viewer': u'false', u'CloudFront-Forwarded-Proto': u'https', u'X-Forwarded-For': u'71.231.27.57, 104.246.180.51', u'CloudFront-Viewer-Country': u'US', u'Accept': u'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', u'User-Agent': u'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:45.0) Gecko/20100101 Firefox/45.0', u'Host': u'xo2z7zafjh.execute-api.us-east-1.amazonaws.com', u'X-Forwarded-Proto': u'https', u'Cookie': u'zappa=AQ4', u'CloudFront-Is-Tablet-Viewer': u'false', u'X-Forwarded-Port': u'443', u'Referer': u'https://xo8z7zafjh.execute-api.us-east-1.amazonaws.com/former/post', u'CloudFront-Is-Mobile-Viewer': u'false', u'X-Amz-Cf-Id': u'31zxcUcVyUxBOMk320yh5NOhihn5knqrlYQYpGGyOngKKwJb0J0BAQ==', u'CloudFront-Is-Desktop-Viewer': u'true'}, u'params': {u'parameter_1': u'post'}, u'method': u'POST', u'query': {}}

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
            u'headers': {u'Content-Type': u'multipart/form-data; boundary=---------------------------7695228484678176580630961', u'Via': u'1.1 38205a04d96d60185e88658d3185ccee.cloudfront.net (CloudFront)', u'Accept-Language': u'en-US,en;q=0.5', u'Accept-Encoding': u'gzip, deflate, br', u'CloudFront-Is-SmartTV-Viewer': u'false', u'CloudFront-Forwarded-Proto': u'https', u'X-Forwarded-For': u'71.231.27.57, 104.246.180.51', u'CloudFront-Viewer-Country': u'US', u'Accept': u'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', u'User-Agent': u'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:45.0) Gecko/20100101 Firefox/45.0', u'Host': u'xo2z7zafjh.execute-api.us-east-1.amazonaws.com', u'X-Forwarded-Proto': u'https', u'Cookie': u'zappa=AQ4', u'CloudFront-Is-Tablet-Viewer': u'false', u'X-Forwarded-Port': u'443', u'Referer': u'https://xo8z7zafjh.execute-api.us-east-1.amazonaws.com/former/post', u'CloudFront-Is-Mobile-Viewer': u'false', u'X-Amz-Cf-Id': u'31zxcUcVyUxBOMk320yh5NOhihn5knqrlYQYpGGyOngKKwJb0J0BAQ==', u'CloudFront-Is-Desktop-Viewer': u'true'},
            u'stageVariables': None,
            u'path': u'/',
            }

        environ = create_wsgi_request(event, trailing_slash=False)
        response_tuple = collections.namedtuple('Response', ['status_code', 'content'])
        response = response_tuple(200, 'hello')


    def test_wsgi_without_body(self):
        event = {
            u'body': None,
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
            u'headers': {u'Via': u'1.1 38205a04d96d60185e88658d3185ccee.cloudfront.net (CloudFront)', u'Accept-Language': u'en-US,en;q=0.5', u'Accept-Encoding': u'gzip, deflate, br', u'CloudFront-Is-SmartTV-Viewer': u'false', u'CloudFront-Forwarded-Proto': u'https', u'X-Forwarded-For': u'71.231.27.57, 104.246.180.51', u'CloudFront-Viewer-Country': u'US', u'Accept': u'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', u'User-Agent': u'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:45.0) Gecko/20100101 Firefox/45.0', u'Host': u'xo2z7zafjh.execute-api.us-east-1.amazonaws.com', u'X-Forwarded-Proto': u'https', u'Cookie': u'zappa=AQ4', u'CloudFront-Is-Tablet-Viewer': u'false', u'X-Forwarded-Port': u'443', u'Referer': u'https://xo8z7zafjh.execute-api.us-east-1.amazonaws.com/former/post', u'CloudFront-Is-Mobile-Viewer': u'false', u'X-Amz-Cf-Id': u'31zxcUcVyUxBOMk320yh5NOhihn5knqrlYQYpGGyOngKKwJb0J0BAQ==', u'CloudFront-Is-Desktop-Viewer': u'true'},
            u'stageVariables': None,
            u'path': u'/',
            }

        environ = create_wsgi_request(event, trailing_slash=False)
        response_tuple = collections.namedtuple('Response', ['status_code', 'content'])
        response = response_tuple(200, 'hello')

    ##
    # Handler
    ##

    @placebo_session
    def test_handler(self, session):
        # Init will test load_remote_settings
        lh = LambdaHandler('test_settings', session=session)

        # Annoyingly, this will fail during record, but
        # the result will actually be okay to use in playback.
        # See: https://github.com/garnaat/placebo/issues/48
        self.assertEqual(os.environ['hello'], 'world')

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
        lh.handler(event, None)

        # Test scheduled event
        event = {
                    u'account': u'72333333333',
                    u'region': u'us-east-1',
                    u'detail': {},
                    u'detail-type': u'Scheduled Event',
                    u'source': u'aws.events',
                    u'version': u'0',
                    u'time': u'2016-05-10T21:05:39Z',
                    u'id': u'0d6a6db0-d5e7-4755-93a0-750a8bf49d55',
                    u'resources': [u'arn:aws:events:us-east-1:72333333333:rule/tests.test_app.schedule_me']
                }
        lh.handler(event, None)

        # Test command event
        event = {
                    u'account': u'72333333333',
                    u'region': u'us-east-1',
                    u'detail': {},
                    u'command': u'test_settings.command',
                    u'source': u'aws.events',
                    u'version': u'0',
                    u'time': u'2016-05-10T21:05:39Z',
                    u'id': u'0d6a6db0-d5e7-4755-93a0-750a8bf49d55',
                    u'resources': [u'arn:aws:events:us-east-1:72333333333:rule/tests.test_app.schedule_me']
                }
        lh.handler(event, None)

        # Test raw_command event
        event = {
                    u'account': u'72333333333',
                    u'region': u'us-east-1',
                    u'detail': {},
                    u'raw_command': u'print("check one two")',
                    u'source': u'aws.events',
                    u'version': u'0',
                    u'time': u'2016-05-10T21:05:39Z',
                    u'id': u'0d6a6db0-d5e7-4755-93a0-750a8bf49d55',
                    u'resources': [u'arn:aws:events:us-east-1:72333333333:rule/tests.test_app.schedule_me']
                }
        lh.handler(event, None)

        # Test AWS S3 event
        event = {
                    u'account': u'72333333333',
                    u'region': u'us-east-1',
                    u'detail': {},
                    u'Records': [{'s3': {'configurationId': 'test_settings.aws_s3_event'}}],
                    u'source': u'aws.events',
                    u'version': u'0',
                    u'time': u'2016-05-10T21:05:39Z',
                    u'id': u'0d6a6db0-d5e7-4755-93a0-750a8bf49d55',
                    u'resources': [u'arn:aws:events:us-east-1:72333333333:rule/tests.test_app.schedule_me']
                }
        self.assertEqual("AWS S3 EVENT", lh.handler(event, None))

        # Test AWS SNS event
        event = {
            u'account': u'72333333333',
            u'region': u'us-east-1',
            u'detail': {},
            u'Records': [
                {
                    u'EventVersion': u'1.0',
                    u'EventSource': u'aws:sns',
                    u'EventSubscriptionArn': u'arn:aws:sns:EXAMPLE',
                    u'Sns': {
                        u'SignatureVersion': u'1',
                        u'Timestamp': u'1970-01-01T00:00:00.000Z',
                        u'Signature': u'EXAMPLE',
                        u'SigningCertUrl': u'EXAMPLE',
                        u'MessageId': u'95df01b4-ee98-5cb9-9903-4c221d41eb5e',
                        u'Message': u'Hello from SNS!',
                        u'Subject': u'TestInvoke',
                        u'Type': u'Notification',
                        u'UnsubscribeUrl': u'EXAMPLE',
                        u'TopicArn': u'arn:aws:sns:1',
                        u'MessageAttributes': {
                            u'Test': {u'Type': u'String', u'Value': u'TestString'},
                            u'TestBinary': {u'Type': u'Binary', u'Value': u'TestBinary'}
                        }
                    }
                }
            ]
        }
        self.assertEqual("AWS SNS EVENT", lh.handler(event, None))

        # Test AWS DynamoDB event
        event = {
            u'Records': [
                {
                    u'eventID': u'1',
                    u'eventVersion': u'1.0',
                    u'dynamodb': {
                        u'Keys': {u'Id': {u'N': u'101'}},
                        u'NewImage': {u'Message': {u'S': u'New item!'}, u'Id': {u'N': u'101'}},
                        u'StreamViewType': u'NEW_AND_OLD_IMAGES',
                        u'SequenceNumber': u'111', u'SizeBytes': 26
                    },
                    u'awsRegion': u'us-west-2',
                    u'eventName': u'INSERT',
                    u'eventSourceARN': u'arn:aws:dynamodb:1',
                    u'eventSource': u'aws:dynamodb'
                }
            ]
        }
        self.assertEqual("AWS DYNAMODB EVENT", lh.handler(event, None))

        # Test AWS kinesis event
        event = {
            u'Records': [
                {
                    u'eventID': u'shardId-000000000000:49545115243490985018280067714973144582180062593244200961',
                    u'eventVersion': u'1.0',
                    u'kinesis': {
                        u'partitionKey': u'partitionKey-3',
                        u'data': u'SGVsbG8sIHRoaXMgaXMgYSB0ZXN0IDEyMy4=',
                        u'kinesisSchemaVersion': u'1.0',
                        u'sequenceNumber': u'49545115243490985018280067714973144582180062593244200961'
                    },
                    u'invokeIdentityArn': u'arn:aws:iam::EXAMPLE',
                    u'eventName': u'aws:kinesis:record',
                    u'eventSourceARN': u'arn:aws:kinesis:1',
                    u'eventSource': u'aws:kinesis',
                    u'awsRegion': u'us-east-1'
                 }
            ]
        }
        self.assertEqual("AWS KINESIS EVENT", lh.handler(event, None))

        # Test Authorizer event
        event = {u'authorizationToken': u'hubtoken1', u'methodArn': u'arn:aws:execute-api:us-west-2:1234:xxxxx/dev/GET/v1/endpoint/param', u'type': u'TOKEN'}
        self.assertEqual("AUTHORIZER_EVENT", lh.handler(event, None))

        # Ensure Zappa does return 401 if no function was defined.
        lh.settings.AUTHORIZER_FUNCTION = None
        with self.assertRaisesRegexp(Exception, 'Unauthorized'):
            lh.handler(event, None)

        # Unhandled event
        event = {
            u'Records': [
                {
                    u'eventID': u'shardId-000000000000:49545115243490985018280067714973144582180062593244200961',
                    u'eventVersion': u'1.0',
                    u'kinesis': {
                        u'partitionKey': u'partitionKey-3',
                        u'data': u'SGVsbG8sIHRoaXMgaXMgYSB0ZXN0IDEyMy4=',
                        u'kinesisSchemaVersion': u'1.0',
                        u'sequenceNumber': u'49545115243490985018280067714973144582180062593244200961'
                    },
                    u'eventSourceARN': u'bad:arn:1',
                }
            ]
        }
        self.assertIsNone(lh.handler(event, None))

    ##
    # CLI
    ##

    def test_cli_sanity(self):
        zappa_cli = ZappaCLI()
        return

    def test_cli_utility(self):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = 'ttt888'
        zappa_cli.load_settings('test_settings.json')
        zappa_cli.create_package()
        zappa_cli.remove_local_zip()
        logs = [
            {
                'timestamp': '12345',
                'message': '[START RequestId] test'
            },
            {
                'timestamp': '12345',
                'message': '[REPORT RequestId] test'
            },
            {
                'timestamp': '12345',
                'message': '[END RequestId] test'
            },
            {
                'timestamp': '12345',
                'message': 'test'
            }
        ]
        zappa_cli.print_logs(logs)
        zappa_cli.check_for_update()

    def test_cli_args(self):
        zappa_cli = ZappaCLI()
        # Sanity
        argv = '-s test_settings.json derp ttt888'.split()
        zappa_cli.handle(argv)

    def test_cli_error_exit_code(self):
        # Discussion: https://github.com/Miserlou/Zappa/issues/407
        zappa_cli = ZappaCLI()
        # Sanity
        argv = '-s test_settings.json status devor'.split()
        with self.assertRaises(SystemExit) as system_exit:
            zappa_cli.handle(argv)
        self.assertEqual(system_exit.exception.code, 1)

    def test_bad_json_catch(self):
        zappa_cli = ZappaCLI()
        self.assertRaises(ValueError, zappa_cli.load_settings_file, 'tests/test_bad_settings.json')

    def test_bad_stage_name_catch(self):
        zappa_cli = ZappaCLI()
        self.assertRaises(ValueError, zappa_cli.load_settings, 'tests/test_bad_stage_name_settings.json')

    def test_bad_environment_vars_catch(self):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = 'ttt888'
        self.assertRaises(ValueError, zappa_cli.load_settings, 'tests/test_bad_environment_vars.json')

    @placebo_session
    def test_cli_aws(self, session):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = 'ttt888'
        zappa_cli.api_key_required = True
        zappa_cli.authorization_type = 'NONE'
        zappa_cli.load_settings('test_settings.json', session)
        zappa_cli.zappa.credentials_arn = 'arn:aws:iam::12345:role/ZappaLambdaExecution'
        zappa_cli.deploy()
        zappa_cli.update()
        zappa_cli.rollback(1)
        zappa_cli.tail(False)
        zappa_cli.schedule()
        zappa_cli.unschedule()
        zappa_cli.undeploy(noconfirm=True, remove_logs=True)

    @placebo_session
    def test_cli_aws_status(self, session):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = 'ttt888'
        zappa_cli.load_settings('test_settings.json', session)
        zappa_cli.api_stage = 'devor'
        zappa_cli.lambda_name = 'baby-flask-devor'
        zappa_cli.zappa.credentials_arn = 'arn:aws:iam::12345:role/ZappaLambdaExecution'
        resp = zappa_cli.status()

    def test_cli_init(self):

        if os.path.isfile('zappa_settings.json'):
            os.remove('zappa_settings.json')

        # Test directly
        zappa_cli = ZappaCLI()
        # Via http://stackoverflow.com/questions/2617057/how-to-supply-stdin-files-and-environment-variable-inputs-to-python-unit-tests
        inputs = ['dev', 'lmbda', 'test_settings', '']
        input_generator = (i for i in inputs)
        with mock.patch('__builtin__.raw_input', lambda prompt: next(input_generator)):
            zappa_cli.init()

        if os.path.isfile('zappa_settings.json'):
            os.remove('zappa_settings.json')

        # Test via handle()
        input_generator = (i for i in inputs)
        with mock.patch('__builtin__.raw_input', lambda prompt: next(input_generator)):
            zappa_cli = ZappaCLI()
            argv = ['init']
            zappa_cli.handle(argv)

        if os.path.isfile('zappa_settings.json'):
            os.remove('zappa_settings.json')

    def test_domain_name_match(self):
        # Simple sanity check
        zone = Zappa.get_best_match_zone(all_zones={ 'HostedZones': [
            {
                'Name': 'example.com.au.',
                'Id': 'zone-correct'
            }
        ]},
            domain='www.example.com.au')
        assert zone == 'zone-correct'

        # No match test
        zone = Zappa.get_best_match_zone(all_zones={'HostedZones': [
            {
                'Name': 'example.com.au.',
                'Id': 'zone-incorrect'
            }
        ]},
            domain='something-else.com.au')
        assert zone is None

        # More involved, better match should win.
        zone = Zappa.get_best_match_zone(all_zones={'HostedZones': [
            {
                'Name': 'example.com.au.',
                'Id': 'zone-incorrect'
            },
            {
                'Name': 'subdomain.example.com.au.',
                'Id': 'zone-correct'
            }
        ]},
            domain='www.subdomain.example.com.au')
        assert zone == 'zone-correct'


    ##
    # Let's Encrypt / ACME
    ##

    def test_lets_encrypt_sanity(self):

        # We need a fake account key and crt
        import subprocess
        proc = subprocess.Popen(["openssl genrsa 2048 > /tmp/account.key"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        out, err = proc.communicate()
        if proc.returncode != 0:
            raise IOError("OpenSSL Error: {0}".format(err))
        proc = subprocess.Popen(["openssl req -x509 -newkey rsa:2048 -subj '/C=US/ST=Denial/L=Springfield/O=Dis/CN=www.example.com' -passout pass:foo -keyout /tmp/key.key -out test_signed.crt -days 1 > /tmp/signed.crt"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        out, err = proc.communicate()
        if proc.returncode != 0:
            raise IOError("OpenSSL Error: {0}".format(err))

        DEFAULT_CA = "https://acme-staging.api.letsencrypt.org"
        CA = "https://acme-staging.api.letsencrypt.org"

        try:
            result = register_account()
        except ValueError as e:
            pass # that's fine.

        create_domain_key()
        create_domain_csr('herp.derp.wtf')
        parse_account_key()
        parse_csr()
        create_chained_certificate()

        try:
            result = sign_certificate()
        except ValueError as e:
            pass # that's fine.

        result = verify_challenge('http://echo.jsontest.com/status/valid')
        try:
            result = verify_challenge('http://echo.jsontest.com/status/fail')
        except ValueError as e:
            pass # that's fine.
        try:
            result = verify_challenge('http://bing.com')
        except ValueError as e:
            pass # that's fine.

        encode_certificate(b'123')

        os.remove('test_signed.crt')
        cleanup()

    ##
    # Django
    ##

    def test_detect_dj(self):
        # Sanity
        settings_modules = detect_django_settings()

    def test_dj_wsgi(self):
        # Sanity
        settings_modules = detect_django_settings()

        settings = """
# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os
BASE_DIR = os.path.dirname(os.path.dirname(__file__))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.7/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'alskdfjalsdkf=0*%do-ayvy*m2k=vss*$7)j8q!@u0+d^na7mi2(^!l!d'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

TEMPLATE_DEBUG = True

ALLOWED_HOSTS = []

# Application definition

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
)

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
)

ROOT_URLCONF = 'blah.urls'
WSGI_APPLICATION = 'hackathon_starter.wsgi.application'

# Database
# https://docs.djangoproject.com/en/1.7/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

# Internationalization
# https://docs.djangoproject.com/en/1.7/topics/i18n/

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True
        """

        djts = open("dj_test_settings.py", "w")
        djts.write(settings)
        djts.close()

        app = get_django_wsgi('dj_test_settings')
        os.remove('dj_test_settings.py')
        os.remove('dj_test_settings.pyc')

    ##
    # Util / Misc
    ##

    def test_human_units(self):
        zappa = Zappa()
        zappa.human_size(1)
        zappa.human_size(9999999999999)

    def test_event_name(self):
        zappa = Zappa()
        truncated = zappa.get_event_name("basldfkjalsdkfjalsdkfjaslkdfjalsdkfjadlsfkjasdlfkjasdlfkjasdflkjasdf-asdfasdfasdfasdfasdf", "this.is.my.dang.function.wassup.yeah.its.long")
        self.assertTrue(len(truncated) <= 64)
        truncated = zappa.get_event_name("basldfkjalsdkfjalsdkfjaslkdfjalsdkfjadlsfkjasdlfkjasdlfkjasdflkjasdf-asdfasdfasdfasdfasdf", "thisidoasdfaljksdfalskdjfalsdkfjasldkfjalsdkfjalsdkfjalsdfkjalasdfasdfasdfasdklfjasldkfjalsdkjfaslkdfjasldkfjasdflkjdasfskdj")
        self.assertTrue(len(truncated) <= 64)
        truncated = zappa.get_event_name("a", "b")
        self.assertTrue(len(truncated) <= 64)

    def test_detect_dj(self):
        # Sanity
        settings_modules = detect_django_settings()

    def test_detect_flask(self):
        # Sanity
        settings_modules = detect_flask_apps()

    @placebo_session
    def test_add_event_source(self, session):

        event_source = {'arn': 'blah:blah:blah:blah', 'events': [
                    "s3:ObjectCreated:*"
                  ]}
        # Sanity. This should fail.
        try:
            es = add_event_source(event_source, 'blah:blah:blah:blah', 'test_settings.callback', session)
            self.fail("Success should have failed.")
        except ValueError:
            pass

        event_source = {'arn': 's3:s3:s3:s3', 'events': [
                    "s3:ObjectCreated:*"
                  ]}
        add_event_source(event_source, 'lambda:lambda:lambda:lambda', 'test_settings.callback', session, dry=True)
        remove_event_source(event_source, 'lambda:lambda:lambda:lambda', 'test_settings.callback', session, dry=True)
        # get_event_source_status(event_source, 'lambda:lambda:lambda:lambda', 'test_settings.callback', session, dry=True)

    def test_shameless(self):
        shamelessly_promote()

if __name__ == '__main__':
    unittest.main()
