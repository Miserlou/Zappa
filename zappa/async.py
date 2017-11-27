"""
Zappa Async Tasks

Example:
```
from zappa.async import task

@task(service='sns')
def my_async_func(*args, **kwargs):
    dosomething()
```

For SNS, you can also pass an `arn` argument to task() which will specify which SNS path to send it to.

Without `service='sns'`, the default service is 'lambda' which will call the method in an asynchronous
lambda call.

The following restrictions apply:
* function must have a clean import path -- i.e. no closures, lambdas, or methods.
* args and kwargs must be JSON-serializable.
* The JSON-serialized form must be within the size limits for Lambda (128K) or SNS (256K) events.

Discussion of this comes from:
    https://github.com/Miserlou/Zappa/issues/61
    https://github.com/Miserlou/Zappa/issues/603
    https://github.com/Miserlou/Zappa/pull/694
    https://github.com/Miserlou/Zappa/pull/732
    https://github.com/Miserlou/Zappa/issues/840

## Full lifetime of an asynchronous dispatch:

1. In a file called `foo.py`, there is the following code:

```
   from zappa.async import task

   @task
   def my_async_func(*args, **kwargs):
       return sum(args)
```

2. The decorator desugars to:
   `my_async_func = task(my_async_func)`

3. Somewhere else, the code runs:
   `res = my_async_func(1,2)`
   really calls task's `_run_async(1,2)`
      with `func` equal to the original `my_async_func`
   If we are running in Lambda, this runs:
      LambdaAsyncResponse().send('foo.my_async_func', (1,2), {})
   and returns the LambdaAsyncResponse instance to the local
   context.  That local context, can, e.g. test for `res.sent`
   to confirm it was dispatched correctly.

4. LambdaAsyncResponse.send invoked the currently running
   AWS Lambda instance with the json message:

```
   { "command": "zappa.async.route_lambda_task",
     "task_path": "foo.my_async_func",
     "args": [1,2],
     "kwargs": {}
   }
```

5. The new lambda instance is invoked with the message above,
   and Zappa runs its usual bootstrapping context, and inside
   zappa.handler, the existence of the 'command' key in the message
   dispatches the full message to zappa.async.route_lambda_task, which
   in turn calls `run_message(message)`

6. `run_message` loads the task_path value to load the `func` from `foo.py`.
   We should note that my_async_func is wrapped by @task in this new
   context, as well.  However, @task also decorated `my_async_func.sync()`
   to run the original function synchronously.

   `run_message` duck-types the method and finds the `.sync` attribute
   and runs that instead -- thus we do not infinitely dispatch.

   If `my_async_func` had code to dispatch other functions inside its
   synchronous portions (or even call itself recursively), those *would*
   be dispatched asynchronously, unless, of course, they were called
   by: `my_async_func.sync(1,2)` in which case it would run synchronously
   and in the current lambda function.

"""

import boto3
import botocore
from functools import update_wrapper, wraps
import importlib
import inspect
import json
import os
import uuid
import time

from .utilities import get_topic_name

try:
    from zappa_settings import ASYNC_RESPONSE_TABLE
except ImportError:
    ASYNC_RESPONSE_TABLE = None

# Declare these here so they're kept warm.
try:
    aws_session = boto3.Session()
    LAMBDA_CLIENT = aws_session.client('lambda')
    SNS_CLIENT = aws_session.client('sns')
    STS_CLIENT = aws_session.client('sts')
    DYNAMODB_CLIENT = aws_session.client('dynamodb')
except botocore.exceptions.NoRegionError as e: # pragma: no cover
    # This can happen while testing on Travis, but it's taken care  of
    # during class initialization.
    pass


##
# Response and Exception classes
##

class AsyncException(Exception): # pragma: no cover
    """ Simple exception class for async tasks. """
    pass


class LambdaAsyncResponse(object):
    """
    Base Response Dispatcher class
    Can be used directly or subclassed if the method to send the message is changed.
    """
    def __init__(self, lambda_function_name=None, aws_region=None, capture_response=False, **kwargs):
        """ """
        if kwargs.get('boto_session'):
            self.client = kwargs.get('boto_session').client('lambda')
        else:  # pragma: no cover
            self.client = LAMBDA_CLIENT

        self.lambda_function_name = lambda_function_name
        self.aws_region = aws_region
        if capture_response:
            if ASYNC_RESPONSE_TABLE is None:
                print(
                    "Warning! Attempted to capture a response without "
                    "async_response_table configured in settings (you won't "
                    "capture async responses)."
                )
                capture_response = False
                self.response_id = "MISCONFIGURED"

            else:
                self.response_id = str(uuid.uuid4())
        else:
            self.response_id = None

        self.capture_response = capture_response


    def send(self, task_path, args, kwargs):
        """
        Create the message object and pass it to the actual sender.
        """
        message = {
                'task_path': task_path,
                'capture_response': self.capture_response,
                'response_id': self.response_id,
                'args': args,
                'kwargs': kwargs
            }
        self._send(message)
        return self

    def _send(self, message):
        """
        Given a message, directly invoke the lamdba function for this task.
        """
        message['command'] = 'zappa.async.route_lambda_task'
        payload = json.dumps(message).encode('utf-8')
        if len(payload) > 128000: # pragma: no cover
            raise AsyncException("Payload too large for async Lambda call")
        self.response = self.client.invoke(
                                    FunctionName=self.lambda_function_name,
                                    InvocationType='Event', #makes the call async
                                    Payload=payload
                                )
        self.sent = (self.response.get('StatusCode', 0) == 202)

