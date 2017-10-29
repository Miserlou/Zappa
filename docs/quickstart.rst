==========
Quickstart
==========

Installation and Configuration
==============================

Before you begin, make sure you have a valid AWS account and your
`AWS credentials file
<https://blogs.aws.amazon.com/security/post/Tx3D6U6WSFGOK2H/A-New-and-Standardized-Way-to-Manage-Credentials-in-the-AWS-SDKs>`_
is properly installed.

**Zappa** can easily be installed through pip, like so: ::

    $ pip install zappa

Please note that Zappa **must** be installed into your project's 
`virtual environment <http://docs.python-guide.org/en/latest/dev/virtualenvs/>`_.

(If you use `pyenv <https://github.com/yyuu/pyenv>`_ and love to manage virtualenvs with **pyenv-virtualenv**, you just have to call *pyenv local [your_venv_name]* and it's ready. `Conda <http://conda.pydata.org/docs/>`_ users should comment `here <https://github.com/Miserlou/Zappa/pull/108>`_.)

Next, you'll need to define your local and server-side settings.

Running the Initial Setup / Settings
------------------------------------

**Zappa** can automatically set up your deployment settings for you with the *init* command: ::

    $ zappa init

This will automatically detect your application type and help you define your deployment configuration settings. Once you finish initialization, you'll have a file named *zappa_settings.json* in your project directory defining your deployment settings. It will probably look something like this: ::

    {
        "dev": { // The name of your stage
            "s3_bucket": "lmbda", // The name of your S3 bucket
            "app_function": "your_module.app" // The python path to your WSGI application function. In Flask, this is your 'app' object.
        }
    }

You can define as many stages as you like. We recommend having dev, staging, and production.

Now, you're ready to deploy!

Basic Usage
===========

Initial Deployments
-------------------

Once your settings are configured, you can package and deploy your application to a stage called "production" with a single command: ::

    $ zappa deploy production
    Deploying..
    Your application is now live at: https://7k6anj0k99.execute-api.us-east-1.amazonaws.com/production

And now your app is **live!** How cool is that?!

To explain what's going on, when you call 'deploy', Zappa will automatically package up your application and local virtual environment into a Lambda-compatible archive, replace any dependencies with versions
`precompiled for Lambda <https://github.com/Miserlou/lambda-packages>`_, set up the function handler and necessary WSGI Middleware, upload the archive to S3, register it as a new Lambda function, create a new API Gateway resource, create WSGI-compatible routes for it, link it to the new Lambda function, and finally delete the archive from your S3 bucket. Handy!

Updates
-------

If your application has already been deployed and you only need to upload new Python code, but not touch the underlying routes, you can simply: ::

    $ zappa update production
    Updating..
    Your application is now live at: https://7k6anj0k99.execute-api.us-east-1.amazonaws.com/production

This creates a new archive, uploads it to S3 and updates the Lambda function to use the new code, but doesn't touch the API Gateway routes.
