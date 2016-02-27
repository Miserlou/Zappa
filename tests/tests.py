import collections
import json
import os
import unittest
import mock

from .utils import placebo_session

from zappa.wsgi import create_wsgi_request, common_log
from zappa.zappa import Zappa, ASSUME_POLICY, ATTACH_POLICY


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


if __name__ == '__main__':
    unittest.main()
