=======================
Configuration Reference
=======================

Envirnments, such as *dev*, *staging*, and *production* are configured in the *zappa_settings.json* file.  Here is an example of defining many of the available settings:

::

    {
        "dev": {
            "api_key_required": false,
            "assume_policy": "my_assume_policy.json",
            "attach_policy": "my_attach_policy.json",
            "aws_region": "us-east-1",
            "cache_cluster_enabled": false,
            "cache_cluster_size": .5,
            "callbacks": {
                "settings": "my_app.settings_callback",
                "zip": "my_app.zip_callback",
                "post": "my_app.post_callback",
            },
            "cloudwatch_log_level": "OFF",
            "cloudwatch_data_trace": false,
            "cloudwatch_metrics_enabled": false,
            "debug": true
            "delete_zip": true
            "django_settings": "your_project.production_settings",
            "domain": "yourapp.yourdomain.com",
            "events": [
                {   // Recurring events
                    "function": "your_module.your_recurring_function",
                    "expression": "rate(1 minute)"
                },
                {   // AWS Reactive events
                    "function": "your_module.your_reactive_function",
                    "event_source": {
                        "arn":  "arn:aws:s3:::my-bucket",
                        "events": [
                            "s3:ObjectCreated:*"
                        ]
                    }
                }
            ],
            "exclude": ["*.gz", "*.pem"],
            "http_methods": ["GET", "POST"],
            "integration_response_codes": [200, 301, 404, 500],
            "keep_warm": true,
            "lambda_handler": "your_custom_handler",
            "log_level": "DEBUG",
            "memory_size": 512,
            "method_response_codes": [200, 301, 404, 500],
            "parameter_depth": 10,
            "prebuild_script": "your_module.your_function",
            "profile_name": "your-profile-name",
            "project_name": "MyProject",
            "remote_env_bucket": "my-project-config-files",
            "remote_env_file": "filename.json",
            "role_name": "MyLambdaRole",
            "s3_bucket": "dev-bucket",
            "settings_file": "~/Projects/MyApp/settings/dev_settings.py",
            "timeout_seconds": 30,
            "touch": false,
            "use_precompiled_packages": false,
            "use_apigateway": true,
            "vpc_config": {
                            "SubnetIds": [ "subnet-12345678" ],
                            "SecurityGroupIds": [ "sg-12345678" ]
                          }
        }    
    }

All values are standard JSON data types (Numbers, Strings, Booleans, Arrays, and Objects).

api_key_required
================

This boolean setting determines whether or not to enable securing API Gateway endpoints with x-api-key header.  The default value is *false*.

assume_policy
=============

This string setting indicates the name of the IAM assume policy JSON file.  This is an optional setting.

attach_policy
=============

This string setting indicates the name of the IAM attach policy JSON file.  This is an optional setting.

aws_region
==========

This string setting specifies which AWS Region to use.

The default value is US East, which is *"us-east-1"*.

cache_cluster_enabled
=====================

This boolean setting indicates whether to use the APIGW cash cluster.

The default value is *false*.

cache_cluster_size
==================

This number setting specifies the APIGW Cache Cluster size.

The default value is *0.5*.

callbacks
=========

This is an array with settings which define any custom functions during the Zappa deployment/update process.  This is an optional setting.

*settings*
----------

This is a string which names the custom callback used after loading the settings.

*zip*
-----

This is a string which names the custom callback used after creating the package.

*post*
------

This is a string which names the custom callback used after the command has executed.

cloudwatch_data_trace
=====================

This boolean setting indicates whether to log all data about received events.

cloudwatch_log_level
====================

This string setting enables and configures the desired logging level for the given staging.

Available options are *"OFF"* (default), *"INFO"*, and *"ERROR"*. 

cloudwatch_metrics_enabled
==========================

This boolean setting indicates whether additional API Gateway metrics are desired.

debug
=====

This boolean setting governs whether Zappa configuration errors tracebacks are to appear in HTTP 500 error pages.

delete_zip
==========

This boolean setting specifies wheter to delete the local zip archive after code updates.

django_settings
===============

This string setting indicates the modular path to your Django project's settings.  It is for Django projects only.

domain
======

This string setting is required if a domain will be used.

It should be in a format like *"yourapp.yourdomain.com"*.

events
======

This is an array with settings which describe the functions and schedules to execute them.

Each event should contain objects with values for *function* and *expression*.

*function*
----------

This string setting identifies the function being referenced in an event.

It should have a format like *"your_module.your_function"*.

*expression*
------------

This string setting provides an AWS Lambda schedule expression using Rate or Cron formats.  See the `AWS documentation <http://docs.aws.amazon.com/lambda/latest/dg/tutorial-scheduled-events-schedule-expressions.html>`_ for a description of currently accepable formats for this setting.  This is the setting that defines when the function should be executed.

exclude
=======

This is an array of regex string patterns to exclude from the archive.


http_methods
============

This array setting is a list of HTTP methods to route.  

Examples of HTTP methods are GET and POST, as in this example: *["GET", "POST"]*.


integration_response_codes
==========================

This is an array of integers which are integration response status codes to route.

This should in a formal like *[200, 301, 404, 500]*.

keep_warm
=========

This boolean setting is used to specify whether to create CloudWatch events to keep the server warm.

lambda_handler
==============

The string setting is the name of the Lambda handler.

The default is *"handler.lambda_handler"*.

log_level
=========

This string setting is used to set the Zappa log level.

The value of this setting can be either *"CRITICAL"*, *"ERROR"*, *"WARNING"*, *"INFO"* or *"DEBUG"*.  The default is *"DEBUG"*.

memory_size
===========

This number setting specifies the Lambda function memory in MB.

method_response_codes
=====================

This array setting is a list of method response status codes to route.

This should be in a format like *[200, 301, 404, 500]*.

parameter_depth
===============

This integer setting specifies the size of the URL depth to route.

This defaults to *8*.

prebuild_script
===============

This string setting identifies a function to execute before uploading code.

This should be in a format like *"your_module.your_function"*.

profile_name
============

This string setting identifies the profile name of the AWS credentials to use.

The default is *"default"*.

project_name
============

This string setting is the name of the project as it appears on AWS. 

It defaults to *a slugified `pwd`*.

remote_env_bucket
=================

This string setting defines an optional S3 bucket where the remote_env_file can be located.

remote_env_file
===============

This string setting names the file in the remote_env_bucket which contains a flat json object which is used to set custom environment variables.

role_name
=========

This string setting is name of the Lambda execution role.

s3_bucket
=========

This string setting is the name of the Zappa zip bucket.

settings_file
=============

This string setting is the full path for the server side settings file.

timeout_seconds
===============

This number setting specifies the maximum lifespan for the Lambda function in seconds.

The default is *30*.

touch
=====

This boolean setting determines whether to GET the production URL upon initial deployment.

Default is *true*.

use_precompiled_packages
========================

This boolean setting is used to indicate whether, if possible, to use the C-extension packages which have been pre-compiled for AWS Lambda.

use_apigateway
==============

This boolean setting indicates whether the API Gateway resource should be created.

The default is *true*.

vpc_config
==========

This setting provides some optional VPC configuration for Lambda function.  This value for this setting is an object with sub-settings.

*SubnetsIds*
------------

This is an array setting that is used to select subnets, which is a list of strings.

Note that not all availability zones support Lambda.


*SecurityGroupIds*
------------------

This is an array setting that is used to select security groups, which is a list of strings.
