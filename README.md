<p align="center">
  <img src="http://i.imgur.com/oePnHJn.jpg" alt="Zappa Rocks!"/>
</p>

## Zappa - Serverless Python Web Services

[![Build Status](https://travis-ci.org/Miserlou/Zappa.svg)](https://travis-ci.org/Miserlou/Zappa)
[![Coverage](https://img.shields.io/coveralls/Miserlou/Zappa.svg)](https://coveralls.io/github/Miserlou/Zappa)
[![Requirements Status](https://requires.io/github/Miserlou/Zappa/requirements.svg?branch=master)](https://requires.io/github/Miserlou/Zappa/requirements/?branch=master)
[![PyPI](https://img.shields.io/pypi/v/Zappa.svg)](https://pypi.python.org/pypi/zappa)
[![Slack](https://img.shields.io/badge/chat-slack-ff69b4.svg)](https://slack.zappa.io/)

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
    - [Executing in Response to AWS Events](#executing-in-response-to-aws-events)
    - [Undeploy](#undeploy)
    - [Status](#status)
    - [Tailing Logs](#tailing-logs)
    - [Remote Function Invocation](#remote-function-invocation)
    - [Django Management Commands](#django-management-commands)
    - [Let's Encrypt SSL Domain Certification and Installation](#lets-encrypt-ssl-domain-certification-and-installation)
- [Advanced Settings](#advanced-settings)
- [Advanced Usage](#advanced-usage)
    - [Keeping The Server Warm](#keeping-the-server-warm)
    - [Serving Static Files / Binary Uploads](#serving-static-files--binary-uploads)
    - [Enabling CORS](#enabling-cors)
    - [Enabling Secure Endpoints on API Gateway](#enabling-secure-endpoints-on-api-gateway)
        - [API Key](#api-key)
        - [IAM Policy](#iam-policy)
        - [Authorizer](#authorizer)
    - [Deploying to a Domain With a Let's Encrypt Certificate (DNS Auth)](#deploying-to-a-domain-with-a-lets-encrypt-certificate-dns-auth)
    - [Deploying to a Domain With a Let's Encrypt Certificate (HTTP Auth)](#deploying-to-a-domain-with-a-lets-encrypt-certificate-http-auth)
    - [Setting Environment Variables](#setting-environment-variables)
      - [Local Environment Variables](#local-environment-variables)
      - [Remote Environment Variables](#remote-environment-variables)
    - [Setting Integration Content-Type Aliases](#setting-integration-content-type-aliases)
    - [Catching Unhandled Exceptions](#catching-unhandled-exceptions)
    - [Using Custom AWS IAM Roles and Policies](#using-custom-aws-iam-roles-and-policies)
- [Zappa Guides](#zappa-guides)
- [Zappa in the Press](#zappa-in-the-press)
- [Sites Using Zappa](#sites-using-zappa)
- [Related Projects](#related-projects)
- [Hacks](#hacks)
- [Contributing](#contributing)
    - [Using a Local Repo](#using-a-local-repo)
- [Support / Development / Training / Consulting](#support--development--training--consulting)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

## About

<p align="center">
  <a href="https://htmlpreview.github.io/?https://raw.githubusercontent.com/Miserlou/Talks/master/serverless-sf/big.quickstart.html"><img src="http://i.imgur.com/c23kDNT.png?1" alt="Zappa Slides"/></a>
</p>
<p align="center">
  <i>In a hurry? Click to see <a href="https://htmlpreview.github.io/?https://raw.githubusercontent.com/Miserlou/Talks/master/serverless-sf/big.quickstart.html">slides from Serverless SF</a>!</i>
</p>

**Zappa** makes it super easy to deploy all Python WSGI applications on AWS Lambda + API Gateway. Think of it as "serverless" web hosting for your Python web apps. That means **infinite scaling**, **zero downtime**, **zero maintenance** - and at a fraction of the cost of your current deployments!

If you've got a Python web app (including Django and Flask apps), it's as easy as:

```
$ pip install zappa
$ zappa init
$ zappa deploy
```

and now you're server-less! _Wow!_

> What do you mean "serverless"?

Okay, so there still is a server - but it only has a _40 millisecond_ life cycle! Serverless in this case means **"without any permanent infrastucture."**

With a traditional HTTP server, the server is online 24/7, processing requests one by one as they come in. If the queue of incoming requests grows too large, some requests will time out. With Zappa, **each request is given its own virtual HTTP "server"** by Amazon API Gateway. AWS handles the horizontal scaling automatically, so no requests ever time out. Each request then calls your application from a memory cache in AWS Lambda and returns the response via Python's WSGI interface. After your app returns, the "server" dies.

Better still, with Zappa you only pay for the milliseconds of server time that you use, so it's many **orders of magnitude cheaper** than VPS/PaaS hosts like Linode or Heroku - and in most cases, it's completely free. Plus, there's no need to worry about load balancing or keeping servers online ever again.

It's great for deploying serverless microservices with frameworks like Flask and Bottle, and for hosting larger web apps and CMSes with Django. Or, you can use any WSGI-compatible app you like! You **probably don't need to change your existing applications** to use it, and you're not locked into using it.

And finally, Zappa is **super easy to use**. You can deploy your application with a single command out of the box.

__Awesome!__

<p align="center">
  <img src="http://i.imgur.com/f1PJxCQ.gif" alt="Zappa Demo Gif"/>
</p>

## Installation and Configuration

_Before you begin, make sure you have a valid AWS account and your [AWS credentials file](https://blogs.aws.amazon.com/security/post/Tx3D6U6WSFGOK2H/A-New-and-Standardized-Way-to-Manage-Credentials-in-the-AWS-SDKs) is properly installed._

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
    "dev": { // The name of your environment
       "s3_bucket": "lmbda", // The name of your S3 bucket
       "app_function": "your_module.app" // The python path to your WSGI application function. In Flask, this is your 'app' object.
    }
}
```

or for Django:

```javascript
{
    "dev": { // The name of your environment
       "s3_bucket": "lmbda", // The name of your S3 bucket
       "django_settings": "your_project.settings" // The python path to your Django settings.
    }
}
```

You can define as many environments as your like - we recommend having _dev_, _staging_, and _production_.

Now, you're ready to deploy!

## Basic Usage

#### Initial Deployments

Once your settings are configured, you can package and deploy your application to an environment called "production" with a single command:

    $ zappa deploy production
    Deploying..
    Your application is now live at: https://7k6anj0k99.execute-api.us-east-1.amazonaws.com/production

And now your app is **live!** How cool is that?!

To explain what's going on, when you call `deploy`, Zappa will automatically package up your application and local virtual environment into a Lambda-compatible archive, replace any dependencies with versions [precompiled for Lambda](https://github.com/Miserlou/lambda-packages), set up the function handler and necessary WSGI Middleware, upload the archive to S3, register it as a new Lambda function, create a new API Gateway resource, create WSGI-compatible routes for it, link it to the new Lambda function, and finally delete the archive from your S3 bucket. Handy!

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

#### Executing in Response to AWS Events

Similarly, you can have your functions execute in response to events that happen in the AWS ecosystem, such as S3 uploads, DynamoDB entries, Kinesis streams, and SNS messages.

In your *zappa_settings.json* file, define your [event sources](http://docs.aws.amazon.com/lambda/latest/dg/invoking-lambda-function.html) and the function you wish to execute. For instance, this will execute `your_module.your_function` in response to new objects in your `my-bucket` S3 bucket. Note that `your_function` must accept `event` and `context` paramaters.

```javascript
{
    "production": {
       ...
       "events": [{
            "function": "your_module.your_function",
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

#### Undeploy

If you need to remove the API Gateway and Lambda function that you have previously published, you can simply:

    $ zappa undeploy production

You will be asked for confirmation before it executes.

If you enabled CloudWatch Logs for your API Gateway service and you don't
want to keep those logs, you can specify the `--remove-logs` argument to purge the logs for your API Gateway and your Lambda function:

    $ zappa undeploy production --remove-logs

#### Status

If you need to see the status of your deployment and event schedules, simply use the `status` command.

    $ zappa status production

#### Tailing Logs

You can watch the logs of a deployment by calling the `tail` management command.

    $ zappa tail production

#### Remote Function Invocation

You can execute any function in your application directly at any time by using the `invoke` command.

For instance, suppose you have a basic application in a file called "my_app.py", and you want to invoke a function in it called "my_function". Once your application is deployed, you can invoke that function at any time by calling:

    $ zappa invoke production 'my_app.my_function'

Any remote print statements made and the value the function returned will then be printed to your local console. **Nifty!**

You can also invoke interpretable Python 2.7 strings directly by using `--raw`, like so:

    $ zappa invoke production "print 1 + 2 + 3" --raw

#### Django Management Commands

As a convenience, Zappa can also invoke remote Django 'manage.py' commands with the `manage` command. For instance, to perform the basic Django status check:

    $ zappa manage production showmigrations admin

Obviously, this only works for Django projects which have their settings properly defined.

For commands which have their own arguments, you can also pass the command in as a string, like so:

    $ zappa manage production "shell --version"

Commands which require direct user input, such as `createsuperuser`, should be [replaced by commands](http://stackoverflow.com/a/26091252) which use `zappa <env> invoke --raw`.

_(Please note that commands which take over 30 seconds to execute may time-out. See [this related issue](https://github.com/Miserlou/Zappa/issues/205#issuecomment-236391248) for a work-around.)_

#### Let's Encrypt SSL Domain Certification and Installation

If you want to use Zappa applications on a custom domain or subdomain, you'll need to supply a valid SSL certificate. Fortunately for you, Zappa can automatically create and install free valid SSL certificates using Let's Encrypt!

If your domain is located within an AWS Route 53 Hosted Zone and you've defined `domain` and `lets_encrypt_key` (ex: `openssl genrsa 2048 > account.key`) settings, all you need to do is:

    $ zappa certify production

And your domain will be verified, certified and registered!

_(Please note that this can take around 45 minutes to take effect the first time your run the command, and around 60 seconds every time after that.)_

More detailed instructions are available [in this handy guide](https://github.com/Miserlou/Zappa/blob/master/docs/domain_with_free_ssl_dns.md).

## Advanced Settings

There are other settings that you can define in your local settings
to change Zappa's behavior. Use these at your own risk!

```javascript
 {
    "dev": {
        "api_key_required": false, // enable securing API Gateway endpoints with x-api-key header (default False)
        "api_key": "your_api_key_id" // optional, use an existing API key. The option "api_key_required" must be true to apply
        "assume_policy": "my_assume_policy.json", // optional, IAM assume policy JSON file
        "attach_policy": "my_attach_policy.json", // optional, IAM attach policy JSON file
        "aws_region": "us-east-1", // AWS Region (default US East),
        "callbacks": { // Call custom functions during the local Zappa deployment/update process
            "settings": "my_app.settings_callback", // After loading the settings
            "zip": "my_app.zip_callback", // After creating the package
            "post": "my_app.post_callback", // After command has excuted
        },
        "cache_cluster_enabled": false, // Use APIGW cache cluster (default False)
        "cache_cluster_size": .5, // APIGW Cache Cluster size (default 0.5)
        "cloudwatch_log_level": "OFF", // Enables/configures a level of logging for the given staging. Available options: "OFF", "INFO", "ERROR", default "OFF".
        "cloudwatch_data_trace": false, // Logs all data about received events.
        "cloudwatch_metrics_enabled": false, // Additional metrics for the API Gateway.
        "debug": true, // Print Zappa configuration errors tracebacks in the 500
        "delete_local_zip": true, // Delete the local zip archive after code updates
        "delete_s3_zip": true, // Delete the s3 zip archive
        "django_settings": "your_project.production_settings", // The modular path to your Django project's settings. For Django projects only.
        "domain": "yourapp.yourdomain.com", // Required if you're using a domain
        "environment_variables": {"your_key": "your_value"}, // A dictionary of environment variables that will be available to your deployed app. See also "remote_env_file". Default {}.
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
        "http_methods": ["GET", "POST"], // HTTP Methods to route,
        "iam_authorization": true, // optional, use IAM to require request signing. Default false. Note that enabling this will override the authorizer configuration.
        "authorizer": {
            "function": "your_module.your_auth_function", // Required. Function to run for token validation. For more information about the function see below.
            "result_ttl": 300, // Optional. Default 300. The time-to-live (TTL) period, in seconds, that specifies how long API Gateway caches authorizer results. Currently, the maximum TTL value is 3600 seconds.
            "token_source": "Authorization", // Optional. Default 'Authorization'. The name of a custom authorization header containing the token that clients submit as part of their requests.
            "validation_expression": "^Bearer \\w+$", // Optional. A validation expression for the incoming token, specify a regular expression.
        },
        "integration_response_codes": [200, 301, 404, 500], // Integration response status codes to route
        "integration_content_type_aliases": { // For routing requests with non-standard mime types
            "application/json": [
                "application/vnd.webhooks+json"
            ]
        },
        "keep_warm": true, // Create CloudWatch events to keep the server warm.
        "keep_warm_expression": "rate(4 minutes)", // How often to execute the keep-warm, in cron and rate format. Default 4 minutes.
        "lambda_description": "Your Description", // However you want to describe your project for the AWS console. Default "Zappa Deployment".
        "lambda_handler": "your_custom_handler", // The name of Lambda handler. Default: handler.lambda_handler
        "lets_encrypt_key": "s3://your-bucket/account.key", // Let's Encrypt account key path. Can either be an S3 path or a local file path.
        "lets_encrypt_schedule": "rate(15 days)" // How often to auto-renew Let's Encrypt certificate on the server. Must be set to enable autorenewing, rate or cron syntax.
        "log_level": "DEBUG", // Set the Zappa log level. Default INFO, can be one of CRITICAL, ERROR, WARNING, INFO and DEBUG.
        "manage_roles": true, // Have Zappa automatically create and define IAM execution roles and policies. Default true. If false, you must define your own IAM Role and role_name setting.
        "memory_size": 512, // Lambda function memory in MB
        "method_header_types": [ // Which headers to include in the API response. Defaults:
            "Content-Type",
            "Location",
            "Status",
            "X-Frame-Options",
            "Set-Cookie"
        ],
        "method_response_codes": [200, 301, 404, 500], // Method response status codes to route
        "parameter_depth": 10, // Size of URL depth to route. Defaults to 8.
        "prebuild_script": "your_module.your_function", // Function to execute before uploading code
        "profile_name": "your-profile-name", // AWS profile credentials to use. Default 'default'.
        "project_name": "MyProject", // The name of the project as it appears on AWS. Defaults to a slugified `pwd`.
        "remote_env_bucket": "my-project-config-files", // optional s3 bucket where remote_env_file can be located.
        "remote_env_file": "filename.json", // file in remote_env_bucket containing a flat json object which will be used to set custom environment variables.
        "role_name": "MyLambdaRole", // Name of Zappa execution role. Default ZappaExecutionRole. To use a different, pre-existing policy, you must also set manage_roles to false.
        "s3_bucket": "dev-bucket", // Zappa zip bucket,
        "settings_file": "~/Projects/MyApp/settings/dev_settings.py", // Server side settings file location,
        "timeout_seconds": 30, // Maximum lifespan for the Lambda function (default 30, max 300.)
        "touch": false, // GET the production URL upon initial deployment (default True)
        "use_precompiled_packages": false, // If possible, use C-extension packages which have been pre-compiled for AWS Lambda
        "use_apigateway": true, // Set to false if you don't want to create API Gateway resource. Default true
        "vpc_config": { // Optional VPC configuration for Lambda function
            "SubnetIds": [ "subnet-12345678" ], // Note: not all availability zones support Lambda!
            "SecurityGroupIds": [ "sg-12345678" ]
        }
    }
}
```

## Advanced Usage

#### Keeping The Server Warm

Zappa will automatically set up a regularly occuring execution of your application in order to keep the Lambda function warm. This can be disabled via the 'keep_warm' setting.

#### Serving Static Files / Binary Uploads

Zappa is for running your application code, not for serving static web assets. If you plan on serving custom static assets in your web application (CSS/JavaScript/images/etc.,), you'll likely want to use a combination of AWS S3 and AWS CloudFront.

Your web application framework will likely be able to handle this for you automatically. For Flask, there is [Flask-S3](https://github.com/e-dard/flask-s3), and for Django, there is [Django-Storages](https://django-storages.readthedocs.io/en/latest/).

Similarly, you will not be able to accept binary multi-part uploads through the API Gateway. Instead, you should design your application so that binary uploads go [directly to S3](http://docs.aws.amazon.com/AWSJavaScriptSDK/guide/browser-examples.html#Uploading_a_local_file_using_the_File_API), which then triggers an event response defined in your `events` setting! That's thinking serverlessly!

#### Enabling CORS

To enable Cross-Origin Resource Sharing (CORS) for your application, follow the [AWS "How to CORS" Guide](https://docs.aws.amazon.com/apigateway/latest/developerguide/how-to-cors.html) to enable CORS via the API Gateway Console. Don't forget to enable CORS per parameter and re-deploy your API after making the changes!

You can also simply handle CORS directly in your application. If you do this, you'll need to add `Access-Control-Allow-Origin`, `Access-Control-Allow-Headers`, and `Access-Control-Allow-Methods` to the `method_header_types` key in your `zappa_settings.json`. See further [discussion here](https://github.com/Miserlou/Zappa/issues/41).

#### Enabling Secure Endpoints on API Gateway

##### API Key

You can use the `api_key_required` setting to generate and assign an API key to all the routes of your API Gateway. After redeployment, you can then pass the provided key as a header called `x-api-key` to access the restricted endpoints. Without the `x-api-key` header, you will receive a 403. [More information on API keys in the API Gateway](http://docs.aws.amazon.com/apigateway/latest/developerguide/how-to-api-keys.html)

##### IAM Policy

You can enable IAM-based (v4 signing) authorization on an API by setting the `iam_authorization` setting to `true`. Your API will then require signed requests and access can be controlled via [IAM policy](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-iam-policy-examples.html). Unsigned requests will receive a 403 response, as will requesters who are not authorized to access the API. Enabling this will override the Authorizer configuration (see below).

##### Authorizer
If you deploy an API endpoint with Zappa, you can take advantage of [API Gateway Authorizers](http://docs.aws.amazon.com/apigateway/latest/developerguide/use-custom-authorizer.html) to implement a token-based authentication - all you need to do is to provide a function to create the required output, Zappa takes care of the rest. A good start for the function is the [awslabs blueprint example.](https://github.com/awslabs/aws-apigateway-lambda-authorizer-blueprints/blob/master/blueprints/python/api-gateway-authorizer-python.py)
Inside your app, the authenticated username will be available through the `REMOTE_USER` environment variable (e.g. in Flask `request.environ.get('REMOTE_USER')`)
If you are wondering for what you would use an Authorizer, here are some potential use cases:
1. Call out to OAuth provider
2. Decode a JWT token inline
3. Lookup in a self-managed DB (for example DynamoDB)


#### Deploying to a Domain With a Let's Encrypt Certificate (DNS Auth)

If you want to use Zappa on a domain with a free Let's Encrypt certificate using automatic Route 53 based DNS Authentication, you can follow [this handy guide](https://github.com/Miserlou/Zappa/blob/master/docs/domain_with_free_ssl_dns.md).

#### Deploying to a Domain With a Let's Encrypt Certificate (HTTP Auth)

If you want to use Zappa on a domain with a free Let's Encrypt certificate using HTTP Authentication, you can follow [this guide](https://github.com/Miserlou/Zappa/blob/master/docs/domain_with_free_ssl_http.md).

However, it's now far easier to use Route 53-based DNS authentication, which will allow you to use a Let's Encrypt certificate with a single `$ zappa certify` command.

#### Setting Environment Variables

##### Local Environment Variables

If you want to set local remote environment variables for a deployment stage, you can simply set them in your `zappa_settings.json`:

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

##### Remote Environment Variables

If you want to use remote environment variables to configure your application (which is especially useful for things like sensitive credentials), you can create a file and place it in an S3 bucket to which your Zappa application has access to. To do this, add the `remote_env_bucket` and `remote_env_file` keys to zappa_settings pointing to a file containing a flat JSON object, so that each key-value pair on the object will be set as an environment variable and value whenever a new lambda instance spins up.

For example, to ensure your application has access to the database credentials without storing them in your version control, you can add a file to S3 with the connection string and load it into the lambda environment using the `remote_env_bucket` and `remote_env_file` configuration settings.

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
        "remote_env_bucket": "my-config-bucket",
        "remote_env_file": "super-secret-config.json"
    },
    ...
}
```

Now in your application you can use:
```python
import os
db_string = os.environ.get('DB_CONNECTION_STRING')
```

#### Setting Integration Content-Type Aliases

By default, Zappa will only route the following MIME-types that are set explicitly via `Content-Type` header: `application/json`, `application/x-www-form-urlencoded`, and `multipart/form-data` (if the Content-Type header isn't set, `application/json` will be the default). If a request comes in with `Content-Type` header set to anything but those 3 values, Amazon will return a 415 status code and a `MIME type not supported` message. If there is a need to support custom MIME-types (e.g. when a third-party making requests to your API) you can specify aliases for the 3 default types:

zappa_settings.json:
```javascript
{
    "dev": {
        ...
        "integration_content_type_aliases": {
            "application/json": ["application/vnd.webhooks+json"]
         }
    },
    ...
}
```

Now Zappa will use `application/json`'s template to route requests with MIME-type of `application/vnd.webhooks+json`. You will need to re-deploy your application for this change to take affect.

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

By default, the Zappa client will create and manage the necessary IAM policies and roles to deploy and execute Zappa applications. However, if you're using Zappa in a corporate environment or as part of a continuous integration, you may instead want to manually manage your policies instead.

To manually define the permissions policy of your Zappa execution role, you must define the following in your *zappa_settings.json*:

```javascript
{
    "dev": {
        ...
        "manage_roles": false, // Disable Zappa client managing roles.
        "role_name": "MyLambdaRole", // Name of your Zappa execution role. Default ZappaExecutionRole.
        ...
    },
    ...
}
```

Ongoing discussion about the minimum policy requirements necessary for a Zappa deployment [can be found here](https://github.com/Miserlou/Zappa/issues/244).

## Zappa Guides

* [Django-Zappa tutorial screencast](https://www.youtube.com/watch?v=plUrbPN0xc8&feature=youtu.be).
* [Using Django-Zappa, Part 1](https://serverlesscode.com/post/zappa-wsgi-for-python/).
* [Using Django-Zappa, Part 2: VPCs](https://serverlesscode.com/post/zappa-wsgi-for-python-pt-2/).
* [Building Serverless Microservices with Zappa and Flask](https://gun.io/blog/serverless-microservices-with-zappa-and-flask/)
* [Zappa で Hello World するまで (Japanese)](http://qiita.com/satoshi_iwashita/items/505492193317819772c7)
* _Your guide here?_

## Zappa in the Press

* _[Zappa Serves Python, Minus the Servers](http://www.infoworld.com/article/3031665/application-development/zappa-serves-python-web-apps-minus-the-servers.html)_
* _[Zappa lyfter serverlösa applikationer med Python](http://computersweden.idg.se/2.2683/1.649895/zappa-lyfter-python)_
* _[Interview: Rich Jones on Zappa](https://serverlesscode.com/post/rich-jones-interview-django-zappa/)_

## Sites Using Zappa

* [Zappa.io](https://www.zappa.io) - A simple Zappa homepage
* [Zappatista!](https://blog.zappa.io) - The official Zappa blog!
* [Mailchimp Signup Utility](https://github.com/sasha42/Mailchimp-utility) - A microservice for adding people to a mailing list via API.
* [Zappa Slack Inviter](https://github.com/Miserlou/zappa-slack-inviter) - A tiny, server-less service for inviting new users to your Slack channel.
* [Serverless Image Host](https://github.com/Miserlou/serverless-imagehost) - A thumbnailing service with Flask, Zappa and Pillow.
* [Gigger](https://www.gigger.rocks/) - The live music industry's search engine
* [Zappa BitTorrent Tracker](https://github.com/Miserlou/zappa-bittorrent-tracker) - An experimental server-less BitTorrent tracker. Work in progress.
* [JankyGlance](https://github.com/Miserlou/JankyGlance) - A server-less Yahoo! Pipes replacement.
* And many more!

Are you using Zappa? Let us know and we'll list your site here!

## Related Projects

* [lambda-packages](http://github.com/Miserlou/lambda-packages) - Precompiled C-extention packages for AWS Lambda. Used automatically by Zappa.
* [zappa-cms](http://github.com/Miserlou/zappa-cms) - A tiny server-less CMS for busy hackers. Work in progress.
* [flask-ask](https://github.com/johnwheeler/flask-ask) - A framework for building Amazon Alexa applications. Uses Zappa for deployments.
* [zappa-file-widget](https://github.com/anush0247/zappa-file-widget) - A Django plugin for supporting binary file uploads in Django on Zappa.
* [zops](https://github.com/bjinwright/zops) - Utilities for teams and continuous integrations using Zappa.

## Hacks

Zappa goes quite far beyond what Lambda and API Gateway were ever intended to handle. As a result, there are quite a few hacks in here that allow it to work. Some of those include, but aren't limited to..

* Using VTL to map body, headers, method, params and query strings into JSON, and then turning that into valid WSGI.
* Attaching response codes to response bodies, Base64 encoding the whole thing, using that as a regex to route the response code, decoding the body in VTL, and mapping the response body to that.
* Packing and _Base58_ encoding multiple cookies into a single cookie because we can only map one kind.
* Turning cookie-setting 301/302 responses into 200 responses with HTML redirects, because we have no way to set headers on redirects.

## Contributing

This project is still young, so there is still plenty to be done. Contributions are more than welcome!

Please file tickets for discussion before submitting patches, and submit your patches to the "dev" branch if possible. If dev falls behind master, feel free to rebase.

If you are adding a non-trivial amount of new code, please include a functioning test in your PR. For AWS calls, we use the placebo library, which you can learn to use [in the test writing guide](docs/README.md).

Please also write comments along with your new code, including the URL of the ticket which you filed along with the PR. This greatly helps for project maintainability, as it allows us to trace back use cases and explain decision making.

#### Using a Local Repo

To use the git HEAD, you *can't* use `pip install -e `. Instead, you should clone the repo to your machine and then `pip install /path/to/zappa/repo` or `ln -s /path/to/zappa/repo/zappa zappa` in your local project.

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

