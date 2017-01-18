==============
Advanced Usage
==============

Rollback
========

You can also rollback the deployed code to a previous version by supplying the number of revisions to return to. For instance, to rollback to the version deployed 3 versions ago:

    $ zappa rollback production -n 3

Scheduling
==========

Zappa can be used to easily schedule functions to occur on regular intervals. Just list your functions and the expression to schedule them using `cron or rate syntax <http://docs.aws.amazon.com/lambda/latest/dg/tutorial-scheduled-events-schedule-expressions.html>`_ in your *zappa_settings.json* file:

::

    {
        "production": {
            ...
            "events": [{
                "function": "your_module.your_function", // The function to execute
                "expression": "rate(1 minute)" // When to execute it (in cron or rate format)
            }],
            ...
    }

And then:
::

    $ zappa schedule production

And now your function will execute every minute!

If you want to cancel these, you can simply use the 'unschedule' command:
::

    $ zappa unschedule production

And now your scheduled event rules are deleted.

Executing in Response to AWS Events
===================================

Similarly, you can have your functions execute in response to events that happen in the AWS ecosystem, such as S3 uploads, DynamoDB entries, Kinesis streams, and SNS messages.

In your *zappa_settings.json* file, define your `event sources <http://docs.aws.amazon.com/lambda/latest/dg/invoking-lambda-function.html>`_ and the function you wish to execute. For instance, this will execute *your_module.your_function* in response to new objects in your *my-bucket* S3 bucket. Note that *your_function* must accept *event* and *context* paramaters.

::

    {
        "production": {
            ...
            "events": [{
                "function": "your_module.your_function",
                "event_source": {
                    "arn":  "arn:aws:s3:::my-bucket",
                    "events": [
                        "s3:ObjectCreated:*"
                    ]
                }
            }],
            ...
        }
    }

And then:
::

    $ zappa schedule production

And now your function will execute every time a new upload appears in your bucket!

Undeploy
========

If you need to remove the API Gateway and Lambda function that you have previously published, you can simply:
::

    $ zappa undeploy production

You will be asked for confirmation before it executes.

Tailing Logs
============

You can watch the logs of a deployment by calling the ``tail`` management command.
::

    $ zappa tail production

Remote Function Invocation
==========================

You can execute any function in your application directly at any time by using the ``invoke`` command.

For instance, suppose you have a basic application in a file called "my_app.py", and you want to invoke a function in it called "my_function". Once your application is deployed, you can invoke that function at any time by calling:
::

    $ zappa invoke production 'my_app.my_function'

Any remote print statements made and the value the function returned will then be printed to your local console. **Nifty!**

Django Management Commands
==========================

As a convenience, Zappa can also invoke remote Django 'manage.py' commands with the ``manage`` command. For instance, to perform the basic Django status check:
::

    $ zappa manage production check

Obviously, this only works for Django projects which have their settings properly defined. (*Please note that commands which take over 30 seconds to execute may time-out. See* `this related issue <https://github.com/Miserlou/Zappa/issues/205#issuecomment-236391248>`_ *for a work-around.)* 

Keeping The Server Warm
=======================

Zappa will automatically set up a regularly occuring execution of your application in order to keep the Lambda function warm. This can be disabled via the 'keep_warm' setting.

Enabling CORS
=============

To enable Cross-Origin Resource Sharing (CORS) for your application, follow the `AWS "How to CORS" Guide <https://docs.aws.amazon.com/apigateway/latest/developerguide/how-to-cors.html>`_ to enable CORS via the API Gateway Console. Don't forget to enable CORS per parameter and re-deploy your API after making the changes!

Enabling Secure Endpoints on API Gateway
========================================

You can use the ``api_key_required`` setting to generate and assign an API key to all the routes of your API Gateway. After redeployment, you can then pass the provided key as a header called ``x-api-key`` to access the restricted endpoints. Without the ``x-api-key`` header, you will receive a 403. See `more information on API keys in the API Gateway <http://docs.aws.amazon.com/apigateway/latest/developerguide/how-to-api-keys.html>`_. 

You can enable IAM-based (v4 signing) authorization on an API by setting the ``authorization_type`` setting to ``AWS_IAM``. Your API will then require signed requests and access can be controlled via `IAM policy <https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-iam-policy-examples.html>`. Unsigned requests will receive a 403 response, as will requesters who are not authorized to access the API.

Deploying to a Domain With a Let's Encrypt Certificate
======================================================

If you want to use Zappa on a domain with a free Let's Encrypt certificate, you can follow `this guide <https://github.com/Miserlou/Zappa/blob/master/docs/domain_with_free_ssl.md>`_.

Setting Environment Variables
=============================

If you want to use environment variables to configure your application (which is especially useful for things like sensitive credentials), you can create a file and place it in an S3 bucket to which your Zappa application has access to. To do this, add the ``remote_env`` key to zappa_settings pointing to a file containing a flat JSON object, so that each key-value pair on the object will be set as an environment variable and value whenever a new lambda instance spins up.

For example, to ensure your application has access to the database credentials without storing them in your version control, you can add a file to S3 with the connection string and load it into the lambda environment using the ``remote_env`` configuration setting.

super-secret-config.json (uploaded to my-config-bucket):

::

    {
        "DB_CONNECTION_STRING": "super-secret:database"
    }

zappa_settings.json:

::

    {
        "dev": {
            ...
            "remote_env": "s3://my-config-bucket/super-secret-config.json",
        },
        ...
    }

Now in your application you can use:

::

    import os
    db_string = os.environ.get('DB_CONNECTION_STRING')
