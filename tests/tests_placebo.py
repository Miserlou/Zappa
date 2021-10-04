# -*- coding: utf8 -*-
import mock
import os
import random
import string
import unittest

from .utils import placebo_session

from zappa.cli import ZappaCLI
from zappa.handler import LambdaHandler
from zappa.utilities import add_event_source, remove_event_source
from zappa.core import Zappa


def random_string(length):
    return "".join(random.choice(string.printable) for _ in range(length))


class TestZappa(unittest.TestCase):
    def setUp(self):
        self.sleep_patch = mock.patch("time.sleep", return_value=None)
        # Tests expect us-east-1.
        # If the user has set a different region in env variables, we set it aside for now and use us-east-1
        self.users_current_region_name = os.environ.get("AWS_DEFAULT_REGION", None)
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
        if not os.environ.get("PLACEBO_MODE") == "record":
            self.sleep_patch.start()

    def tearDown(self):
        if not os.environ.get("PLACEBO_MODE") == "record":
            self.sleep_patch.stop()
        del os.environ["AWS_DEFAULT_REGION"]
        if self.users_current_region_name is not None:
            # Give the user their AWS region back, we're done testing with us-east-1.
            os.environ["AWS_DEFAULT_REGION"] = self.users_current_region_name

    @placebo_session
    def test_upload_remove_s3(self, session):
        bucket_name = "test_zappa_upload_s3"
        z = Zappa(session)
        zip_path = z.create_lambda_zip(minify=False)
        res = z.upload_to_s3(zip_path, bucket_name)
        self.assertTrue(res)
        s3 = session.resource("s3")

        # will throw ClientError with 404 if bucket doesn't exist
        s3.meta.client.head_bucket(Bucket=bucket_name)

        # will throw ClientError with 404 if object doesn't exist
        s3.meta.client.head_object(
            Bucket=bucket_name,
            Key=zip_path,
        )
        res = z.remove_from_s3(zip_path, bucket_name)
        self.assertTrue(res)

        fail = z.upload_to_s3("/tmp/this_isnt_real", bucket_name)
        self.assertFalse(fail)

        # Will graciouly handle quirky S3 behavior on 'us-east-1' region name'
        z.aws_region = "us-east-1"
        res = z.upload_to_s3(zip_path, bucket_name)
        os.remove(zip_path)
        self.assertTrue(res)

    @placebo_session
    def test_copy_on_s3(self, session):
        bucket_name = "test_zappa_upload_s3"
        z = Zappa(session)
        zip_path = z.create_lambda_zip(minify=False)
        res = z.upload_to_s3(zip_path, bucket_name)
        self.assertTrue(res)
        s3 = session.resource("s3")

        # will throw ClientError with 404 if bucket doesn't exist
        s3.meta.client.head_bucket(Bucket=bucket_name)

        # will throw ClientError with 404 if object doesn't exist
        s3.meta.client.head_object(
            Bucket=bucket_name,
            Key=zip_path,
        )
        zp = "copy_" + zip_path
        res = z.copy_on_s3(zip_path, zp, bucket_name)
        os.remove(zip_path)
        self.assertTrue(res)

    @placebo_session
    def test_create_lambda_function_s3(self, session):
        bucket_name = "lmbda"
        zip_path = "Spheres-dev-1454694878.zip"

        z = Zappa(session)
        z.aws_region = "us-east-1"
        z.load_credentials(session)
        z.credentials_arn = "arn:aws:iam::12345:role/ZappaLambdaExecution"

        arn = z.create_lambda_function(
            bucket=bucket_name,
            s3_key=zip_path,
            function_name="test_lmbda_function55",
            handler="runme.lambda_handler",
        )

        arn = z.update_lambda_function(
            bucket=bucket_name,
            s3_key=zip_path,
            function_name="test_lmbda_function55",
        )

    @placebo_session
    def test_create_lambda_function_local(self, session):
        bucket_name = "lmbda"
        local_file = "Spheres-dev-1454694878.zip"

        z = Zappa(session)
        z.aws_region = "us-east-1"
        z.load_credentials(session)
        z.credentials_arn = "arn:aws:iam::12345:role/ZappaLambdaExecution"

        arn = z.create_lambda_function(
            bucket=bucket_name,
            local_zip=local_file,
            function_name="test_lmbda_function55",
            handler="runme.lambda_handler",
        )

        arn = z.update_lambda_function(
            bucket=bucket_name,
            local_zip=local_file,
            function_name="test_lmbda_function55",
        )

    @placebo_session
    def test_create_lambda_function_docker(self, session):
        bucket_name = "lmbda"
        docker_image_uri = "docker_image_uri"

        z = Zappa(session)
        z.aws_region = "us-east-1"
        z.load_credentials(session)
        z.credentials_arn = "arn:aws:iam::12345:role/ZappaLambdaExecution"

        arn = z.create_lambda_function(
            bucket=bucket_name,
            docker_image_uri=docker_image_uri,
            function_name="test_lmbda_function55",
        )

        arn = z.update_lambda_function(
            bucket=bucket_name,
            docker_image_uri=docker_image_uri,
            function_name="test_lmbda_function55",
        )

    @placebo_session
    def test_rollback_lambda_function_version(self, session):
        z = Zappa(session)
        z.credentials_arn = "arn:aws:iam::724336686645:role/ZappaLambdaExecution"

        function_name = "django-helloworld-unicode"
        too_many_versions = z.rollback_lambda_function_version(function_name, 99999)
        self.assertFalse(too_many_versions)

        function_arn = z.rollback_lambda_function_version(function_name, 1)

    @placebo_session
    def test_rollback_lambda_function_version_docker(self, session):
        z = Zappa(session)
        z.credentials_arn = "arn:aws:iam::724336686645:role/ZappaLambdaExecution"

        function_name = "django-helloworld-unicode"

        with self.assertRaises(NotImplementedError):
            z.rollback_lambda_function_version(function_name)

    @placebo_session
    def test_invoke_lambda_function(self, session):
        z = Zappa(session)
        z.credentials_arn = "arn:aws:iam::724336686645:role/ZappaLambdaExecution"

        function_name = "django-helloworld-unicode"
        payload = '{"event": "hello"}'
        response = z.invoke_lambda_function(function_name, payload)

    @placebo_session
    def test_create_iam_roles(self, session):
        z = Zappa(session)
        arn, updated = z.create_iam_roles()
        self.assertEqual(arn, "arn:aws:iam::123:role/{}".format(z.role_name))

    @placebo_session
    def test_get_api_url(self, session):
        z = Zappa(session)
        z.credentials_arn = "arn:aws:iam::724336686645:role/ZappaLambdaExecution"
        url = z.get_api_url("Spheres-demonstration", "demonstration")

    @placebo_session
    def test_fetch_logs(self, session):
        z = Zappa(session)
        z.credentials_arn = "arn:aws:iam::12345:role/ZappaLambdaExecution"
        events = z.fetch_logs("Spheres-demonstration")
        self.assertTrue(events is not None)

    ##
    # Handler
    ##

    @placebo_session
    def test_handler(self, session):
        # Init will test load_remote_settings
        lh = LambdaHandler("test_settings", session=session)

        # Annoyingly, this will fail during record, but
        # the result will actually be okay to use in playback.
        # See: https://github.com/garnaat/placebo/issues/48
        self.assertEqual(os.environ["hello"], "world")

        event = {
            "body": {},
            "headers": {},
            "params": {
                "parameter_1": "asdf1",
                "parameter_2": "asdf2",
            },
            "method": "GET",
            "query": {},
        }
        lh.handler(event, None)

        # Test scheduled event
        event = {
            "account": "72333333333",
            "region": "us-east-1",
            "detail": {},
            "detail-type": "Scheduled Event",
            "source": "aws.events",
            "version": "0",
            "time": "2016-05-10T21:05:39Z",
            "id": "0d6a6db0-d5e7-4755-93a0-750a8bf49d55",
            "resources": [
                "arn:aws:events:us-east-1:72333333333:rule/tests.test_app.schedule_me"
            ],
        }
        lh.handler(event, None)

        # Test command event
        event = {
            "account": "72333333333",
            "region": "us-east-1",
            "detail": {},
            "command": "test_settings.command",
            "source": "aws.events",
            "version": "0",
            "time": "2016-05-10T21:05:39Z",
            "id": "0d6a6db0-d5e7-4755-93a0-750a8bf49d55",
            "resources": [
                "arn:aws:events:us-east-1:72333333333:rule/tests.test_app.schedule_me"
            ],
        }
        lh.handler(event, None)

        # Test command for async event
        event = {
            "account": "72333333333",
            "region": "us-east-1",
            "detail": {},
            "command": "zappa.asynchronous.route_lambda_task",
            "task_path": "tests.test_app.async_me",
            "args": ["xxx"],
            "kwargs": {},
            "source": "aws.events",
            "version": "0",
            "time": "2016-05-10T21:05:39Z",
            "id": "0d6a6db0-d5e7-4755-93a0-750a8bf49d55",
        }
        self.assertEqual("run async when on lambda xxx", lh.handler(event, None))
        event["kwargs"] = {"foo": "bar"}
        self.assertEqual("run async when on lambda xxxbar", lh.handler(event, None))

        # Test raw_command event
        event = {
            "account": "72333333333",
            "region": "us-east-1",
            "detail": {},
            "raw_command": 'print("check one two")',
            "source": "aws.events",
            "version": "0",
            "time": "2016-05-10T21:05:39Z",
            "id": "0d6a6db0-d5e7-4755-93a0-750a8bf49d55",
            "resources": [
                "arn:aws:events:us-east-1:72333333333:rule/tests.test_app.schedule_me"
            ],
        }
        lh.handler(event, None)

        # Test AWS S3 event
        event = {
            "account": "72333333333",
            "region": "us-east-1",
            "detail": {},
            "Records": [
                {"s3": {"configurationId": "test_project:test_settings.aws_s3_event"}}
            ],
            "source": "aws.events",
            "version": "0",
            "time": "2016-05-10T21:05:39Z",
            "id": "0d6a6db0-d5e7-4755-93a0-750a8bf49d55",
            "resources": [
                "arn:aws:events:us-east-1:72333333333:rule/tests.test_app.schedule_me"
            ],
        }
        self.assertEqual("AWS S3 EVENT", lh.handler(event, None))

        # Test AWS SNS event
        event = {
            "account": "72333333333",
            "region": "us-east-1",
            "detail": {},
            "Records": [
                {
                    "EventVersion": "1.0",
                    "EventSource": "aws:sns",
                    "EventSubscriptionArn": "arn:aws:sns:EXAMPLE",
                    "Sns": {
                        "SignatureVersion": "1",
                        "Timestamp": "1970-01-01T00:00:00.000Z",
                        "Signature": "EXAMPLE",
                        "SigningCertUrl": "EXAMPLE",
                        "MessageId": "95df01b4-ee98-5cb9-9903-4c221d41eb5e",
                        "Message": "Hello from SNS!",
                        "Subject": "TestInvoke",
                        "Type": "Notification",
                        "UnsubscribeUrl": "EXAMPLE",
                        "TopicArn": "arn:aws:sns:1",
                        "MessageAttributes": {
                            "Test": {"Type": "String", "Value": "TestString"},
                            "TestBinary": {"Type": "Binary", "Value": "TestBinary"},
                        },
                    },
                }
            ],
        }
        self.assertEqual("AWS SNS EVENT", lh.handler(event, None))

        # Test AWS SNS event
        event = {
            "account": "72333333333",
            "region": "us-east-1",
            "detail": {},
            "Records": [
                {
                    "EventVersion": "1.0",
                    "EventSource": "aws:sns",
                    "EventSubscriptionArn": "arn:aws:sns:EXAMPLE",
                    "Sns": {
                        "SignatureVersion": "1",
                        "Timestamp": "1970-01-01T00:00:00.000Z",
                        "Signature": "EXAMPLE",
                        "SigningCertUrl": "EXAMPLE",
                        "MessageId": "95df01b4-ee98-5cb9-9903-4c221d41eb5e",
                        "Message": '{"args": ["arg1", "arg2"], "command": "zappa.asynchronous.route_sns_task", '
                        '"task_path": "test_settings.aws_async_sns_event", "kwargs": {"arg3": "varg3"}}',
                        "Subject": "TestInvoke",
                        "Type": "Notification",
                        "UnsubscribeUrl": "EXAMPLE",
                        "MessageAttributes": {
                            "Test": {"Type": "String", "Value": "TestString"},
                            "TestBinary": {"Type": "Binary", "Value": "TestBinary"},
                        },
                    },
                }
            ],
        }
        self.assertEqual("AWS ASYNC SNS EVENT", lh.handler(event, None))

        # Test AWS DynamoDB event
        event = {
            "Records": [
                {
                    "eventID": "1",
                    "eventVersion": "1.0",
                    "dynamodb": {
                        "Keys": {"Id": {"N": "101"}},
                        "NewImage": {"Message": {"S": "New item!"}, "Id": {"N": "101"}},
                        "StreamViewType": "NEW_AND_OLD_IMAGES",
                        "SequenceNumber": "111",
                        "SizeBytes": 26,
                    },
                    "awsRegion": "us-west-2",
                    "eventName": "INSERT",
                    "eventSourceARN": "arn:aws:dynamodb:1",
                    "eventSource": "aws:dynamodb",
                }
            ]
        }
        self.assertEqual("AWS DYNAMODB EVENT", lh.handler(event, None))

        # Test AWS kinesis event
        event = {
            "Records": [
                {
                    "eventID": "shardId-000000000000:49545115243490985018280067714973144582180062593244200961",
                    "eventVersion": "1.0",
                    "kinesis": {
                        "partitionKey": "partitionKey-3",
                        "data": "SGVsbG8sIHRoaXMgaXMgYSB0ZXN0IDEyMy4=",
                        "kinesisSchemaVersion": "1.0",
                        "sequenceNumber": "49545115243490985018280067714973144582180062593244200961",
                    },
                    "invokeIdentityArn": "arn:aws:iam::EXAMPLE",
                    "eventName": "aws:kinesis:record",
                    "eventSourceARN": "arn:aws:kinesis:1",
                    "eventSource": "aws:kinesis",
                    "awsRegion": "us-east-1",
                }
            ]
        }
        self.assertEqual("AWS KINESIS EVENT", lh.handler(event, None))

        # Test AWS SQS event
        event = {
            "Records": [
                {
                    "messageId": "c80e8021-a70a-42c7-a470-796e1186f753",
                    "receiptHandle": "AQEBJQ+/u6NsnT5t8Q/VbVxgdUl4TMKZ5FqhksRdIQvLBhwNvADoBxYSOVeCBXdnS9P+erlTtwEALHsnBXynkfPLH3BOUqmgzP25U8kl8eHzq6RAlzrSOfTO8ox9dcp6GLmW33YjO3zkq5VRYyQlJgLCiAZUpY2D4UQcE5D1Vm8RoKfbE+xtVaOctYeINjaQJ1u3mWx9T7tork3uAlOe1uyFjCWU5aPX/1OHhWCGi2EPPZj6vchNqDOJC/Y2k1gkivqCjz1CZl6FlZ7UVPOx3AMoszPuOYZ+Nuqpx2uCE2MHTtMHD8PVjlsWirt56oUr6JPp9aRGo6bitPIOmi4dX0FmuMKD6u/JnuZCp+AXtJVTmSHS8IXt/twsKU7A+fiMK01NtD5msNgVPoe9JbFtlGwvTQ==",
                    "body": '{"foo":"bar"}',
                    "attributes": {
                        "ApproximateReceiveCount": "3",
                        "SentTimestamp": "1529104986221",
                        "SenderId": "594035263019",
                        "ApproximateFirstReceiveTimestamp": "1529104986230",
                    },
                    "messageAttributes": {},
                    "md5OfBody": "9bb58f26192e4ba00f01e2e7b136bbd8",
                    "eventSource": "aws:sqs",
                    "eventSourceARN": "arn:aws:sqs:1",
                    "awsRegion": "us-east-1",
                }
            ]
        }
        self.assertEqual("AWS SQS EVENT", lh.handler(event, None))

        # Test Authorizer event
        event = {
            "authorizationToken": "hubtoken1",
            "methodArn": "arn:aws:execute-api:us-west-2:1234:xxxxx/dev/GET/v1/endpoint/param",
            "type": "TOKEN",
        }
        self.assertEqual("AUTHORIZER_EVENT", lh.handler(event, None))

        # Ensure Zappa does return 401 if no function was defined.
        lh.settings.AUTHORIZER_FUNCTION = None
        with self.assertRaisesRegexp(Exception, "Unauthorized"):
            lh.handler(event, None)

        # Unhandled event
        event = {
            "Records": [
                {
                    "eventID": "shardId-000000000000:49545115243490985018280067714973144582180062593244200961",
                    "eventVersion": "1.0",
                    "kinesis": {
                        "partitionKey": "partitionKey-3",
                        "data": "SGVsbG8sIHRoaXMgaXMgYSB0ZXN0IDEyMy4=",
                        "kinesisSchemaVersion": "1.0",
                        "sequenceNumber": "49545115243490985018280067714973144582180062593244200961",
                    },
                    "eventSourceARN": "bad:arn:1",
                }
            ]
        }
        self.assertIsNone(lh.handler(event, None))

    ##
    # CLI
    ##

    @placebo_session
    def test_cli_aws(self, session):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "ttt888"
        zappa_cli.api_key_required = True
        zappa_cli.authorization_type = "NONE"
        zappa_cli.load_settings("test_settings.json", session)
        zappa_cli.zappa.credentials_arn = "arn:aws:iam::12345:role/ZappaLambdaExecution"
        zappa_cli.deploy()
        zappa_cli.update()
        zappa_cli.rollback(1)
        zappa_cli.tail(since=0, filter_pattern="", keep_open=False)
        zappa_cli.schedule()
        zappa_cli.unschedule()
        zappa_cli.undeploy(no_confirm=True, remove_logs=True)

    @placebo_session
    def test_cli_aws_status(self, session):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "ttt888"
        zappa_cli.load_settings("test_settings.json", session)
        zappa_cli.api_stage = "devor"
        zappa_cli.lambda_name = "baby-flask-devor"
        zappa_cli.zappa.credentials_arn = "arn:aws:iam::12345:role/ZappaLambdaExecution"
        resp = zappa_cli.status()

    ##
    # Let's Encrypt / ACME
    ##

    ##
    # Django
    ##

    ##
    # Util / Misc
    ##

    @placebo_session
    def test_add_event_source(self, session):

        event_source = {"arn": "blah:blah:blah:blah", "events": ["s3:ObjectCreated:*"]}
        # Sanity. This should fail.
        try:
            es = add_event_source(
                event_source, "blah:blah:blah:blah", "test_settings.callback", session
            )
            self.fail("Success should have failed.")
        except ValueError:
            pass

        event_source = {"arn": "s3:s3:s3:s3", "events": ["s3:ObjectCreated:*"]}
        add_event_source(
            event_source,
            "lambda:lambda:lambda:lambda",
            "test_settings.callback",
            session,
            dry=True,
        )
        remove_event_source(
            event_source,
            "lambda:lambda:lambda:lambda",
            "test_settings.callback",
            session,
            dry=True,
        )
        # get_event_source_status(event_source, 'lambda:lambda:lambda:lambda', 'test_settings.callback', session, dry=True)

    @placebo_session
    def test_cognito_trigger(self, session):
        z = Zappa(session)
        z.update_cognito(
            "Zappa-Trigger-Test",
            "us-east-1_9jUv74DH8",
            {"PreSignUp": "test.tasks.pre_signup"},
            "arn:aws:lambda:us-east-1:12345:function:Zappa-Trigger-Test",
        )

    @placebo_session
    def test_cognito_trigger_existing(self, session):
        z = Zappa(session)
        z.update_cognito(
            "Zappa-Trigger-Test",
            "us-east-1_9jUv74DH8",
            {"PreSignUp": "test.tasks.pre_signup"},
            "arn:aws:lambda:us-east-1:12345:function:Zappa-Trigger-Test",
        )

    @placebo_session
    def test_cli_cognito_triggers(self, session):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "ttt888"
        zappa_cli.api_key_required = True
        zappa_cli.load_settings("test_settings.json", session)
        zappa_cli.lambda_arn = (
            "arn:aws:lambda:us-east-1:12345:function:Zappa-Trigger-Test"
        )
        zappa_cli.update_cognito_triggers()

    @placebo_session
    def test_cognito_trigger_existing_UnusedAccountValidityDays(self, session):
        z = Zappa(session)
        z.update_cognito(
            "Zappa-Trigger-Test",
            "us-east-1_9jUv74DH8",
            {"PreSignUp": "test.tasks.pre_signup"},
            "arn:aws:lambda:us-east-1:12345:function:Zappa-Trigger-Test",
        )


if __name__ == "__main__":
    unittest.main()