class SnsAsyncResponse(LambdaAsyncResponse):
    """
    Send a SNS message to a specified SNS topic
    Serialise the func path and arguments
    """
    def __init__(self, lambda_function_name=None, aws_region=None, capture_response=False, **kwargs):

        self.lambda_function_name = lambda_function_name
        self.aws_region=aws_region

        if kwargs.get('boto_session'):
            self.client = kwargs.get('boto_session').client('sns')
        else: # pragma: no cover
            self.client = SNS_CLIENT


        if kwargs.get('arn'):
            self.arn = kwargs.get('arn')
        else:
            if kwargs.get('boto_session'):
                sts_client = kwargs.get('boto_session').client('sts')
            else:
                sts_client = STS_CLIENT
            AWS_ACCOUNT_ID = sts_client.get_caller_identity()['Account']
            self.arn = 'arn:aws:sns:{region}:{account}:{topic_name}'.format(
                                    region=self.aws_region,
                                    account=AWS_ACCOUNT_ID,
                                    topic_name=get_topic_name(self.lambda_function_name)
                                )

        # Issue: https://github.com/Miserlou/Zappa/issues/1209
        # TODO: Refactor
        self.capture_response = capture_response
        if capture_response:
            if ASYNC_RESPONSE_TABLE is None:
                print(
                    "Warning! Attempted to capture a response without "
                    "async_response_table configured in settings (you won't "
                    "capture async responses)."
                )
                capture_response = False
                self.response_id = "MISCONFIGURED"

            else:
                self.response_id = str(uuid.uuid4())
        else:
            self.response_id = None

        self.capture_response = capture_response


    def _send(self, message):
        """
        Given a message, publish to this topic.
        """
        message['command'] = 'zappa.async.route_sns_task'
        payload = json.dumps(message).encode('utf-8')
        if len(payload) > 256000: # pragma: no cover
            raise AsyncException("Payload too large for SNS")
        self.response = self.client.publish(
                                TargetArn=self.arn,
                                Message=payload
                            )
        self.sent = self.response.get('MessageId')

##
# Aync Routers
##

ASYNC_CLASSES = {
    'lambda': LambdaAsyncResponse,
    'sns': SnsAsyncResponse,
}


def route_lambda_task(event, context):
    """
    Deserialises the message from event passed to zappa.handler.run_function
    imports the function, calls the function with args
    """
    message = event
    return run_message(message)


def route_sns_task(event, context):
    """
    Gets SNS Message, deserialises the message,
    imports the function, calls the function with args
    """
    record = event['Records'][0]
    message = json.loads(
            record['Sns']['Message']
        )
    return run_message(message)


def run_message(message):
    """
    Runs a function defined by a message object with keys:
    'task_path', 'args', and 'kwargs' used by lambda routing
    and a 'command' in handler.py
    """
    if message.get('capture_response', False):
        DYNAMODB_CLIENT.put_item(
            TableName=ASYNC_RESPONSE_TABLE,
            Item={
                'id': {'S': str(message['response_id'])},
                'ttl': {'N': str(int(time.time()+600))},
                'async_status': {'S': 'in progress'},
                'async_response': {'S': str(json.dumps('N/A'))},
            }
        )

    func = import_and_get_task(message['task_path'])
    if hasattr(func, 'sync'):
        response = func.sync(
            *message['args'],
            **message['kwargs']
        )
    else:
        response = func(
            *message['args'],
            **message['kwargs']
        )

    if message.get('capture_response', False):
        DYNAMODB_CLIENT.update_item(
            TableName=ASYNC_RESPONSE_TABLE,
            Key={'id': {'S': str(message['response_id'])}},
            UpdateExpression="SET async_response = :r, async_status = :s",
            ExpressionAttributeValues={
                ':r': {'S': str(json.dumps(response))},
                ':s': {'S': 'complete'},
            },
        )

    return response

##
# Execution interfaces and classes
##


