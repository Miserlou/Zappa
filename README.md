<p align="center">
  <img src="http://i.imgur.com/oePnHJn.jpg" alt="Zappa Rocks!"/>
</p>

## Zappa - Serverless Python Web Services

[![Build Status](https://travis-ci.org/Miserlou/Zappa.svg)](https://travis-ci.org/Miserlou/Zappa)
[![Coverage](https://img.shields.io/coveralls/Miserlou/Zappa.svg)](https://coveralls.io/github/Miserlou/Zappa)
[![Requirements Status](https://requires.io/github/Miserlou/Zappa/requirements.svg?branch=master)](https://requires.io/github/Miserlou/Zappa/requirements/?branch=master)
[![PyPI](https://img.shields.io/pypi/v/Zappa.svg)](https://pypi.python.org/pypi/zappa)
[![Slack](https://img.shields.io/badge/chat-slack-ff69b4.svg)](https://slackautoinviter.herokuapp.com/)

**Zappa** makes it super easy to deploy all Python WSGI applications on AWS Lambda + API Gateway. Think of it as "serverless" web hosting for your Python web apps.

> What do you mean "serverless"?

Okay, so there still is a server - but it only has a _40 millisecond_ life cycle! Serverless in this case means **"without any permanent infrastucture."**

With a traditional HTTP server, the server is online 24/7, processing requests one by one as they come in. If the queue of incoming requests grows too large, some requests will time out. With Zappa, **each request is given its own virtual HTTP "server"** by Amazon API Gateway. AWS handles the horizontal scaling automatically, so no requests ever time out. Each request then calls your application from a memory cache in AWS Lambda and returns the response via Python's WSGI interface. After your app returns, the "server" dies.

Better still, with Zappa you only pay for the milliseconds of server time that you use, so it's many **orders of magnitude cheaper** than VPS/PaaS hosts like Linode or Heroku - and in most cases, it's completely free. Plus, there's no need to worry about load balancing or keeping servers online ever again.

It's great for deploying serverless microservices with frameworks like Flask and Bottle, and for hosting larger web apps and CMSes with Django. Or, you can use any WSGI-compatible app you like! You **probably don't need to change your existing applications** to use it, and you're not locked into using it.

And finally, Zappa is **super easy to use**. You can deploy your application with a single command out of the box.  

Using **Zappa** means:

* **No more** tedious web server configuration!
* **No more** paying for 24/7 server uptime!
* **No more** worrying about load balancing / scalability!
* **No more** worrying about keeping servers online!

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

This will automatically detect your application type and help you define your deployment configuration settings. Once you finish initialization, you'll have a file named *zappa_settings.json* in your project directory defining your deployment settings. It will probably look something like this:

```javascript
{
    "dev": { // The name of your environment
       "s3_bucket": "lmbda", // The name of your S3 bucket
       "app_function": "your_module.app" // The python path to your WSGI application function. In Flask, this is your 'app' object.
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

Zappa can be used to easily schedule functions to occur on regular intervals.
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
                    "s3:ObjectCreated:*"
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

#### Undeploy

If you need to remove the API Gateway and Lambda function that you have previously published, you can simply:

    $ zappa undeploy production

You will be asked for confirmation before it executes.

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

#### Django Management Commands

As a convenience, Zappa can also invoke remote Django 'manage.py' commands with the `manage` command. For instance, to perform the basic Django status check:

    $ zappa manage production check

Obviously, this only works for Django projects which have their settings properly defined. _(Please note that commands which take over 30 seconds to execute may time-out. See [this related issue](https://github.com/Miserlou/Zappa/issues/205#issuecomment-236391248) for a work-around.)_ 

## Advanced Settings

There are other settings that you can define in your local settings
to change Zappa's behavior. Use these at your own risk!

```javascript
 {
    "dev": {
        "api_key_required": false, // enable securing API Gateway endpoints with x-api-key header (default False)
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
        "delete_zip": true, // Delete the local zip archive after code updates
        "django_settings": "your_project.production_settings", // The modular path to your Django project's settings. For Django projects only.
        "domain": "yourapp.yourdomain.com", // Required if you're using a domain
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
        "exclude": ["*.gz", "*.rar"], // A list of regex patterns to exclude from the archive
        "http_methods": ["GET", "POST"], // HTTP Methods to route,
        "integration_response_codes": [200, 301, 404, 500], // Integration response status codes to route
        "integration_content_type_aliases": { // For routing requests with non-standard mime types
            "application/json": [
                "application/vnd.webhooks+json"
            ]
        }, 
        "keep_warm": true, // Create CloudWatch events to keep the server warm.
        "keep_warm_expression": "rate(5 minutes)", // How often to execute the keep-warm, in cron and rate format. Default 5 minutes.
        "lambda_handler": "your_custom_handler", // The name of Lambda handler. Default: handler.lambda_handler
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
        "timeout_seconds": 30, // Maximum lifespan for the Lambda function (default 30)
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

#### Enabling CORS

To enable Cross-Origin Resource Sharing (CORS) for your application, follow the [AWS "How to CORS" Guide](https://docs.aws.amazon.com/apigateway/latest/developerguide/how-to-cors.html) to enable CORS via the API Gateway Console. Don't forget to enable CORS per parameter and re-deploy your API after making the changes!

#### Enabling Secure Endpoints on API Gateway

You can use the `api_key_required` setting to generate and assign an API key to all the routes of your API Gateway. After redeployment, you can then pass the provided key as a header called `x-api-key` to access the restricted endpoints. Without the `x-api-key` header, you will receive a 403. [More information on API keys in the API Gateway](http://docs.aws.amazon.com/apigateway/latest/developerguide/how-to-api-keys.html) 

#### Deploying to a Domain With a Let's Encrypt Certificate

If you want to use Zappa on a domain with a free Let's Encrypt certificate, you can follow [this guide](https://github.com/Miserlou/Zappa/blob/master/docs/domain_with_free_ssl.md).

#### Setting Environment Variables

If you want to use environment variables to configure your application (which is especially useful for things like sensitive credentials), you can create a file and place it in an S3 bucket to which your Zappa application has access to. To do this, add the `remote_env_bucket` and `remote_env_file` keys to zappa_settings pointing to a file containing a flat JSON object, so that each key-value pair on the object will be set as an environment variable and value whenever a new lambda instance spins up.

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
db_string = os.environ('DB_CONNECTION_STRING')
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

* [zappa.gun.io](https://zappa.gun.io) - A Zappa "Hello, World" (real homepage coming.. soon..)
* [spheres.gun.io](https://spheres.gun.io)  - Spheres, a photosphere host and viewer
* [Mailchimp Signup Utility](https://github.com/sasha42/Mailchimp-utility) - A microservice for adding people to a mailing list via API.
* [Serverless Image Host](https://github.com/Miserlou/serverless-imagehost) - A thumbnailing service with Flask, Zappa and Pillow.
* Your site here?

## Hacks

Zappa goes quite far beyond what Lambda and API Gateway were ever intended to handle. As a result, there are quite a few hacks in here that allow it to work. Some of those include, but aren't limited to..

* Using VTL to map body, headers, method, params and query strings into JSON, and then turning that into valid WSGI.
* Attaching response codes to response bodies, Base64 encoding the whole thing, using that as a regex to route the response code, decoding the body in VTL, and mapping the response body to that.
* Packing and _Base58_ encoding multiple cookies into a single cookie because we can only map one kind.
* Turning cookie-setting 301/302 responses into 200 responses with HTML redirects, because we have no way to set headers on redirects.

## Contributing

This project is still young, so there is still plenty to be done. Contributions are more than welcome! Please file tickets before submitting patches, and submit your patches to the "dev" branch.
