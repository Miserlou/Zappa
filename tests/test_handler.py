from mock import Mock
import sys
import unittest
from zappa.handler import LambdaHandler
from zappa.utilities import merge_headers


def no_args():
    return


def one_arg(first):
    return first


def two_args(first, second):
    return first, second


def var_args(*args):
    return args


def var_args_with_one(first, *args):
    return first, args[0]


def unsupported(first, second, third):
    return first, second, third


def raises_exception(*args, **kwargs):
    raise Exception("app exception")


def handle_bot_intent(event, context):
    return "Success"


mocked_exception_handler = Mock()


class TestZappa(unittest.TestCase):
    def setUp(self):
        mocked_exception_handler.reset_mock()

    def tearDown(self):
        LambdaHandler._LambdaHandler__instance = None
        LambdaHandler.settings = None
        LambdaHandler.settings_name = None

    def test_run_function(self):
        self.assertIsNone(LambdaHandler.run_function(no_args, "e", "c"))
        self.assertEqual(LambdaHandler.run_function(one_arg, "e", "c"), "e")
        self.assertEqual(LambdaHandler.run_function(two_args, "e", "c"), ("e", "c"))
        self.assertEqual(LambdaHandler.run_function(var_args, "e", "c"), ("e", "c"))
        self.assertEqual(
            LambdaHandler.run_function(var_args_with_one, "e", "c"), ("e", "c")
        )

        try:
            LambdaHandler.run_function(unsupported, "e", "c")
            self.fail("Exception expected")
        except RuntimeError as e:
            pass

    def test_run_fuction_with_type_hint(self):
        scope = {}
        exec("def f_with_type_hint() -> None: return", scope)
        f_with_type_hint = scope["f_with_type_hint"]
        self.assertIsNone(LambdaHandler.run_function(f_with_type_hint, "e", "c"))

    def test_wsgi_script_name_on_aws_url(self):
        """
        Ensure that requests to the amazonaws.com host for an API with a
        domain have the correct request.url
        """
        lh = LambdaHandler("tests.test_wsgi_script_name_settings")

        event = {
            "body": "",
            "resource": "/{proxy+}",
            "requestContext": {},
            "queryStringParameters": {},
            "headers": {
                "Host": "1234567890.execute-api.us-east-1.amazonaws.com",
            },
            "pathParameters": {"proxy": "return/request/url"},
            "httpMethod": "GET",
            "stageVariables": {},
            "path": "/return/request/url",
        }
        response = lh.handler(event, None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(
            response["body"],
            "https://1234567890.execute-api.us-east-1.amazonaws.com/dev/return/request/url",
        )

    def test_wsgi_script_name_on_domain_url(self):
        """
        Ensure that requests to the amazonaws.com host for an API with a
        domain have the correct request.url
        """
        lh = LambdaHandler("tests.test_wsgi_script_name_settings")

        event = {
            "body": "",
            "resource": "/{proxy+}",
            "requestContext": {},
            "queryStringParameters": {},
            "headers": {
                "Host": "example.com",
            },
            "pathParameters": {"proxy": "return/request/url"},
            "httpMethod": "GET",
            "stageVariables": {},
            "path": "/return/request/url",
        }
        response = lh.handler(event, None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(response["body"], "https://example.com/return/request/url")

    def test_wsgi_script_name_with_multi_value_header(self):
        """
        Ensure that requests generated with multivalued headers (such as
        from an ALB with Multi Valued Headers enabled) succeed.
        """
        lh = LambdaHandler("tests.test_wsgi_script_name_settings")

        event = {
            "body": "",
            "resource": "/{proxy+}",
            "requestContext": {},
            "queryStringParameters": {},
            "multiValueHeaders": {
                "Host": ["example.com"],
            },
            "pathParameters": {"proxy": "return/request/url"},
            "httpMethod": "GET",
            "stageVariables": {},
            "path": "/return/request/url",
        }
        response = lh.handler(event, None)
        self.assertEqual(response["statusCode"], 200)
        self.assertIn("multiValueHeaders", response)

    def test_wsgi_script_name_with_multi_value_querystring(self):
        """
        Ensure that requests generated with multivalue querystrings succeed.
        """
        lh = LambdaHandler("tests.test_wsgi_script_name_settings")

        event = {
            "body": "",
            "resource": "/{proxy+}",
            "requestContext": {},
            "multiValueQueryStringParameters": {"multi": ["value", "qs"]},
            "multiValueHeaders": {
                "Host": ["example.com"],
            },
            "pathParameters": {"proxy": "return/request/url"},
            "httpMethod": "GET",
            "stageVariables": {},
            "path": "/return/request/url",
        }
        response = lh.handler(event, None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(
            response["body"],
            "https://example.com/return/request/url?multi=value&multi=qs",
        )

    def test_wsgi_script_name_on_test_request(self):
        """
        Ensure that requests sent by the "Send test request" button behaves
        sensibly
        """
        lh = LambdaHandler("tests.test_wsgi_script_name_settings")

        event = {
            "body": "",
            "resource": "/{proxy+}",
            "requestContext": {},
            "queryStringParameters": {},
            "headers": {},
            "pathParameters": {"proxy": "return/request/url"},
            "httpMethod": "GET",
            "stageVariables": {},
            "path": "/return/request/url",
        }
        response = lh.handler(event, None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(response["body"], "https://zappa:80/return/request/url")

    def test_exception_handler_on_web_request(self):
        """
        Ensure that app exceptions triggered by web requests use the exception_handler.
        """
        lh = LambdaHandler("tests.test_exception_handler_settings")

        event = {
            "body": "",
            "resource": "/{proxy+}",
            "requestContext": {},
            "queryStringParameters": {},
            "headers": {
                "Host": "1234567890.execute-api.us-east-1.amazonaws.com",
            },
            "pathParameters": {"proxy": "return/request/url"},
            "httpMethod": "GET",
            "stageVariables": {},
            "path": "/return/request/url",
        }

        mocked_exception_handler.assert_not_called()
        response = lh.handler(event, None)

        self.assertEqual(response["statusCode"], 500)
        mocked_exception_handler.assert_called()

    def test_wsgi_script_on_cognito_event_request(self):
        """
        Ensure that requests sent by cognito behave sensibly
        """
        lh = LambdaHandler("tests.test_wsgi_script_name_settings")

        event = {
            "version": "1",
            "region": "eu-west-1",
            "userPoolId": "region_poolID",
            "userName": "uuu-id-here",
            "callerContext": {
                "awsSdkVersion": "aws-sdk-js-2.149.0",
                "clientId": "client-id-here",
            },
            "triggerSource": "PreSignUp_SignUp",
            "request": {
                "userAttributes": {"email": "email@example.com"},
                "validationData": None,
            },
            "response": {
                "autoConfirmUser": False,
                "autoVerifyEmail": False,
                "autoVerifyPhone": False,
            },
        }

        response = lh.handler(event, None)

        self.assertEqual(response["response"]["autoConfirmUser"], False)

    def test_bot_triggered_event(self):
        """
        Ensure that bot triggered events are handled as in the settings
        """
        lh = LambdaHandler("tests.test_bot_handler_being_triggered")
        # from : https://docs.aws.amazon.com/lambda/latest/dg/eventsources.html#eventsources-lex
        event = {
            "messageVersion": "1.0",
            "invocationSource": "DialogCodeHook",
            "userId": "user-id specified in the POST request to Amazon Lex.",
            "sessionAttributes": {
                "key1": "value1",
                "key2": "value2",
            },
            "bot": {"name": "bot-name", "alias": "bot-alias", "version": "bot-version"},
            "outputDialogMode": "Text or Voice, based on ContentType request header in runtime API request",
            "currentIntent": {
                "name": "intent-name",
                "slots": {
                    "slot-name": "value",
                    "slot-name": "value",
                    "slot-name": "value",
                },
                "confirmationStatus": "None, Confirmed, or Denied (intent confirmation, if configured)",
            },
        }

        response = lh.handler(event, None)

        self.assertEqual(response, "Success")

    def test_exception_in_bot_triggered_event(self):
        """
        Ensure that bot triggered exceptions are handled as defined in the settings.
        """
        lh = LambdaHandler("tests.test_bot_exception_handler_settings")
        # from : https://docs.aws.amazon.com/lambda/latest/dg/eventsources.html#eventsources-lex
        event = {
            "messageVersion": "1.0",
            "invocationSource": "DialogCodeHook",
            "userId": "user-id specified in the POST request to Amazon Lex.",
            "sessionAttributes": {
                "key1": "value1",
                "key2": "value2",
            },
            "bot": {"name": "bot-name", "alias": "bot-alias", "version": "bot-version"},
            "outputDialogMode": "Text or Voice, based on ContentType request header in runtime API request",
            "currentIntent": {
                "name": "intent-name",
                "slots": {
                    "slot-name": "value",
                    "slot-name": "value",
                    "slot-name": "value",
                },
                "confirmationStatus": "None, Confirmed, or Denied (intent confirmation, if configured)",
            },
        }

        response = lh.lambda_handler(event, None)
        mocked_exception_handler.assert_called

    def test_wsgi_script_name_on_alb_event(self):
        """
        Ensure ALB-triggered events are properly handled by LambdaHandler
        ALB-forwarded events have a slightly different request structure than API-Gateway
        https://docs.aws.amazon.com/elasticloadbalancing/latest/application/lambda-functions.html
        """
        lh = LambdaHandler("tests.test_wsgi_script_name_settings")

        event = {
            "requestContext": {
                "elb": {
                    "targetGroupArn": "arn:aws:elasticloadbalancing:region:123456789012:targetgroup/my-target-group/6d0ecf831eec9f09"
                }
            },
            "httpMethod": "GET",
            "path": "/return/request/url",
            "queryStringParameters": {},
            "headers": {
                "accept": "text/html,application/xhtml+xml",
                "accept-language": "en-US,en;q=0.8",
                "content-type": "text/plain",
                "cookie": "cookies",
                "host": "1234567890.execute-api.us-east-1.amazonaws.com",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6)",
                "x-amzn-trace-id": "Root=1-5bdb40ca-556d8b0c50dc66f0511bf520",
                "x-forwarded-for": "72.21.198.66",
                "x-forwarded-port": "443",
                "x-forwarded-proto": "https",
            },
            "isBase64Encoded": False,
            "body": "",
        }
        response = lh.handler(event, None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(response["statusDescription"], "200 OK")
        self.assertEqual(response["isBase64Encoded"], False)
        self.assertEqual(
            response["body"],
            "https://1234567890.execute-api.us-east-1.amazonaws.com/return/request/url",
        )

    def test_merge_headers_no_multi_value(self):
        event = {"headers": {"a": "b"}}

        merged = merge_headers(event)
        self.assertEqual(merged["a"], "b")

    def test_merge_headers_combine_values(self):
        event = {
            "headers": {"a": "b", "z": "q"},
            "multiValueHeaders": {"a": ["c"], "x": ["y"]},
        }

        merged = merge_headers(event)
        self.assertEqual(merged["a"], "c")
        self.assertEqual(merged["x"], "y")
        self.assertEqual(merged["z"], "q")

    def test_merge_headers_no_single_value(self):
        event = {"multiValueHeaders": {"a": ["c", "d"], "x": ["y", "z", "f"]}}
        merged = merge_headers(event)
        self.assertEqual(merged["a"], "c, d")
        self.assertEqual(merged["x"], "y, z, f")

    def test_cloudwatch_subscription_event(self):
        """
        Test that events sent in the format used by CloudWatch logs via
        subscription filters are handled properly.
        The actual payload that Lambda receives is in the following format
        { "awslogs": {"data": "BASE64ENCODED_GZIP_COMPRESSED_DATA"} }
        https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/SubscriptionFilters.html
        """
        lh = LambdaHandler("tests.test_event_script_settings")

        event = {"awslogs": {"data": "some-data-not-important-for-test"}}
        response = lh.handler(event, None)

        self.assertEqual(response, True)