def run(func, args=[], kwargs={}, service='lambda', capture_response=False,
        remote_aws_lambda_function_name=None, remote_aws_region=None, **task_kwargs):
    """
    Instead of decorating a function with @task, you can just run it directly.
    If you were going to do func(*args, **kwargs), then you will call this:

    import zappa.async.run
    zappa.async.run(func, args, kwargs)

    If you want to use SNS, then do:

    zappa.async.run(func, args, kwargs, service='sns')

    and other arguments are similar to @task
    """
    lambda_function_name = remote_aws_lambda_function_name or os.environ.get('AWS_LAMBDA_FUNCTION_NAME')
    aws_region = remote_aws_region or os.environ.get('AWS_REGION')

    task_path = get_func_task_path(func)
    return ASYNC_CLASSES[service](lambda_function_name=lambda_function_name,
                                  aws_region=aws_region,
                                  capture_response=capture_response,
                                  **task_kwargs).send(task_path, args, kwargs)


# Handy:
# http://stackoverflow.com/questions/10294014/python-decorator-best-practice-using-a-class-vs-a-function
# However, this needs to pass inspect.getargspec() in handler.py which does not take classes
# Wrapper written to take optional arguments
# http://chase-seibert.github.io/blog/2013/12/17/python-decorator-optional-parameter.html
def task(*args, **kwargs):
    """Async task decorator so that running

    Args:
        func (function): the function to be wrapped
            Further requirements:
            func must be an independent top-level function.
                 i.e. not a class method or an anonymous function
        service (str): either 'lambda' or 'sns'
        remote_aws_lambda_function_name (str): the name of a remote lambda function to call with this task
        remote_aws_region (str): the name of a remote region to make lambda/sns calls against

    Returns:
        A replacement function that dispatches func() to
        run asynchronously through the service in question
    """

    func = None
    if len(args) == 1 and callable(args[0]):
        func = args[0]

    if not kwargs:  # Default Values
        service = 'lambda'
        lambda_function_name = os.environ.get('AWS_LAMBDA_FUNCTION_NAME')
        aws_region = os.environ.get('AWS_REGION')

    else:  # Arguments were passed
        service = kwargs.get('service', 'lambda')
        lambda_function_name = kwargs.get('remote_aws_lambda_function_name') or os.environ.get('AWS_LAMBDA_FUNCTION_NAME')
        aws_region = kwargs.get('remote_aws_region') or os.environ.get('AWS_REGION')

    capture_response = kwargs.get('capture_response', False)

    def func_wrapper(func):

        task_path = get_func_task_path(func)

        @wraps(func)
        def _run_async(*args, **kwargs):
            """
            This is the wrapping async function that replaces the function
            that is decorated with @task.
            Args:
                These are just passed through to @task's func

            Assuming a valid service is passed to task() and it is run
            inside a Lambda process (i.e. AWS_LAMBDA_FUNCTION_NAME exists),
            it dispatches the function to be run through the service variable.
            Otherwise, it runs the task synchronously.

            Returns:
                In async mode, the object returned includes state of the dispatch.
                For instance

                When outside of Lambda, the func passed to @task is run and we
                return the actual value.
            """
            if (service in ASYNC_CLASSES) and (lambda_function_name):
                send_result = ASYNC_CLASSES[service](lambda_function_name=lambda_function_name,
                                                     aws_region=aws_region,
                                                     capture_response=capture_response).send(task_path, args, kwargs)
                return send_result
            else:
                return func(*args, **kwargs)

        update_wrapper(_run_async, func)

        _run_async.service = service
        _run_async.sync = func

        return _run_async

    return func_wrapper(func) if func else func_wrapper


def task_sns(func):
    """
    SNS-based task dispatcher. Functions the same way as task()
    """
    return task(func, service='sns')


##
# Utility Functions
##

def import_and_get_task(task_path):
    """
    Given a modular path to a function, import that module
    and return the function.
    """
    module, function = task_path.rsplit('.', 1)
    app_module = importlib.import_module(module)
    app_function = getattr(app_module, function)
    return app_function


def get_func_task_path(func):
    """
    Format the modular task path for a function via inspection.
    """
    module_path = inspect.getmodule(func).__name__
    task_path = '{module_path}.{func_name}'.format(
                                        module_path=module_path,
                                        func_name=func.__name__
                                    )
    return task_path


def get_async_response(response_id):
    """
    Get the response from the async table
    """
    response = DYNAMODB_CLIENT.get_item(
        TableName=ASYNC_RESPONSE_TABLE,
        Key={'id': {'S': str(response_id)}}
    )
    if 'Item' not in response:
        return None

    return {
        'status': response['Item']['async_status']['S'],
        'response': json.loads(response['Item']['async_response']['S']),
    }
