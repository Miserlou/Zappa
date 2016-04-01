<p align="center">
  <img src="http://i.imgur.com/oePnHJn.jpg" alt="Zappa Rocks!"/>
</p>

## Zappa - Serverless Python Web Services 

[![Build Status](https://travis-ci.org/Miserlou/Zappa.svg)](https://travis-ci.org/Miserlou/Zappa)
[![Coverage](https://img.shields.io/coveralls/Miserlou/Zappa.svg)](https://coveralls.io/github/Miserlou/Zappa) 
[![PyPI](https://img.shields.io/pypi/dm/Zappa.svg?style=flat)](https://pypi.python.org/pypi/zappa/)
[![PyPI](https://img.shields.io/pypi/v/Zappa.svg)](https://pypi.python.org/pypi/zappa)
[![Slack](https://img.shields.io/badge/chat-slack-ff69b4.svg)](https://slackautoinviter.herokuapp.com/)

**Zappa** makes it super easy to deploy all Python WSGI applications on AWS Lambda + API Gateway. Think of it as "serverless" web hosting for your Python web apps. 

It's great for deploying serverless microservices with frameworks like Flask and Bottle, and for hosting larger web apps and CMSes with Django. Or, you can use any WSGI-compatible app you like!

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

If you're looking for Django-specific integration, you should probably check out _**[django-zappa](https://github.com/Miserlou/django-zappa)**_ instead.

Next, you'll need to define your local and server-side settings.

#### Settings

Next, you'll need to define a few settings for your Zappa deployment environments in a file named *zappa_settings.json* in your project directory. The simplest example is:

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

To expain what's going on, when you call 'deploy', Zappa will automatically package up your application and local virtual environment into a Lambda-compatible archive, replace any dependencies with versions [precompiled for Lambda](https://github.com/Miserlou/lambda-packages), set up the function handler and necessary WSGI Middleware, upload the archive to S3, register it as a new Lambda function, create a new API Gateway resource, create WSGI-compatible routes for it, link it to the new Lambda function, and finally delete the archive from your S3 bucket. Handy!

#### Updates

If your application has already been deployed and you only need to upload new Python code, but not touch the underlying routes, you can simply:

    $ zappa update production
    Updating..
    Your application is now live at: https://7k6anj0k99.execute-api.us-east-1.amazonaws.com/production

This creates a new archive, uploads it to S3 and updates the Lambda function to use the new code, but doesn't touch the API Gateway routes.

#### Rollback

You can also rollback the deployed code to a previous version by supplying the number of revisions to return to. For instance, to rollback to the version deployed 3 versions ago:

    $ zappa rollback production -n 3

#### Tailing Logs

You can watch the logs of a deployment by calling the "tail" management command.

    $ zappa tail production

## Advanced Usage

There are other settings that you can define in your local settings
to change Zappa's behavior. Use these at your own risk!

```javascript
 {
    "dev": {
        "aws_region": "us-east-1", // AWS Region (default US East),
        "debug": true // Print Zappa configuration errors tracebacks in the 500
        "delete_zip": true // Delete the local zip archive after code updates
        "domain": "yourapp.yourdomain.com", // Required if you're using a domain
        "http_methods": ["GET", "POST"], // HTTP Methods to route,
        "integration_response_codes": [200, 301, 404, 500], // Integration response status codes to route
        "memory_size": 512, // Lambda function memory in MB
        "method_response_codes": [200, 301, 404, 500], // Method response status codes to route
        "parameter_depth": 10, // Size of URL depth to route. Defaults to 5.
        "role_name": "MyLambdaRole", // Lambda execution Role
        "s3_bucket": "dev-bucket", // Zappa zip bucket,
        "settings_file": "~/Projects/MyApp/settings/dev_settings.py", // Server side settings file location,
        "touch": false, // GET the production URL upon initial deployment (default True)
        "use_precompiled_packages": false, // If possible, use C-extension packages which have been pre-compiled for AWS Lambda
        "vpc_config": { // Optional VPC configuration for Lambda function
            "SubnetIds": [ "subnet-12345678" ], // Note: not all availability zones support Lambda!
            "SecurityGroupIds": [ "sg-12345678" ]
        }
    }
}
```

#### Keeping the server warm

Lambda has a limitation that functions which aren't called very often take longer to start - sometimes up to ten seconds. However, functions that are called regularly are cached and start quickly, usually in less than 50ms. To ensure that your servers are kept in a cached state, you can [manually configure](http://stackoverflow.com/a/27382253) a scheduled task for your Zappa function that'll keep the server cached by calling it every 5 minutes. There is currently no way to configure this through API, so you'll have to set this up manually. When this ability is available via API, Zappa will configure this automatically. It would be nice to also add support LetsEncrypt through this same mechanism.

#### Enabling CORS

To enable Cross-Origin Resource Sharing (CORS) for your application, follow the [AWS "How to CORS" Guide](https://docs.aws.amazon.com/apigateway/latest/developerguide/how-to-cors.html) to enable CORS via the API Gateway Console. Don't forget to re-deploy your API after making the changes!

## Zappa Guides

* [Django-Zappa tutorial screencast](https://www.youtube.com/watch?v=plUrbPN0xc8&feature=youtu.be).
* [Using Django-Zappa, Part 1](https://serverlesscode.com/post/zappa-wsgi-for-python/).
* [Using Django-Zappa, Part 2: VPCs](https://serverlesscode.com/post/zappa-wsgi-for-python-pt-2/).
* [Building Serverless Microservices with Zappa and Flask](https://gun.io/blog/serverless-microservices-with-zappa-and-flask/)
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

## TODO

This project is very young, so there is still plenty to be done. Contributions are more than welcome! Please file tickets before submitting patches, and submit your patches to the "dev" branch.

Things that need work right now:

* Testing
* Feedback
* Real documentation / website!
