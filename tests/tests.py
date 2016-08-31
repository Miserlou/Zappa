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

    @placebo_session
    def test_deploy_api_gateway(self, session):
        z = Zappa(session)
        z.credentials_arn = 'arn:aws:iam::12345:role/ZappaLambdaExecution'

        z.parameter_depth = 1
        z.integration_response_codes = [200]
        z.method_response_codes = [200]
        z.http_methods = ['GET']

        lambda_arn = 'arn:aws:lambda:us-east-1:12345:function:django-helloworld-unicode'
        api_id = z.create_api_gateway_routes(lambda_arn)
        endpoint_url = z.deploy_api_gateway(api_id, "test_stage")

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

        event = {
            "body": "",
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
                "CloudFront-Is-Desktop-Viewer": "true",
                "Content-Type": "application/json"
            },
            "params": {
                "parameter_1": "asdf1",
                "parameter_2": "asdf2",
            },
            "method": "POST",
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

        request = create_wsgi_request(event, trailing_slash=False, script_name='asdf1')
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

    def test_wsgi_multipart(self):
        event = {u'body': u'LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS03Njk1MjI4NDg0Njc4MTc2NTgwNjMwOTYxDQpDb250ZW50LURpc3Bvc2l0aW9uOiBmb3JtLWRhdGE7IG5hbWU9Im15c3RyaW5nIg0KDQpkZGQNCi0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tNzY5NTIyODQ4NDY3ODE3NjU4MDYzMDk2MS0tDQo=', u'headers': {u'Content-Type': u'multipart/form-data; boundary=---------------------------7695228484678176580630961', u'Via': u'1.1 38205a04d96d60185e88658d3185ccee.cloudfront.net (CloudFront)', u'Accept-Language': u'en-US,en;q=0.5', u'Accept-Encoding': u'gzip, deflate, br', u'CloudFront-Is-SmartTV-Viewer': u'false', u'CloudFront-Forwarded-Proto': u'https', u'X-Forwarded-For': u'71.231.27.57, 104.246.180.51', u'CloudFront-Viewer-Country': u'US', u'Accept': u'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', u'User-Agent': u'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:45.0) Gecko/20100101 Firefox/45.0', u'Host': u'xo2z7zafjh.execute-api.us-east-1.amazonaws.com', u'X-Forwarded-Proto': u'https', u'Cookie': u'zappa=AQ4', u'CloudFront-Is-Tablet-Viewer': u'false', u'X-Forwarded-Port': u'443', u'Referer': u'https://xo8z7zafjh.execute-api.us-east-1.amazonaws.com/former/post', u'CloudFront-Is-Mobile-Viewer': u'false', u'X-Amz-Cf-Id': u'31zxcUcVyUxBOMk320yh5NOhihn5knqrlYQYpGGyOngKKwJb0J0BAQ==', u'CloudFront-Is-Desktop-Viewer': u'true'}, u'params': {u'parameter_1': u'post'}, u'method': u'POST', u'query': {}}
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

    def test_cli_args(self):
        zappa_cli = ZappaCLI()
        # Sanity
        argv = '-s test_settings.json derp ttt888'.split()
        zappa_cli.handle(argv)

    @placebo_session
    def test_cli_aws(self, session):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = 'ttt888'
        zappa_cli.api_key_required = True
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

        zappa_cli = ZappaCLI()
        # Via http://stackoverflow.com/questions/2617057/how-to-supply-stdin-files-and-environment-variable-inputs-to-python-unit-tests
        inputs = ['dev', 'lmbda', 'test_settings', '']
        input_generator = (i for i in inputs)
        with mock.patch('__builtin__.raw_input', lambda prompt: next(input_generator)):
            zappa_cli.init()

        if os.path.isfile('zappa_settings.json'):
            os.remove('zappa_settings.json')

        # with mock.patch('__builtin__.raw_input', lambda prompt: next(input_generator)):
        #     zappa_cli = ZappaCLI()
        #     argv = ['init']
        #     zappa_cli.handle(argv)

        # if os.path.isfile('zappa_settings.json'):
        #     os.remove('zappa_settings.json')

    def test_domain_name_match(self):
        # Simple sanity check
        zone = Zappa._get_best_match_zone(all_zones={ 'HostedZones': [
            {
                'Name': 'example.com.au.',
                'Id': 'zone-correct'
            }
        ]},
            domain='www.example.com.au')
        assert zone == 'zone-correct'

        # No match test
        zone = Zappa._get_best_match_zone(all_zones={'HostedZones': [
            {
                'Name': 'example.com.au.',
                'Id': 'zone-incorrect'
            }
        ]},
            domain='something-else.com.au')
        assert zone is None

        # More involved, better match should win.
        zone = Zappa._get_best_match_zone(all_zones={'HostedZones': [
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
