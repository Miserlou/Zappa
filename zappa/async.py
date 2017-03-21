import os
import json
import importlib
import inspect
import boto3


"""
Example:
from zappa.async import task

@task(service='sns')
def my_async_func(*args, **kwargs):
    dosomething()

res = my_async_func.delay(*args, **kwargs)
if res.sent:
    print('It was dispatched! Who knows what the function result will be!')

For sns, you can also pass an `arn` argument to task() which will specify which SNS path to send it to.

Without service='sns', the default service is 'lambda' which will call the method in an asynchronous
lambda call.

"""


AWS_REGION = os.environ.get('AWS_REGION')
AWS_LAMBDA_FUNCTION_NAME = os.environ.get('AWS_LAMBDA_FUNCTION_NAME')


class LambdaAsyncResponse(object):
    def __init__(self, **kwargs):
        self.client = boto3.client('lambda')

    def send(self, task_path, *args, **kwargs):
        message = {
            'task_path': task_path,
            'args': args,
            'kwargs': kwargs
        }
        self._send(message)
        return self

    def _send(self, message):
        message['command'] = 'zappa.async.route_lambda_task'

        self.response = self.client.invoke(
            FunctionName=AWS_LAMBDA_FUNCTION_NAME,
            InvocationType='Event', #makes the call async
            Payload=json.dumps(message).encode('utf-8'))

        self.sent = (response.get('StatusCode', 0) == 202)


class SnsAsyncResponse(LambdaAsyncResponse):
    """
    Send a SNS message to a specified SNS topic
    Serialise the func path and arguments
    """
    def __init__(self, **kwargs):
        self.client = boto3.client('sns')
        if kwargs.get('arn'):
            self.arn = kwargs.get('arn')
        else:
            stsclient = boto3.client('sts')
            AWS_ACCOUNT_ID = stsclient.get_caller_identity()['Account']
            self.arn = 'arn:aws:sns:{region}:{account}:{lambda_name}-zappa-async'.format(
                region=AWS_REGION, account=AWS_ACCOUNT_ID,
                lambda_name=AWS_LAMBDA_FUNCTION_NAME
            )

    def _send(self, message):
        self.response = client.publish(
            TargetArn=self.arn, Message=json.dumps(message),
        )
        self.sent = self.response.get('MessageId')


ASYNC_CLASSES = {
    'lambda': LambdaAsyncResponse,
    'sns': SnsAsyncResponse,
}

def import_and_get_task(task_path):
    """
    Given a modular path to a function, import that module
    and return the function.
    """
    module, function = task_path.rsplit('.', 1)
    app_module = importlib.import_module(module)
    app_function = getattr(app_module, function)
    return app_function


def route_lambda_task(event, context):
    """
    Deserialises the message from event passed to zappa.handler.run_function
    imports the function, calls the function with args
    """
    message = event
    func = import_and_get_task(message['task_path'])
    return func(
        *message['args'], **message['kwargs']
    )


def route_sns_task(event, context):
    """
    Gets SNS Message, deserialises the message,
    imports the function, calls the function with args
    """
    record = event['Records'][0]
    message = json.loads(
        record['Sns']['Message']
    )
    func = import_and_get_task(message['task_path'])
    return func(
        *message['args'], **message['kwargs']
    )


def task(service='lambda', **task_kwargs):
    """
    Async task decorator for a function.
    Serialises and dispatches the task to SNS.
    Lambda subscribes to SNS topic and gets this message
    Lambda routes the message to the same function
    Example:
        @task(service='sns')
        def my_async_func(*args, **kwargs):
            dosomething()
        my_async_func.delay(*args, **kwargs)
    """
    def _delay(func, task_path):
        def _delay_inner(*args, **kwargs):
            if service in ASYNC_CLASSES:
                return ASYNC_CLASSES[service](**task_kwargs).send(task_path, *args, **kwargs)
            return func(*args, **kwargs)
        return _delay_inner

    def _wrap(func):
        module_path = inspect.getmodule(func).__name__
        task_path = '{module_path}.{func_name}'.format(
            module_path=module_path,
            func_name=func.__name__
        )
        func.delay = _delay(func, task_path)
        return func

    return _wrap
