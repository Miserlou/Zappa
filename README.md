<p align="center">
  <img src="http://i.imgur.com/oePnHJn.jpg" alt="Zappa Rocks!"/>
</p>

## Zappa - Serverless Python

[![Build Status](https://travis-ci.org/Miserlou/Zappa.svg)](https://travis-ci.org/Miserlou/Zappa)
[![Coverage](https://img.shields.io/coveralls/Miserlou/Zappa.svg)](https://coveralls.io/github/Miserlou/Zappa)
[![PyPI](https://img.shields.io/pypi/v/Zappa.svg)](https://pypi.python.org/pypi/zappa)
[![Slack](https://img.shields.io/badge/chat-slack-ff69b4.svg)](https://slack.zappa.io/)
[![Gun.io](https://img.shields.io/badge/made%20by-gun.io-blue.svg)](https://gun.io/)
[![Patreon](https://img.shields.io/badge/support-patreon-brightgreen.svg)](https://patreon.com/zappa)

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->


- [About](#about)
- [Installation and Configuration](#installation-and-configuration)
    - [Running the Initial Setup / Settings](#running-the-initial-setup--settings)
- [Basic Usage](#basic-usage)
    - [Initial Deployments](#initial-deployments)
    - [Updates](#updates)
    - [Rollback](#rollback)
    - [Scheduling](#scheduling)
    - [Undeploy](#undeploy)
    - [Package](#package)
    - [Template](#template)
    - [Status](#status)
    - [Tailing Logs](#tailing-logs)
    - [Remote Function Invocation](#remote-function-invocation)
    - [Django Management Commands](#django-management-commands)
    - [SSL Certification](#ssl-certification)
- [Executing in Response to AWS Events](#executing-in-response-to-aws-events)
- [Asynchronous Task Execution](#asynchronous-task-execution)
  - [Task Sources](#task-sources)
  - [Direct Invocation](#direct-invocation)
  - [Restrictions](#restrictions)
- [Advanced Settings](#advanced-settings)
    - [YAML Settings](#yaml-settings)
- [Advanced Usage](#advanced-usage)
    - [Keeping The Server Warm](#keeping-the-server-warm)
    - [Serving Static Files / Binary Uploads](#serving-static-files--binary-uploads)
    - [Enabling CORS](#enabling-cors)
    - [Large Projects](#large-projects)
    - [Enabling Bash Completion](#enabling-bash-completion)
    - [Enabling Secure Endpoints on API Gateway](#enabling-secure-endpoints-on-api-gateway)
      - [API Key](#api-key)
      - [IAM Policy](#iam-policy)
      - [API Gateway Authorizers](#api-gateway-authorizers)
      - [Cognito User Pool Authorizer](#cognito-user-pool-authorizer)
    - [Deploying to a Custom Domain Name with SSL Certificates](#deploying-to-a-custom-domain-name-with-ssl-certificates)
      - [Deploying to a Domain With a Let's Encrypt Certificate (DNS Auth)](#deploying-to-a-domain-with-a-lets-encrypt-certificate-dns-auth)
      - [Deploying to a Domain With a Let's Encrypt Certificate (HTTP Auth)](#deploying-to-a-domain-with-a-lets-encrypt-certificate-http-auth)
      - [Deploying to a Domain With Your Own SSL Certs](#deploying-to-a-domain-with-your-own-ssl-certs)
      - [Deploying to a Domain With AWS Certificate Manager](#deploying-to-a-domain-with-aws-certificate-manager)
    - [Setting Environment Variables](#setting-environment-variables)
      - [Local Environment Variables](#local-environment-variables)
      - [Remote Environment Variables](#remote-environment-variables)
    - [API Gateway Context Variables](#api-gateway-context-variables)
    - [Catching Unhandled Exceptions](#catching-unhandled-exceptions)
    - [Using Custom AWS IAM Roles and Policies](#using-custom-aws-iam-roles-and-policies)
    - [Globally Available Server-less Architectures](#globally-available-server-less-architectures)
    - [Raising AWS Service Limits](#raising-aws-service-limits)
    - [Using Zappa With Docker](#using-zappa-with-docker)
    - [Dead Letter Queues](#dead-letter-queues)
- [Zappa Guides](#zappa-guides)
- [Zappa in the Press](#zappa-in-the-press)
- [Sites Using Zappa](#sites-using-zappa)
- [Related Projects](#related-projects)
- [Hacks](#hacks)
- [Contributing](#contributing)
    - [Using a Local Repo](#using-a-local-repo)
- [Patrons](#patrons)
- [Support / Development / Training / Consulting](#support--development--training--consulting)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

## About

<p align="center">
  <a href="https://htmlpreview.github.io/?https://raw.githubusercontent.com/Miserlou/Talks/master/serverless-sf/big.quickstart.html"><img src="http://i.imgur.com/c23kDNT.png?1" alt="Zappa Slides"/></a>
</p>
<p align="center">
  <i>In a hurry? Click to see <a href="https://htmlpreview.github.io/?https://raw.githubusercontent.com/Miserlou/Talks/master/serverless-sf/big.quickstart.html">(now slightly out-dated) slides from Serverless SF</a>!</i>
</p>

**Zappa** makes it super easy to build and deploy all Python WSGI applications on AWS Lambda + API Gateway. Think of it as "serverless" web hosting for your Python apps. That means **infinite scaling**, **zero downtime**, **zero maintenance** - and at a fraction of the cost of your current deployments!

If you've got a Python web app (including Django and Flask apps), it's as easy as:

```
$ pip install zappa
$ zappa init
$ zappa deploy
```

and now you're server-less! _Wow!_

> What do you mean "serverless"?

Okay, so there still is a server - but it only has a _40 millisecond_ life cycle! Serverless in this case means **"without any permanent infrastructure."**

With a traditional HTTP server, the server is online 24/7, processing requests one by one as they come in. If the queue of incoming requests grows too large, some requests will time out. With Zappa, **each request is given its own virtual HTTP "server"** by Amazon API Gateway. AWS handles the horizontal scaling automatically, so no requests ever time out. Each request then calls your application from a memory cache in AWS Lambda and returns the response via Python's WSGI interface. After your app returns, the "server" dies.

Better still, with Zappa you only pay for the milliseconds of server time that you use, so it's many **orders of magnitude cheaper** than VPS/PaaS hosts like Linode or Heroku - and in most cases, it's completely free. Plus, there's no need to worry about load balancing or keeping servers online ever again.

It's great for deploying serverless microservices with frameworks like Flask and Bottle, and for hosting larger web apps and CMSes with Django. Or, you can use any WSGI-compatible app you like! You **probably don't need to change your existing applications** to use it, and you're not locked into using it.

Zappa also lets you build hybrid event-driven applications that can scale to **trillions of events** a year with **no additional effort** on your part! You also get **free SSL certificates**, **global app deployment**, **API access management**, **automatic security policy generation**, **precompiled C-extensions**, **auto keep-warms**, **oversized Lambda packages**, and **many other exclusive features**!

And finally, Zappa is **super easy to use**. You can deploy your application with a single command out of the box!

__Awesome!__

<p align="center">
  <img src="http://i.imgur.com/f1PJxCQ.gif" alt="Zappa Demo Gif"/>
</p>

## Installation and Configuration

_Before you begin, make sure you are running Python 2.7 or Python 3.6 and you have a valid AWS account and your [AWS credentials file](https://blogs.aws.amazon.com/security/post/Tx3D6U6WSFGOK2H/A-New-and-Standardized-Way-to-Manage-Credentials-in-the-AWS-SDKs) is properly installed._

**Zappa** can easily be installed through pip, like so:

    $ pip install zappa

Please note that Zappa _**must**_ be installed into your project's [virtual environment](http://docs.python-guide.org/en/latest/dev/virtualenvs/).

_(If you use [pyenv](https://github.com/yyuu/pyenv) and love to manage virtualenvs with **pyenv-virtualenv**, you just have to call `pyenv local [your_venv_name]` and it's ready. [Conda](http://conda.pydata.org/docs/) users should comment [here](https://github.com/Miserlou/Zappa/pull/108).)_

Next, you'll need to define your local and server-side settings.

#### Running the Initial Setup / Settings

**Zappa** can automatically set up your deployment settings for you with the `init` command:

    $ zappa init

This will automatically detect your application type (Flask/Django - Pyramid users [see here](https://github.com/Miserlou/Zappa/issues/278#issuecomment-241917956)) and help you define your deployment configuration settings. Once you finish initialization, you'll have a file named *zappa_settings.json* in your project directory defining your basic deployment settings. It will probably look something like this for most WSGI apps:

```javascript
{
    // The name of your stage
    "dev": {
        // The name of your S3 bucket
        "s3_bucket": "lmbda",

        // The modular python path to your WSGI application function.
        // In Flask and Bottle, this is your 'app' object.
        // Flask (your_module.py):
        // app = Flask()
        // Bottle (your_module.py):
        // app = bottle.default_app()
        "app_function": "your_module.app"
    }
}
```

or for Django:

```javascript
{
    "dev": { // The name of your stage
       "s3_bucket": "lmbda", // The name of your S3 bucket
       "django_settings": "your_project.settings" // The python path to your Django settings.
    }
}
```

You can define as many stages as your like - we recommend having _dev_, _staging_, and _production_.

Now, you're ready to deploy!

## Basic Usage

#### Initial Deployments

Once your settings are configured, you can package and deploy your application to a stage called "production" with a single command:

    $ zappa deploy production
    Deploying..
    Your application is now live at: https://7k6anj0k99.execute-api.us-east-1.amazonaws.com/production

And now your app is **live!** How cool is that?!

To explain what's going on, when you call `deploy`, Zappa will automatically package up your application and local virtual environment into a Lambda-compatible archive, replace any dependencies with versions [precompiled for Lambda](https://github.com/Miserlou/lambda-packages), set up the function handler and necessary WSGI Middleware, upload the archive to S3, create and manage the necessary Amazon IAM policies and roles, register it as a new Lambda function, create a new API Gateway resource, create WSGI-compatible routes for it, link it to the new Lambda function, and finally delete the archive from your S3 bucket. Handy!

#### Updates

If your application has already been deployed and you only need to upload new Python code, but not touch the underlying routes, you can simply:

    $ zappa update production
    Updating..
    Your application is now live at: https://7k6anj0k99.execute-api.us-east-1.amazonaws.com/production

This creates a new archive, uploads it to S3 and updates the Lambda function to use the new code, but doesn't touch the API Gateway routes.

#### Rollback

You can also `rollback` the deployed code to a previous version by supplying the number of revisions to return to. For instance, to rollback to the version deployed 3 versions ago:

    $ zappa rollback production -n 3

#### Scheduling

Zappa can be used to easily schedule functions to occur on regular intervals. This provides a much nicer, maintenance-free alternative to Celery!
These functions will be packaged and deployed along with your `app_function` and called from the handler automatically.
Just list your functions and the expression to schedule them using [cron or rate syntax](http://docs.aws.amazon.com/lambda/latest/dg/tutorial-scheduled-events-schedule-expressions.html) in your *zappa_settings.json* file:

```javascript
{
    "production": {
       ...
       "events": [{
           "function": "your_module.your_function", // The function to execute
           "expression": "rate(1 minute)" // When to execute it (in cron or rate format)
       }],
       ...
    }
}
```

And then:

    $ zappa schedule production

And now your function will execute every minute!

If you want to cancel these, you can simply use the `unschedule` command:

    $ zappa unschedule production

And now your scheduled event rules are deleted.

See the [example](example/) for more details.

##### Advanced Scheduling

Sometimes a function needs multiple expressions to describe its schedule. To set multiple expressions, simply list your functions, and the list of expressions to schedule them using [cron or rate syntax](http://docs.aws.amazon.com/lambda/latest/dg/tutorial-scheduled-events-schedule-expressions.html) in your *zappa_settings.json* file:

```javascript
{
    "production": {
       ...
       "events": [{
           "function": "your_module.your_function", // The function to execute
           "expressions": ["cron(0 20-23 ? * SUN-THU *)", "cron(0 0-8 ? * MON-FRI *)"] // When to execute it (in cron or rate format)
       }],
       ...
    }
}
```

This can be used to deal with issues arising from the UTC timezone crossing midnight during business hours in your local timezone.

It should be noted that overlapping expressions will not throw a warning, and should be checked for, to prevent duplicate triggering of functions.

#### Undeploy

If you need to remove the API Gateway and Lambda function that you have previously published, you can simply:

    $ zappa undeploy production

You will be asked for confirmation before it executes.

If you enabled CloudWatch Logs for your API Gateway service and you don't
want to keep those logs, you can specify the `--remove-logs` argument to purge the logs for your API Gateway and your Lambda function:

    $ zappa undeploy production --remove-logs

#### Package

If you want to build your application package without actually uploading and registering it as a Lambda function, you can use the `package` command:

    $ zappa package production

If you have a `zip` callback in your `callbacks` setting, this will also be invoked.

```javascript
{
    "production": { // The name of your stage
        "callbacks": {
            "zip": "my_app.zip_callback"// After creating the package
        }
    }
}
```

You can also specify the output filename of the package with `-o`:

    $ zappa package production -o my_awesome_package.zip

#### Template

Similarly, if you only want the API Gateway CloudFormation template, for use the `template` command:

    $ zappa template production --l your-lambda-arn -r your-role-arn

Note that you must supply your own Lambda ARN and Role ARNs in this case, as they may not have been created for you.

You can use get the JSON output directly with `--json`, and specify the output file with `--output`.

#### Status

If you need to see the status of your deployment and event schedules, simply use the `status` command.

    $ zappa status production

#### Tailing Logs

You can watch the logs of a deployment by calling the `tail` management command.

    $ zappa tail production

By default, this will show all log items. In addition to HTTP and other events, anything `print`ed to `stdout` or `stderr` will be shown in the logs.

You can use the argument `--http` to filter for HTTP requests, which will be in the Apache Common Log Format.

    $ zappa tail production --http

Similarly, you can do the inverse and only show non-HTTP events and log messages:

    $ zappa tail production --non-http

If you don't like the default log colors, you can turn them off with `--no-color`.

You can also limit the length of the tail with `--since`, which accepts a simple duration string:

    $ zappa tail production --since 4h # 4 hours
    $ zappa tail production --since 1m # 1 minute
    $ zappa tail production --since 1mm # 1 month

You can filter out the contents of the logs with `--filter`, like so:

    $ zappa tail production --http --filter "POST" # Only show POST HTTP requests

Note that this uses the [CloudWatch Logs filter syntax](http://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/FilterAndPatternSyntax.html).

#### Remote Function Invocation

You can execute any function in your application directly at any time by using the `invoke` command.

For instance, suppose you have a basic application in a file called "my_app.py", and you want to invoke a function in it called "my_function". Once your application is deployed, you can invoke that function at any time by calling:

    $ zappa invoke production 'my_app.my_function'

Any remote print statements made and the value the function returned will then be printed to your local console. **Nifty!**

You can also invoke interpretable Python 2.7 or Python 3.6 strings directly by using `--raw`, like so:

    $ zappa invoke production "print 1 + 2 + 3" --raw

#### Django Management Commands

As a convenience, Zappa can also invoke remote Django 'manage.py' commands with the `manage` command. For instance, to perform the basic Django status check:

    $ zappa manage production showmigrations admin

Obviously, this only works for Django projects which have their settings properly defined.

For commands which have their own arguments, you can also pass the command in as a string, like so:

    $ zappa manage production "shell --version"

Commands which require direct user input, such as `createsuperuser`, should be [replaced by commands](http://stackoverflow.com/a/26091252) which use `zappa <env> invoke --raw`.

_(Please note that commands which take over 30 seconds to execute may time-out. See [this related issue](https://github.com/Miserlou/Zappa/issues/205#issuecomment-236391248) for a work-around.)_

#### SSL Certification

If you want to use Zappa applications on a custom domain or subdomain, you'll need to supply a valid SSL certificate.

Zappa gives you three options here: Custom SSL certificates, AWS Certificate Manager-generated certificates, and Let's Encrypt certificates.

If your domain is located within an AWS Route 53 Hosted Zone and you've defined settings for `domain` and either `certificate`, `certificate_arn` or `lets_encrypt_key` (ex: `openssl genrsa 2048 > account.key`), all you need to do is:

    $ zappa certify production

And your domain will be verified, certified and registered!

More detailed instructions are available [in this handy guide](https://github.com/Miserlou/Zappa/blob/master/docs/domain_with_free_ssl_dns.md) and lower down in this README file.

## Executing in Response to AWS Events

Similarly, you can have your functions execute in response to events that happen in the AWS ecosystem, such as S3 uploads, DynamoDB entries, Kinesis streams, and SNS messages.

In your *zappa_settings.json* file, define your [event sources](http://docs.aws.amazon.com/lambda/latest/dg/invoking-lambda-function.html) and the function you wish to execute. For instance, this will execute `your_module.process_upload_function` in response to new objects in your `my-bucket` S3 bucket. Note that `process_upload_function` must accept `event` and `context` parameters.

```javascript
{
    "production": {
       ...
       "events": [{
            "function": "your_module.process_upload_function",
            "event_source": {
                  "arn":  "arn:aws:s3:::my-bucket",
                  "events": [
                    "s3:ObjectCreated:*" // Supported event types: http://docs.aws.amazon.com/AmazonS3/latest/dev/NotificationHowTo.html#supported-notification-event-types
                  ]
               }
            }],
       ...
    }
}
```

And then:

    $ zappa schedule production

And now your function will execute every time a new upload appears in your bucket!

To access the key's information in your application context, you'll want `process_upload_function` to look something like this:

```python
import boto3
s3_client = boto3.client('s3')

def process_upload_function(event, context):
    """
    Process a file upload.
    """

    # Get the uploaded file's information
    bucket = event['Records'][0]['s3']['bucket']['name'] # Will be `my-bucket`
    key = event['Records'][0]['s3']['object']['key'] # Will be the file path of whatever file was uploaded.

    # Get the bytes from S3
    s3_client.download_file(bucket, key, '/tmp/' + key) # Download this file to writable tmp space.
    file_bytes = open('/tmp/' + key).read()
```

Similarly, for a [Simple Notification Service](https://aws.amazon.com/sns/) event:

```javascript
        "events": [
            {
                "function": "your_module.your_function",
                "event_source": {
                    "arn":  "arn:aws:sns:::your-event-topic-arn",
                    "events": [
                        "sns:Publish"
                    ]
                }
            }
        ]
```

[DynamoDB](http://docs.aws.amazon.com/lambda/latest/dg/with-ddb.html) and [Kinesis](http://docs.aws.amazon.com/lambda/latest/dg/with-kinesis.html) are slightly different as it is not event based but pulling from a stream:

```javascript
       "events": [
           {
               "function": "replication.replicate_records",
               "event_source": {
                    "arn":  "arn:aws:dynamodb:us-east-1:1234554:table/YourTable/stream/2016-05-11T00:00:00.000",
                    "starting_position": "TRIM_HORIZON", // Supported values: TRIM_HORIZON, LATEST
                    "batch_size": 50, // Max: 1000
                    "enabled": true // Default is false
               }
           }
       ]
```

You can find more [example event sources here](http://docs.aws.amazon.com/lambda/latest/dg/eventsources.html).

## Asynchronous Task Execution

Zappa also now offers the ability to seamlessly execute functions asynchronously in a completely separate AWS Lambda instance!

For example, if you have a Flask API for ordering a pie, you can call your `bake` function seamlessly in a completely seperate Lambda instance by using the `zappa.async.task` decorator like so:

```python
from flask import Flask
from zappa.async import task
app = Flask(__name__)

@task
def make_pie():
    """ This takes a long time! """
    ingredients = get_ingredients()
    pie = bake(ingredients)
    deliver(pie)

@app.route('/api/order/pie')
def order_pie():
    """ This returns immediately! """
    make_pie()
    return "Your pie is being made!"

```

And that's it! Your API response will return immediately, while the `make_pie` function executes in a completely different Lambda instance.

### Task Sources

By default, this feature uses direct AWS Lambda invocation. You can instead use AWS Simple Notification Service as the task event source by using the `task_sns` decorator, like so:

```python
from zappa.async import task_sns
@task_sns
```

Using SNS also requires setting the following settings in your `zappa_settings`:

```javascript
{
  "dev": {
    ..
      "async_source": "sns", // Source of async tasks. Defaults to "lambda"
      "async_resources": true, // Create the SNS topic to use. Defaults to true.
    ..
    }
}
```

This will automatically create and subscribe to the SNS topic the code will use when you call the `zappa schedule` command.

Using SNS will also return a message ID in case you need to track your invocations.

### Direct Invocation

You can also use this functionality without a decorator by passing your function to `zappa.async.run`, like so:

```python
from zappa.async import run

run(your_function, args, kwargs) # Using Lambda
run(your_function, args, kwargs, service='sns') # Using SNS
```

### Remote Invocations

By default, Zappa will use lambda's current function name and current AWS region. If you wish to invoke a lambda with
  a different function name/region or invoke your lambda from outside of lambda, you must specify the 
  `remote_aws_lambda_function_name` and `remote_aws_region` arguments so that the application knows which function and 
  region to use. For example, if some part of our pizza making application had to live on an EC2 instance, but we 
  wished to call the make_pie() function on its own Lambda instance, we would do it as follows:
  
 ```python
@task(remote_aws_lambda_function_name='pizza-pie-prod', remote_aws_region='us-east-1')
def make_pie():
    """ This takes a long time! """
    ingredients = get_ingredients()
    pie = bake(ingredients)
    deliver(pie)

```
If those task() parameters were not used, then EC2 would execute the function locally. These same
 `remote_aws_lambda_function_name` and `remote_aws_region` arguments can be used on the zappa.async.run() function as well.

### Restrictions

The following restrictions to this feature apply:

* Functions must have a clean import path -- i.e. no closures, lambdas, or methods.
* `args` and `kwargs` must be JSON-serializable.
* The JSON-serialized arguments must be within the size limits for Lambda (128K) or SNS (256K) events.

All of this code is still backwards-compatible with non-Lambda environments - it simply executes in a blocking fashion and returns the result.

## Advanced Settings

There are other settings that you can define in your local settings
to change Zappa's behavior. Use these at your own risk!

```javascript
 {
    "dev": {
        "api_key_required": false, // enable securing API Gateway endpoints with x-api-key header (default False)
        "api_key": "your_api_key_id", // optional, use an existing API key. The option "api_key_required" must be true to apply
        "apigateway_enabled": true, // Set to false if you don't want to create an API Gateway resource. Default true.
        "apigateway_description": "My funky application!", // Define a custom description for the API Gateway console. Default None.
        "assume_policy": "my_assume_policy.json", // optional, IAM assume policy JSON file
        "attach_policy": "my_attach_policy.json", // optional, IAM attach policy JSON file
        "async_source": "sns", // Source of async tasks. Defaults to "lambda"
        "async_resources": true, // Create the SNS topic to use. Defaults to true.
        "aws_environment_variables" : {"your_key": "your_value"}, // A dictionary of environment variables that will be available to your deployed app via AWS Lambdas native environment variables. See also "environment_variables" and "remote_env" . Default {}.
        "aws_kms_key_arn": "your_aws_kms_key_arn", // Your AWS KMS Key ARN
        "aws_region": "aws-region-name", // optional, uses region set in profile or environment variables if not set here,
        "binary_support": true, // Enable automatic MIME-type based response encoding through API Gateway. Default true.
        "callbacks": { // Call custom functions during the local Zappa deployment/update process
            "settings": "my_app.settings_callback", // After loading the settings
            "zip": "my_app.zip_callback", // After creating the package
            "post": "my_app.post_callback", // After command has executed
        },
        "cache_cluster_enabled": false, // Use APIGW cache cluster (default False)
        "cache_cluster_size": 0.5, // APIGW Cache Cluster size (default 0.5)
        "cache_cluster_ttl": 300, // APIGW Cache Cluster time-to-live (default 300)
        "cache_cluster_encrypted": false, // Whether or now APIGW Cache Cluster encrypts data (default False)
        "certificate": "my_cert.crt", // SSL certificate file location. Used to manually certify a custom domain
        "certificate_key": "my_key.key", // SSL key file location. Used to manually certify a custom domain
        "certificate_chain": "my_cert_chain.pem", // SSL certificate chain file location. Used to manually certify a custom domain
        "certificate_arn": "arn:aws:acm:us-east-1:1234512345:certificate/aaaa-bbb-cccc-dddd", // ACM certificate ARN.
        "cloudwatch_log_level": "OFF", // Enables/configures a level of logging for the given staging. Available options: "OFF", "INFO", "ERROR", default "OFF". C
        "cloudwatch_data_trace": false, // Logs all data about received events. Default false.
        "cloudwatch_metrics_enabled": false, // Additional metrics for the API Gateway. Default false.
        "context_header_mappings": { "HTTP_header_name": "API_Gateway_context_variable" }, // A dictionary mapping HTTP header names to API Gateway context variables
        "cors": true, // Enable Cross-Origin Resource Sharing. Default false. If true, simulates the "Enable CORS" button on the API Gateway console. Can also be a dictionary specifying lists of "allowed_headers", "allowed_methods", and string of "allowed_origin"
        "dead_letter_arn": "arn:aws:<sns/sqs>:::my-topic/queue", // Optional Dead Letter configuration for when Lambda async invoke fails thrice
        "debug": true, // Print Zappa configuration errors tracebacks in the 500. Default true.
        "delete_local_zip": true, // Delete the local zip archive after code updates. Default true.
        "delete_s3_zip": true, // Delete the s3 zip archive. Default true.
        "django_settings": "your_project.production_settings", // The modular path to your Django project's settings. For Django projects only.
        "domain": "yourapp.yourdomain.com", // Required if you're using a domain
        "environment_variables": {"your_key": "your_value"}, // A dictionary of environment variables that will be available to your deployed app. See also "remote_env" and "aws_environment_variables". Default {}.
        "events": [
            {   // Recurring events
                "function": "your_module.your_recurring_function", // The function to execute
                "expression": "rate(1 minute)" // When to execute it (in cron or rate format)
            },
            {   // AWS Reactive events
                "function": "your_module.your_reactive_function", // The function to execute
                "event_source": {
                    "arn":  "arn:aws:s3:::my-bucket", // The ARN of this event source
                    "events": [
                        "s3:ObjectCreated:*" // The specific event to execute in response to.
                    ]
                }
            }
        ],
        "exception_handler": "your_module.report_exception", // function that will be invoked in case Zappa sees an unhandled exception raised from your code
        "exclude": ["*.gz", "*.rar"], // A list of regex patterns to exclude from the archive. To exclude boto3 and botocore (available in an older version on Lambda), add "boto3*" and "botocore*".
        "extends": "stage_name", // Duplicate and extend another stage's settings. For example, `dev-asia` could extend from `dev-common` with a different `s3_bucket` value.
        "extra_permissions": [{ // Attach any extra permissions to this policy. Default None
            "Effect": "Allow",
            "Action": ["rekognition:*"], // AWS Service ARN
            "Resource": "*"
        }],
        "iam_authorization": true, // optional, use IAM to require request signing. Default false. Note that enabling this will override the authorizer configuration.
        "include": ["your_special_library_to_load_at_handler_init"], // load special libraries into PYTHONPATH at handler init that certain modules cannot find on path
        "authorizer": {
            "function": "your_module.your_auth_function", // Local function to run for token validation. For more information about the function see below.
            "arn": "arn:aws:lambda:<region>:<account_id>:function:<function_name>", // Existing Lambda function to run for token validation.
            "result_ttl": 300, // Optional. Default 300. The time-to-live (TTL) period, in seconds, that specifies how long API Gateway caches authorizer results. Currently, the maximum TTL value is 3600 seconds.
            "token_source": "Authorization", // Optional. Default 'Authorization'. The name of a custom authorization header containing the token that clients submit as part of their requests.
            "validation_expression": "^Bearer \\w+$", // Optional. A validation expression for the incoming token, specify a regular expression.
        },
        "keep_warm": true, // Create CloudWatch events to keep the server warm. Default true.
        "keep_warm_expression": "rate(4 minutes)", // How often to execute the keep-warm, in cron and rate format. Default 4 minutes.
        "lambda_description": "Your Description", // However you want to describe your project for the AWS console. Default "Zappa Deployment".
        "lambda_handler": "your_custom_handler", // The name of Lambda handler. Default: handler.lambda_handler
        "lets_encrypt_key": "s3://your-bucket/account.key", // Let's Encrypt account key path. Can either be an S3 path or a local file path.
        "log_level": "DEBUG", // Set the Zappa log level. Can be one of CRITICAL, ERROR, WARNING, INFO and DEBUG. Default: DEBUG
        "manage_roles": true, // Have Zappa automatically create and define IAM execution roles and policies. Default true. If false, you must define your own IAM Role and role_name setting.
        "memory_size": 512, // Lambda function memory in MB. Default 512.
        "prebuild_script": "your_module.your_function", // Function to execute before uploading code
        "profile_name": "your-profile-name", // AWS profile credentials to use. Default 'default'.
        "project_name": "MyProject", // The name of the project as it appears on AWS. Defaults to a slugified `pwd`.
        "remote_env": "s3://my-project-config-files/filename.json", // optional file in s3 bucket containing a flat json object which will be used to set custom environment variables.
        "role_name": "MyLambdaRole", // Name of Zappa execution role. Default <project_name>-<env>-ZappaExecutionRole. To use a different, pre-existing policy, you must also set manage_roles to false.
        "route53_enabled": true, // Have Zappa update your Route53 Hosted Zones when certifying with a custom domain. Default true.
        "runtime": "python2.7", // Python runtime to use on Lambda. Can be one of "python2.7" or "python3.6". Defaults to whatever the current Python being used is.
        "s3_bucket": "dev-bucket", // Zappa zip bucket,
        "slim_handler": false, // Useful if project >50M. Set true to just upload a small handler to Lambda and load actual project from S3 at runtime. Default false.
        "settings_file": "~/Projects/MyApp/settings/dev_settings.py", // Server side settings file location,
        "timeout_seconds": 30, // Maximum lifespan for the Lambda function (default 30, max 300.)
        "touch": false, // GET the production URL upon initial deployment (default True)
        "use_precompiled_packages": true, // If possible, use C-extension packages which have been pre-compiled for AWS Lambda. Default true.
        "vpc_config": { // Optional VPC configuration for Lambda function
            "SubnetIds": [ "subnet-12345678" ], // Note: not all availability zones support Lambda!
            "SecurityGroupIds": [ "sg-12345678" ]
        }
    }
}
```

#### YAML Settings

If you prefer YAML over JSON, you can also use a `zappa_settings.yml`, like so:

```yaml
---
dev:
  app_function: your_module.your_app
  s3_bucket: your-code-bucket
  events:
  - function: your_module.your_function
    event_source:
      arn: arn:aws:s3:::your-event-bucket
      events:
      - s3:ObjectCreated:*
```

You can also supply a custom settings file at any time with the `-s` argument, ex:

```
$ zappa deploy dev -s my-custom-settings.yml
```

Similarly, you can supply a `zappa_settings.toml` file:

```toml
[dev]
  app_function = "your_module.your_app"
  s3_bucket = "your-code-bucket"
```

## Advanced Usage

#### Keeping The Server Warm

Zappa will automatically set up a regularly occurring execution of your application in order to keep the Lambda function warm. This can be disabled via the `keep_warm` setting.

#### Serving Static Files / Binary Uploads

Zappa is now able to serve and receive binary files, as detected by their MIME-type.

However, generally Zappa is designed for running your application code, not for serving static web assets. If you plan on serving custom static assets in your web application (CSS/JavaScript/images/etc.,), you'll likely want to use a combination of AWS S3 and AWS CloudFront.

Your web application framework will likely be able to handle this for you automatically. For Flask, there is [Flask-S3](https://github.com/e-dard/flask-s3), and for Django, there is [Django-Storages](https://django-storages.readthedocs.io/en/latest/).

Similarly, you may want to design your application so that static binary uploads go [directly to S3](http://docs.aws.amazon.com/AWSJavaScriptSDK/guide/browser-examples.html#Uploading_a_local_file_using_the_File_API), which then triggers an event response defined in your `events` setting! That's thinking serverlessly!

#### Enabling CORS

The simplest way to enable CORS (Cross-Origin Resource Sharing) for in your Zappa application is to set `cors` to `true` in your Zappa settings file and updating, which is the equivalent of pushing the "Enable CORS" button in the AWS API Gateway console. This is disabled by default, but you may wish to enable it for APIs which are accessed from other domains, etc. It may also conflict with `binary_support`, so you should set that to `false` in your settings.

You can also simply handle CORS directly in your application. Your web framework will probably have an extention to do this, such as [django-cors-headers](https://github.com/ottoyiu/django-cors-headers) or [Flask-CORS](https://github.com/corydolphin/flask-cors). Using these will make your code more portable.

#### Large Projects

AWS currently limits Lambda zip sizes to 50 megabytes. If your project is larger than that, set `slim_handler: true` in your `zappa_settings.json`. In this case, your fat application package will be replaced with a small handler-only package. The handler file then pulls the rest of the large project down from S3 at run time! The initial load of the large project may add to startup overhead, but the difference should be minimal on a warm lambda function. Note that this will also eat into the _memory_ space of your application function.

#### Enabling Bash Completion

Bash completion can be enabled by adding the following to your .bashrc:

```bash
  eval "$(register-python-argcomplete zappa)"
```

`register-python-argcomplete` is provided by the argcomplete Python package. If this package was installed in a virtualenv
then the command must be run there. Alternatively you can execute:

  activate-global-python-argcomplete --dest=- > file

The file's contents should then be sourced in e.g. ~/.bashrc.

#### Enabling Secure Endpoints on API Gateway

##### API Key

You can use the `api_key_required` setting to generate and assign an API key to all the routes of your API Gateway. After redeployment, you can then pass the provided key as a header called `x-api-key` to access the restricted endpoints. Without the `x-api-key` header, you will receive a 403. You'll also need to manually associate this API key with your usage plan in the AWS console. [More information on API keys in the API Gateway](http://docs.aws.amazon.com/apigateway/latest/developerguide/how-to-api-keys.html).

##### IAM Policy

You can enable IAM-based (v4 signing) authorization on an API by setting the `iam_authorization` setting to `true`. Your API will then require signed requests and access can be controlled via [IAM policy](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-iam-policy-examples.html). Unsigned requests will receive a 403 response, as will requesters who are not authorized to access the API. Enabling this will override the Authorizer configuration (see below).

##### API Gateway Authorizers
If you deploy an API endpoint with Zappa, you can take advantage of [API Gateway Authorizers](http://docs.aws.amazon.com/apigateway/latest/developerguide/use-custom-authorizer.html) to implement a token-based authentication - all you need to do is to provide a function to create the required output, Zappa takes care of the rest. A good start for the function is the [AWS Labs blueprint example](https://github.com/awslabs/aws-apigateway-lambda-authorizer-blueprints/blob/master/blueprints/python/api-gateway-authorizer-python.py).

If you are wondering for what you would use an Authorizer, here are some potential use cases:

1. Call out to OAuth provider
2. Decode a JWT token inline
3. Lookup in a self-managed DB (for example DynamoDB)

Zappa can be configured to call a function inside your code to do the authorization, or to call some other existing lambda function (which lets you share the authorizer between multiple lambdas). You control the behavior by specifying either the `arn` or `function_name` values in the `authorizer` settings block.

##### Cognito User Pool Authorizer

You can also use AWS Cognito User Pool Authorizer by adding:

```javascript
{
    "authorizer": {
        "type": "COGNITO_USER_POOLS",
        "provider_arns": [
            "arn:aws:cognito-idp:{region}:{account_id}:userpool/{user_pool_id}"
        ]
    }
}
```

#### Deploying to a Custom Domain Name with SSL Certificates

##### Deploying to a Domain With a Let's Encrypt Certificate (DNS Auth)

If you want to use Zappa on a domain with a free Let's Encrypt certificate using automatic Route 53 based DNS Authentication, you can follow [this handy guide](https://github.com/Miserlou/Zappa/blob/master/docs/domain_with_free_ssl_dns.md).

##### Deploying to a Domain With a Let's Encrypt Certificate (HTTP Auth)

If you want to use Zappa on a domain with a free Let's Encrypt certificate using HTTP Authentication, you can follow [this guide](https://github.com/Miserlou/Zappa/blob/master/docs/domain_with_free_ssl_http.md).

However, it's now far easier to use Route 53-based DNS authentication, which will allow you to use a Let's Encrypt certificate with a single `$ zappa certify` command.

##### Deploying to a Domain With Your Own SSL Certs

1. The first step is to create a custom domain and obtain your SSL cert / key / bundle.
2. Ensure you have set the `domain` setting within your Zappa settings JSON - this will avoid problems with the Base Path mapping between the Custom Domain and the API invoke URL, which gets the Stage Name appended in the URI
3. Add the paths to your SSL cert / key / bundle to the `certificate`, `certificate_key`, and `certificate_chain` settings, respectively, in your Zappa settings JSON
4. Set `route53_enabled` to `false` if you plan on using your own DNS provider, and not an AWS Route53 Hosted zone.
5. Deploy or update your app using Zappa
6. Run `$ zappa certify` to upload your certificates and register the custom domain name with your API gateway.

##### Deploying to a Domain With AWS Certificate Manager

1. Verify your domain in the AWS Ceriticate Manager console.
2. In the console, request a certificate for your domain or subdomain (`sub.yourdomain.tld`), or request a wildcard domain (`*.yourdomain.tld`).
3. Copy the entire ARN of that certificate and place it in the Zappa setting `certificate_arn`.
4. Set your desired domain in the `domain` setting.
5. Call `$ zappa certify` to create and associate the API Gateway distribution using that ceritficate.

#### Setting Environment Variables

##### Local Environment Variables

If you want to set local environment variables for a deployment stage, you can simply set them in your `zappa_settings.json`:

```javascript
{
    "dev": {
        ...
        "environment_variables": {
            "your_key": "your_value"
        }
    },
    ...
}
```

You can then access these inside your application with:

```python
import os
your_value = os.environ.get('your_key')
```

If your project needs to be aware of the type of environment you're deployed to, you'll also be able to get `SERVERTYPE` (AWS Lambda), `FRAMEWORK` (Zappa), `PROJECT` (your project name) and `STAGE` (_dev_, _production_, etc.) variables at any time.

##### Remote AWS Environment Variables

If you want to use native AWS Lambda environment variables you can use the `aws_environment_variables` configuration setting. These are useful as you can easily change them via the AWS Lambda console or cli at runtime. They are also useful for storing sensitive credentials and to take advantage of KMS encryption of environment variables.


During development, you can add your Zappa defined variables to your locally running app by, for example, using the below (for Django, to manage.py).

```python
if 'SERVERTYPE' in os.environ and os.environ['SERVERTYPE'] == 'AWS Lambda':
    import json
    import os
    json_data = open('zappa_settings.json')
    env_vars = json.load(json_data)['dev']['environment_variables']
    for key, val in env_vars.items():
        os.environ[key] = val

``` 

##### Remote Environment Variables
=======
Any environment variables that you have set outside of Zappa (via AWS Lambda console or cli) will remain as they are when running `update`, unless they are also in `aws_environment_variables`, in which case the remote value will be overwritten by the one in the settings file.

If you are using KMS-encrypted AWS environment variables, you can set your KMS Key ARN in the `aws_kms_key_arn` setting. Make sure that the values you set are encrypted in such case.

_Note: if you rely on these as well as `environment_variables`, and you have the same key names, then those in `environment_variables` will take precedence as they are injected in the lambda handler._

##### Remote Environment Variables (via an S3 file)

_S3 remote environment variables were added to Zappa before AWS introduced native environment variables for Lambda (via the console and cli). Before going down this route check if above make more sense for your usecase._


If you want to use remote environment variables to configure your application (which is especially useful for things like sensitive credentials), you can create a file and place it in an S3 bucket to which your Zappa application has access to. To do this, add the `remote_env` key to zappa_settings pointing to a file containing a flat JSON object, so that each key-value pair on the object will be set as an environment variable and value whenever a new lambda instance spins up.

For example, to ensure your application has access to the database credentials without storing them in your version control, you can add a file to S3 with the connection string and load it into the lambda environment using the `remote_env` configuration setting.

#####
super-secret-config.json (uploaded to my-config-bucket):
```javascript
{
    "DB_CONNECTION_STRING": "super-secret:database"
}
```

zappa_settings.json:
```javascript
{
    "dev": {
        ...
        "remote_env": "s3://my-config-bucket/super-secret-config.json",
    },
    ...
}
```

Now in your application you can use:
```python
import os
db_string = os.environ.get('DB_CONNECTION_STRING')
```

#### API Gateway Context Variables

If you want to map an API Gateway context variable (http://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-mapping-template-reference.html) to an HTTP header you can set up the mapping in `zappa_settings.json`:

```javascript
{
    "dev": {
        ...
        "context_header_mappings": { 
            "HTTP_header_name": "API_Gateway_context_variable" 
        }
    },
    ...
}
```

For example, if you want to expose the $context.identity.cognitoIdentityId variable as the HTTP header CognitoIdentityId, and $context.stage as APIStage, you would have:

```javascript
{
    "dev": {
        ...
        "context_header_mappings": { 
            "CognitoIdentityId": "identity.cognitoIdentityId",
            "APIStage": "stage"
        }
    },
    ...
}
```

#### Catching Unhandled Exceptions

By default, if an _unhandled_ exception happens in your code, Zappa will just print the stacktrace into a CloudWatch log. If you wish to use an external reporting tool to take note of those exceptions, you can use the `exception_handler` configuration option.

zappa_settings.json:
```javascript
{
    "dev": {
        ...
        "exception_handler": "your_module.unhandled_exceptions",
    },
    ...
}
```

The function has to accept three arguments: exception, event, and context:

your_module.py
```python
def unhandled_exception(e, event, context):
    send_to_raygun(e, event)  # gather data you need and send
    return True # Prevent invocation retry
```
You may still need a similar exception handler inside your application, this is just a way to catch exception which happen at the Zappa/WSGI layer (typically event-based invocations, misconfigured settings, bad Lambda packages, and permissions issues).

By default, AWS Lambda will attempt to retry an event based (non-API Gateway, e.g. CloudWatch) invocation if an exception has been thrown. However, you can prevent this by returning True, as in example above, so Zappa that will not re-raise the uncaught exception, thus preventing AWS Lambda from retrying the current invocation.

#### Using Custom AWS IAM Roles and Policies

By default, the Zappa client will create and manage the necessary IAM policies and roles to execute Zappa applications. However, if you're using Zappa in a corporate environment or as part of a continuous integration, you may instead want to manually manage your remote execution policies instead. (You can specify which _local_ profile to use for deploying your Zappa application by defining the `profile_name` setting, which will correspond to a profile in your AWS credentials file.)

To manually define the permissions policy of your Zappa execution role, you must define the following in your *zappa_settings.json*:

```javascript
{
    "dev": {
        ...
        "manage_roles": false, // Disable Zappa client managing roles.
        "role_name": "MyLambdaRole", // Name of your Zappa execution role. Default <project_name>-<env>-ZappaExecutionRole.
        ...
    },
    ...
}
```

Ongoing discussion about the minimum policy requirements necessary for a Zappa deployment [can be found here](https://github.com/Miserlou/Zappa/issues/244).

If you only need to add a few permissions to the default Zappa execution policy, you can use the `extra_permissions` setting like so:

```javascript
{
    "dev": {
        ...
        "extra_permissions": [{ // Attach any extra permissions to this policy.
            "Effect": "Allow",
            "Action": ["rekognition:*"], // AWS Service ARN
            "Resource": "*"
        }]
    },
    ...
}
```

#### Globally Available Server-less Architectures


<p align="center">
  <a href="https://htmlpreview.github.io/?https://github.com/Miserlou/Talks/blob/master/serverless-london/global.html#0"><img src="http://i.imgur.com/oR61Qau.png" alt="Global Zappa Slides"/></a>
</p>
<p align="center">
  <i>Click to see <a href="https://htmlpreview.github.io/?https://github.com/Miserlou/Talks/blob/master/serverless-london/global.html#0">slides from ServerlessConf London</a>!</i>
</p>

During the `init` process, you will be given the option to deploy your application "globally." This will allow you to deploy your application to all available AWS regions simultaneously in order to provide a consistent global speed, increased redundancy, data isolation, and legal compliance. You can also choose to deploy only to "primary" locations, the AWS regions with `-1` in their names.

To learn more about these capabilities, see [these slides](https://htmlpreview.github.io/?https://github.com/Miserlou/Talks/blob/master/serverless-london/global.html#0) from ServerlessConf London.

#### Raising AWS Service Limits

Out of the box, AWS sets a limit of [1000 concurrent executions](http://docs.aws.amazon.com/lambda/latest/dg/limits.html) for your functions. If you start to breach these limits, you may start to see errors like `ClientError: An error occurred (LimitExceededException) when calling the PutTargets.."` or something similar.

To avoid this, you can file a [service ticket](https://console.aws.amazon.com/support/home#/) with Amazon to raise your limits up to the many tens of thousands of concurrent executions which you may need. This is a fairly common practice with Amazon, designed to prevent you from accidentally creating extremely expensive bug reports. So, before raising your service limits, make sure that you don't have any rogue scripts which could accidentally create tens of thousands of parallel executions that you don't want to pay for.

#### Using Zappa With Docker

If Docker is part of your team's CI, testing, or deployments, you may want to check out [this handy guide](https://blog.zappa.io/posts/simplified-aws-lambda-deployments-with-docker-and-zappa) on using Zappa with Docker.

#### Dead Letter Queues

If you want to utilise [AWS Lambda's Dead Letter Queue feature](http://docs.aws.amazon.com/lambda/latest/dg/dlq.html) simply add the key `dead_letter_arn`, with the value being the complete ARN to the corresponding SNS topic or SQS queue in your `zappa_settings.json`.

You must have already created the corresponding SNS/SQS topic/queue, and the Lambda function execution role must have been provisioned with read/publish/sendMessage access to the DLQ resource.

## Zappa Guides

* [Django-Zappa tutorial (screencast)](https://www.youtube.com/watch?v=plUrbPN0xc8&feature=youtu.be).
* [Using Django-Zappa, Part 1](https://serverlesscode.com/post/zappa-wsgi-for-python/).
* [Using Django-Zappa, Part 2: VPCs](https://serverlesscode.com/post/zappa-wsgi-for-python-pt-2/).
* [Building Serverless Microservices with Zappa and Flask](https://gun.io/blog/serverless-microservices-with-zappa-and-flask/)
* [Zappa で Hello World するまで (Japanese)](http://qiita.com/satoshi_iwashita/items/505492193317819772c7)
* [How to Deploy Zappa with CloudFront, RDS and VPC](https://jinwright.net/how-deploy-serverless-wsgi-app-using-zappa/)
* [Secure 'Serverless' File Uploads with AWS Lambda, S3, and Zappa](http://blog.stratospark.com/secure-serverless-file-uploads-with-aws-lambda-s3-zappa.html)
* [First Steps with AWS Lambda, Zappa and Python](https://andrich.blog/2017/02/12/first-steps-with-aws-lambda-zappa-flask-and-python/)
* [Deploy a Serverless WSGI App using Zappa, CloudFront, RDS, and VPC](https://docs.google.com/presentation/d/1aYeOMgQl4V_fFgT5VNoycdXtob1v6xVUWlyxoTEiTw0/edit#slide=id.p)
* [AWS: Deploy Alexa Ask Skills with Flask-Ask and Zappa](https://developer.amazon.com/blogs/post/8e8ad73a-99e9-4c0f-a7b3-60f92287b0bf/New-Alexa-Tutorial-Deploy-Flask-Ask-Skills-to-AWS-Lambda-with-Zappa)
* [Guide to using Django with Zappa](https://edgarroman.github.io/zappa-django-guide/)
* _Your guide here?_

## Zappa in the Press

* _[Zappa Serves Python, Minus the Servers](http://www.infoworld.com/article/3031665/application-development/zappa-serves-python-web-apps-minus-the-servers.html)_
* _[Zappa lyfter serverlösa applikationer med Python](http://computersweden.idg.se/2.2683/1.649895/zappa-lyfter-python)_
* _[Interview: Rich Jones on Zappa](https://serverlesscode.com/post/rich-jones-interview-django-zappa/)_
* [Top 10 Python Libraries of 2016](https://tryolabs.com/blog/2016/12/20/top-10-python-libraries-of-2016/)

## Sites Using Zappa

* [Zappa.io](https://www.zappa.io) - A simple Zappa homepage
* [Zappatista!](https://blog.zappa.io) - The official Zappa blog!
* [Mailchimp Signup Utility](https://github.com/sasha42/Mailchimp-utility) - A microservice for adding people to a mailing list via API.
* [Zappa Slack Inviter](https://github.com/Miserlou/zappa-slack-inviter) - A tiny, server-less service for inviting new users to your Slack channel.
* [Serverless Image Host](https://github.com/Miserlou/serverless-imagehost) - A thumbnailing service with Flask, Zappa and Pillow.
* [Gigger](https://www.gigger.rocks/) - The live music industry's search engine
* [Zappa BitTorrent Tracker](https://github.com/Miserlou/zappa-bittorrent-tracker) - An experimental server-less BitTorrent tracker. Work in progress.
* [JankyGlance](https://github.com/Miserlou/JankyGlance) - A server-less Yahoo! Pipes replacement.
* [LambdaMailer](https://github.com/tryolabs/lambda-mailer) - A server-less endpoint for processing a contact form.
* [Voter Registration Microservice](https://topics.arlingtonva.us/2016/11/voter-registration-search-microservice/) - Official backup to to the Virginia Department of Elections portal.
* [FreePoll Online](https://www.freepoll.online) - A simple and awesome say for groups to make decisions.
* [PasteOfCode](https://paste.ofcode.org/) - A Zappa-powered paste bin.
* And many more, including banks, governments, startups, enterprises and schools!

Are you using Zappa? Let us know and we'll list your site here!

## Related Projects

* [lambda-packages](http://github.com/Miserlou/lambda-packages) - Precompiled C-extension packages for AWS Lambda. Used automatically by Zappa.
* [Mackenzie](http://github.com/Miserlou/Mackenzie) - AWS Lambda Infection Toolkit
* [NoDB](https://github.com/Miserlou/NoDB) - A simple, server-less, Pythonic object store based on S3.
* [zappa-cms](http://github.com/Miserlou/zappa-cms) - A tiny server-less CMS for busy hackers. Work in progress.
* [flask-ask](https://github.com/johnwheeler/flask-ask) - A framework for building Amazon Alexa applications. Uses Zappa for deployments.
* [zappa-file-widget](https://github.com/anush0247/zappa-file-widget) - A Django plugin for supporting binary file uploads in Django on Zappa.
* [zops](https://github.com/bjinwright/zops) - Utilities for teams and continuous integrations using Zappa.
* [cookiecutter-mobile-backend](https://github.com/narfman0/cookiecutter-mobile-backend/) - A `cookiecutter` Django project with Zappa and S3 uploads support.
* [zappa-examples](https://github.com/narfman0/zappa-examples/) - Flask, Django, image uploads, and more!
* [Zappa Docker Image](https://github.com/danielwhatmuff/zappa) - A Docker image for running Zappa locally, based on Lambda Docker.
* [zappa-dashing](https://github.com/nikos/zappa-dashing) - Monitor your AWS environment (health/metrics) with Zappa and CloudWatch.
* [s3env](https://github.com/cameronmaske/s3env) - Manipulate a remote Zappa environment variable key/value JSON object file in an S3 bucket through the CLI.
* [zappa_resize_image_on_fly](https://github.com/wobeng/zappa_resize_image_on_fly) - Resize images on the fly using Flask, Zappa, Pillow, and OpenCV-python.
* [gdrive-lambda](https://github.com/richiverse/gdrive-lambda) - pass json data to a csv file for end users who use Gdrive across the organization.
* [travis-build-repeat](https://github.com/bcongdon/travis-build-repeat) - Repeat TravisCI builds to avoid stale test results.
* [wunderskill-alexa-skill](https://github.com/mcrowson/wunderlist-alexa-skill) - An Alexa skill for adding to a Wunderlist.
* [xrayvision](https://github.com/mathom/xrayvision) - Utilities and wrappers for using AWS X-Ray with Zappa.

## Hacks

Zappa goes quite far beyond what Lambda and API Gateway were ever intended to handle. As a result, there are quite a few hacks in here that allow it to work. Some of those include, but aren't limited to..

* ~~~Using VTL to map body, headers, method, params and query strings into JSON, and then turning that into valid WSGI.~~~
* ~~~Attaching response codes to response bodies, Base64 encoding the whole thing, using that as a regex to route the response code, decoding the body in VTL, and mapping the response body to that.~~~
* ~~~Packing and _Base58_ encoding multiple cookies into a single cookie because we can only map one kind.~~~
* Forcing the case permutations of "Set-Cookie" in order to return multiple headers at the same time.
* ~~~Turning cookie-setting 301/302 responses into 200 responses with HTML redirects, because we have no way to set headers on redirects.~~~

## Contributing

This project is still young, so there is still plenty to be done. Contributions are more than welcome!

Please file tickets for discussion before submitting patches. Pull requests should target `master` and should leave Zappa in a "shippable" state if merged.

If you are adding a non-trivial amount of new code, please include a functioning test in your PR. For AWS calls, we use the `placebo` library, which you can learn to use [in their README](https://github.com/garnaat/placebo#usage-as-a-decorator). The test suite will be run by [Travis CI](https://travis-ci.org/Miserlou/Zappa) once you open a pull request.

Please include the GitHub issue or pull request URL that has discussion related to your changes as a comment in the code ([example](https://github.com/Miserlou/Zappa/blob/fae2925431b820eaedf088a632022e4120a29f89/zappa/zappa.py#L241-L243)). This greatly helps for project maintainability, as it allows us to trace back use cases and explain decision making. Similarly, please make sure that you meet all of the requiments listed in the [pull request template](https://raw.githubusercontent.com/Miserlou/Zappa/master/.github/PULL_REQUEST_TEMPLATE.md).

Please feel free to work on any open ticket, especially any ticket marked with the "help-wanted" label. If you get stuck or want to discuss an issue further, please join [our Slack channel](https://slack.zappa.io), where you'll find a community of smart and interesting people working dilligently on hard problems.

#### Using a Local Repo

To use the git HEAD, you *probably can't* use `pip install -e `. Instead, you should clone the repo to your machine and then `pip install /path/to/zappa/repo` or `ln -s /path/to/zappa/repo/zappa zappa` in your local project.

## Patrons

If you or your company uses **Zappa**, please consider giving what you can to support the ongoing development of the project!

You can become a patron by **[visiting our Patreon page](https://patreon.com/zappa)**.

Zappa is currently supported by these awesome individuals and companies:

  * Nathan Lawrence
  * LaunchLab
  * Sean Paley

Thank you very, very much!

## Merch

<br />
<p align="center">
  <a href="https://blog.zappa.io/posts/weve-got-merch-now-introducing-zappa-tshirts"><img src="https://i.imgur.com/jYZ7aUR.png" alt="Merch!"/></a>
</p>

## Support / Development / Training / Consulting

Do you need help with..

  * Porting existing Flask and Django applications to Zappa?
  * Building new applications and services that scale infinitely?
  * Reducing your operations and hosting costs?
  * Adding new custom features into Zappa?
  * Training your team to use AWS and other server-less paradigms?

Good news! We're currently available for remote and on-site consulting for small, large and enterprise teams. Please contact <miserlou@gmail.com> with your needs and let's work together!

<br />
<p align="center">
  <a href="https://gun.io"><img src="http://i.imgur.com/M7wJipR.png" alt="Made by Gun.io"/></a>
</p>
