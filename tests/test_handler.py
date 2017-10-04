import unittest
from zappa.handler import LambdaHandler


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


class TestZappa(unittest.TestCase):

    def test_run_function(self):
        self.assertIsNone(LambdaHandler.run_function(no_args, 'e', 'c'))
        self.assertEqual(LambdaHandler.run_function(one_arg, 'e', 'c'), 'e')
        self.assertEqual(LambdaHandler.run_function(two_args, 'e', 'c'), ('e', 'c'))
        self.assertEqual(LambdaHandler.run_function(var_args, 'e', 'c'), ('e', 'c'))
        self.assertEqual(LambdaHandler.run_function(var_args_with_one, 'e', 'c'), ('e', 'c'))

        try:
            LambdaHandler.run_function(unsupported, 'e', 'c')
            self.fail('Exception expected')
        except RuntimeError as e:
            pass

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
