APP_MODULE = 'tests.test_app'
APP_FUNCTION = 'hello_world'
DJANGO_SETTINGS = None
DEBUG = 'True'
LOG_LEVEL = 'DEBUG'
SCRIPT_NAME = 'hello_world'
DOMAIN = None
API_STAGE = 'ttt888'
PROJECT_NAME = 'ttt888'

REMOTE_ENV='s3://lmbda/test_env.json'
## test_env.json
#{
#    "hello": "world"
#}
#

AWS_EVENT_MAPPING = {
    'arn:aws:s3:1': 'test_settings.aws_s3_event',
    'arn:aws:sns:1': 'test_settings.aws_sns_event',
    'arn:aws:dynamodb:1': 'test_settings.aws_dynamodb_event',
    'arn:aws:kinesis:1': 'test_settings.aws_kinesis_event',
    'arn:aws:sqs:1': 'test_settings.aws_sqs_event'
}

ENVIRONMENT_VARIABLES={'testenv': 'envtest'}

AUTHORIZER_FUNCTION='test_settings.authorizer_event'


def prebuild_me():
    print("This is a prebuild script!")


def callback(self):
    print("this is a callback")


def aws_s3_event(event, content):
    return "AWS S3 EVENT"


def aws_sns_event(event, content):
    return "AWS SNS EVENT"

def aws_async_sns_event(arg1, arg2, arg3):
    return "AWS ASYNC SNS EVENT"


def aws_dynamodb_event(event, content):
    return "AWS DYNAMODB EVENT"


def aws_kinesis_event(event, content):
    return "AWS KINESIS EVENT"


def aws_sqs_event(event, content):
    return "AWS SQS EVENT"


def authorizer_event(event, content):
    return "AUTHORIZER_EVENT"


def command():
    print("command")
