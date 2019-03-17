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
    raise Exception('app exception')


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
        self.assertIsNone(LambdaHandler.run_function(no_args, 'e', 'c'))
        self.assertEqual(LambdaHandler.run_function(one_arg, 'e', 'c'), 'e')
        self.assertEqual(LambdaHandler.run_function(two_args, 'e', 'c'), ('e', 'c'))
        self.assertEqual(LambdaHandler.run_function(var_args, 'e', 'c'), ('e', 'c'))
        self.assertEqual(LambdaHandler.run_function(var_args_with_one, 'e', 'c'), ('e', 'c'))

        try:
            LambdaHandler.run_function(unsupported, 'e', 'c')
            self.fail('Exception expected')
        except RuntimeError:
            pass

    def test_run_fuction_with_type_hint(self):
        python_version = sys.version_info[0]
        # type hints are python 3 only
        if python_version == 3:
            scope = {}
            exec('def f_with_type_hint() -> None: return', scope)
            f_with_type_hint = scope['f_with_type_hint']
            self.assertIsNone(LambdaHandler.run_function(f_with_type_hint, 'e', 'c'))

    def test_wsgi_script_name_on_aws_url(self):
        """
        Ensure that requests to the amazonaws.com host for an API with a
        domain have the correct request.url
        """
        lh = LambdaHandler('tests.test_wsgi_script_name_settings')

        event = {
            'body': '',
            'resource': '/{proxy+}',
            'requestContext': {},
            'queryStringParameters': {},
            'headers': {
                'Host': '1234567890.execute-api.us-east-1.amazonaws.com',
            },
            'pathParameters': {
                'proxy': 'return/request/url'
            },
            'httpMethod': 'GET',
            'stageVariables': {},
            'path': '/return/request/url'
        }
        response = lh.handler(event, None)

        self.assertEqual(response['statusCode'], 200)
        self.assertEqual(
            response['body'],
            'https://1234567890.execute-api.us-east-1.amazonaws.com/dev/return/request/url'
        )

    def test_wsgi_script_name_on_domain_url(self):
        """
        Ensure that requests to the amazonaws.com host for an API with a
        domain have the correct request.url
        """
        lh = LambdaHandler('tests.test_wsgi_script_name_settings')

        event = {
            'body': '',
            'resource': '/{proxy+}',
            'requestContext': {},
            'queryStringParameters': {},
            'headers': {
                'Host': 'example.com',
            },
            'pathParameters': {
                'proxy': 'return/request/url'
            },
            'httpMethod': 'GET',
            'stageVariables': {},
            'path': '/return/request/url'
        }
        response = lh.handler(event, None)

        self.assertEqual(response['statusCode'], 200)
        self.assertEqual(
            response['body'],
            'https://example.com/return/request/url'
        )

    def test_wsgi_script_name_with_multi_value_header(self):
        """
        Ensure that requests generated with multivalued headers (such as
        from an ALB with Multi Valued Headers enabled) succeed.
        """
        lh = LambdaHandler('tests.test_wsgi_script_name_settings')

        event = {
            'body': '',
            'resource': '/{proxy+}',
            'requestContext': {},
            'queryStringParameters': {},
            'multiValueHeaders': {
                'Host': ['example.com'],
            },
            'pathParameters': {
                'proxy': 'return/request/url'
            },
            'httpMethod': 'GET',
            'stageVariables': {},
            'path': '/return/request/url'
        }
        response = lh.handler(event, None)
        self.assertEqual(response['statusCode'], 200)
        self.assertIn('multiValueHeaders', response)

    def test_wsgi_script_name_with_multi_value_querystring(self):
        """
        Ensure that requests generated with multivalue querystrings succeed.
        """
        lh = LambdaHandler('tests.test_wsgi_script_name_settings')

        event = {
            'body': '',
            'resource': '/{proxy+}',
            'requestContext': {},
            'multiValueQueryStringParameters': {
                'multi': ['value', 'qs']
            },
            'multiValueHeaders': {
                'Host': ['example.com'],
            },
            'pathParameters': {
                'proxy': 'return/request/url'
            },
            'httpMethod': 'GET',
            'stageVariables': {},
            'path': '/return/request/url'
        }
        response = lh.handler(event, None)

        self.assertEqual(response['statusCode'], 200)
        self.assertEqual(
            response['body'],
            'https://example.com/return/request/url?multi=value&multi=qs'
        )

    def test_wsgi_script_name_on_test_request(self):
        """
        Ensure that requests sent by the "Send test request" button behaves
        sensibly
        """
        lh = LambdaHandler('tests.test_wsgi_script_name_settings')

        event = {
            'body': '',
            'resource': '/{proxy+}',
            'requestContext': {},
            'queryStringParameters': {},
            'headers': {},
            'pathParameters': {
                'proxy': 'return/request/url'
            },
            'httpMethod': 'GET',
            'stageVariables': {},
            'path': '/return/request/url'
        }
        response = lh.handler(event, None)

        self.assertEqual(response['statusCode'], 200)
        self.assertEqual(
            response['body'],
            'https://zappa:80/return/request/url'
        )

    def test_exception_handler_on_web_request(self):
        """
        Ensure that app exceptions triggered by web requests use the exception_handler.
        """
        lh = LambdaHandler('tests.test_exception_handler_settings')

        event = {
            'body': '',
            'resource': '/{proxy+}',
            'requestContext': {},
            'queryStringParameters': {},
            'headers': {
                'Host': '1234567890.execute-api.us-east-1.amazonaws.com',
            },
            'pathParameters': {
                'proxy': 'return/request/url'
            },
            'httpMethod': 'GET',
            'stageVariables': {},
            'path': '/return/request/url'
        }

        mocked_exception_handler.assert_not_called()
        response = lh.handler(event, None)

        self.assertEqual(response['statusCode'], 500)
        mocked_exception_handler.assert_called()

    def test_wsgi_script_on_cognito_event_request(self):
        """
        Ensure that requests sent by cognito behave sensibly
        """
        lh = LambdaHandler('tests.test_wsgi_script_name_settings')

        event = {'version': '1',
                 'region': 'eu-west-1',
                 'userPoolId': 'region_poolID',
                 'userName': 'uuu-id-here',
                 'callerContext': {'awsSdkVersion': 'aws-sdk-js-2.149.0',
                                   'clientId': 'client-id-here'},
                 'triggerSource': 'PreSignUp_SignUp',
                 'request': {'userAttributes':
                                 {'email': 'email@example.com'}, 'validationData': None},
                 'response': {'autoConfirmUser': False,
                              'autoVerifyEmail': False,
                              'autoVerifyPhone': False}}

        response = lh.handler(event, None)

        self.assertEqual(response['response']['autoConfirmUser'], False)

    def test_bot_triggered_event(self):
        """
        Ensure that bot triggered events are handled as in the settings
        """
        lh = LambdaHandler('tests.test_bot_handler_being_triggered')
        # from : https://docs.aws.amazon.com/lambda/latest/dg/eventsources.html#eventsources-lex
        event = {
            "messageVersion": "1.0",
            "invocationSource": "DialogCodeHook",
            "userId": "user-id specified in the POST request to Amazon Lex.",
            "sessionAttributes": {
                "key1": "value1",
                "key2": "value2",
            },
            "bot": {
                "name": "bot-name",
                "alias": "bot-alias",
                "version": "bot-version"
            },
            "outputDialogMode": "Text or Voice, based on ContentType request header in runtime API request",
            "currentIntent": {
                "name": "intent-name",
                "slots": {
                    "slot-name": "value",
                    "slot-name": "value",
                    "slot-name": "value"
                },
                "confirmationStatus": "None, Confirmed, or Denied (intent confirmation, if configured)"
            }
        }

        response = lh.handler(event, None)

        self.assertEqual(response, 'Success')

    def test_exception_in_bot_triggered_event(self):
        """
        Ensure that bot triggered exceptions are handled as defined in the settings.
        """
        lh = LambdaHandler('tests.test_bot_exception_handler_settings')
        # from : https://docs.aws.amazon.com/lambda/latest/dg/eventsources.html#eventsources-lex
        event = {
            "messageVersion": "1.0",
            "invocationSource": "DialogCodeHook",
            "userId": "user-id specified in the POST request to Amazon Lex.",
            "sessionAttributes": {
                "key1": "value1",
                "key2": "value2",
            },
            "bot": {
                "name": "bot-name",
                "alias": "bot-alias",
                "version": "bot-version"
            },
            "outputDialogMode": "Text or Voice, based on ContentType request header in runtime API request",
            "currentIntent": {
                "name": "intent-name",
                "slots": {
                    "slot-name": "value",
                    "slot-name": "value",
                    "slot-name": "value"
                },
                "confirmationStatus": "None, Confirmed, or Denied (intent confirmation, if configured)"
            }
        }

        lh.lambda_handler(event, None)
        mocked_exception_handler.assert_called

    def test_ses_event_receipt(self):
        mock_input_record = {
            "eventSource": "aws:ses",
            "eventVersion": "1.0",
            "ses": {
                "receipt": {
                    "timestamp": "2015-09-11T20:32:33.936Z",
                    "processingTimeMillis": 222,
                    "recipients": ["recipient@example.com"],
                    "spamVerdict": {"status": "PASS"},
                    "virusVerdict": {"status": "PASS"},
                    "spfVerdict": {"status": "PASS"},
                    "dkimVerdict": {"status": "PASS"},
                    "action": {
                        "type": "Lambda",
                        "invocationType": "Event",
                        "functionArn": "arn:aws:ses:1",
                    }
                },
                "mail": {
                    "timestamp": "2015-09-11T20:32:33.936Z",
                    "source": "61967230-7A45-4A9D-BEC9-87CBCF2211C9@example.com",
                    "messageId": "d6iitobk75ur44p8kdnnp7g2n800",
                    "destination": [
                        "recipient@example.com"
                    ],
                    "headersTruncated": False,
                    "headers": [{
                        "name": "Return-Path",
                        "value": "<0000014fbe1c09cf-7cb9f704-7531-4e53-89a1-5fa9744f5eb6-000000@amazonses.com>"
                    }, {
                        "name": "Received",
                        "value": "from a9-183.smtp-out.amazonses.com (a9-183.smtp-out.amazonses.com [54.240.9.183]) by inbound-smtp.us-east-1.amazonaws.com with SMTP id d6iitobk75ur44p8kdnnp7g2n800 for recipient@example.com; Fri, 11 Sep 2015 20:32:33 +0000 (UTC)"
                    }, {
                        "name": "DKIM-Signature",
                        "value": "v=1; a=rsa-sha256; q=dns/txt; c=relaxed/simple; s=ug7nbtf4gccmlpwj322ax3p6ow6yfsug; d=amazonses.com; t=1442003552; h=From:To:Subject:MIME-Version:Content-Type:Content-Transfer-Encoding:Date:Message-ID:Feedback-ID; bh=DWr3IOmYWoXCA9ARqGC/UaODfghffiwFNRIb2Mckyt4=; b=p4ukUDSFqhqiub+zPR0DW1kp7oJZakrzupr6LBe6sUuvqpBkig56UzUwc29rFbJF hlX3Ov7DeYVNoN38stqwsF8ivcajXpQsXRC1cW9z8x875J041rClAjV7EGbLmudVpPX 4hHst1XPyX5wmgdHIhmUuh8oZKpVqGi6bHGzzf7g="
                    }, {
                        "name": "From",
                        "value": "sender@example.com"
                    }, {
                        "name": "To",
                        "value": "recipient@example.com"
                    }, {
                        "name": "Subject",
                        "value": "Example subject"
                    }, {
                        "name": "MIME-Version",
                        "value": "1.0"
                    }, {
                        "name": "Content-Type",
                        "value": "text/plain; charset=UTF-8"
                    }, {
                        "name": "Content-Transfer-Encoding",
                        "value": "7bit"
                    }, {
                        "name": "Date",
                        "value": "Fri, 11 Sep 2015 20:32:32 +0000"
                    }, {
                        "name": "Message-ID",
                        "value": "<61967230-7A45-4A9D-BEC9-87CBCF2211C9@example.com>"
                    }, {
                        "name": "X-SES-Outgoing",
                        "value": "2015.09.11-54.240.9.183"
                    }, {
                        "name": "Feedback-ID",
                        "value": "1.us-east-1.Krv2FKpFdWV+KUYw3Qd6wcpPJ4Sv/pOPpEPSHn2u2o4=:AmazonSES"
                    }],
                    "commonHeaders": {
                        "returnPath": "0000014fbe1c09cf-7cb9f704-7531-4e53-89a1-5fa9744f5eb6-000000@amazonses.com",
                        "from": ["sender@example.com"],
                        "date": "Fri, 11 Sep 2015 20:32:32 +0000",
                        "to": ["recipient@example.com"],
                        "messageId": "<61967230-7A45-4A9D-BEC9-87CBCF2211C9@example.com>",
                        "subject": "Example subject"
                    }
                }
            }
        }
        mock_event = {'Records': [mock_input_record]}
        lh = LambdaHandler('tests.test_ses_settings')
        result = lh.lambda_handler(mock_event, None)
        self.assertEqual(mock_event, result)

    #
    # Header merging - see https://github.com/Miserlou/Zappa/pull/1802.
    #
    def test_merge_headers_no_multi_value(self):
        event = {
            'headers': {
                'a': 'b'
            }
        }

        merged = merge_headers(event)
        self.assertEqual(merged['a'], 'b')

    def test_merge_headers_combine_values(self):
        event = {
            'headers': {
                'a': 'b',
                'z': 'q'
            },
            'multiValueHeaders': {
                'a': ['c'],
                'x': ['y']
            }
        }

        merged = merge_headers(event)
        self.assertEqual(merged['a'], 'c, b')
        self.assertEqual(merged['x'], 'y')
        self.assertEqual(merged['z'], 'q')

    def test_merge_headers_no_single_value(self):
        event = {
            'multiValueHeaders': {
                'a': ['c', 'd'],
                'x': ['y', 'z', 'f']
            }
        }
        merged = merge_headers(event)
        self.assertEqual(merged['a'], 'c, d')
        self.assertEqual(merged['x'], 'y, z, f')
