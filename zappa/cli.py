#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Zappa CLI

Deploy arbitrary Python programs as serverless Zappa applications.

"""

from __future__ import unicode_literals
from __future__ import division

import argparse
import base64
import botocore
import click
import hjson as json
import inspect
import imp
import importlib
import logging
import os
import pkg_resources
import random
import re
import requests
import slugify
import string
import sys
import tempfile
import time
import zipfile
from dateutil import parser
from datetime import datetime,timedelta
from zappa import Zappa, logger
from util import check_new_version_available, detect_django_settings, detect_flask_apps

CUSTOM_SETTINGS = [
    'assume_policy',
    'attach_policy',
    'aws_region',
    'delete_local_zip',
    'delete_s3_zip',
    'exclude',
    'http_methods',
    'integration_response_codes',
    'method_header_types',
    'method_response_codes',
    'parameter_depth',
    'role_name',
    'touch',
]

CLI_COMMANDS = [
    'certify',
    'deploy',
    'init',
    'invoke',
    'manage',
    'rollback',
    'schedule',
    'status',
    'tail',
    'undeploy',
    'unschedule',
    'update'
]

##
# Main Input Processing
##

class ZappaCLI(object):
    """
    ZappaCLI object is responsible for loading the settings,
    handling the input arguments and executing the calls to the core library.

    """

    # Zappa settings
    zappa = None
    zappa_settings = None
    load_credentials = True

    api_stage = None
    app_function = None
    aws_region = None
    debug = None
    prebuild_script = None
    project_name = None
    profile_name = None
    lambda_arn = None
    lambda_name = None
    lambda_description = None
    s3_bucket_name = None
    settings_file = None
    zip_path = None
    vpc_config = None
    memory_size = None
    use_apigateway = None
    lambda_handler = None
    django_settings = None
    manage_roles = True
    exception_handler = None
    environment_variables = None
    authorizer = None

    stage_name_env_pattern = re.compile('^[a-zA-Z0-9_]+$')

    @property
    def stage_config(self):
        """A shortcut property for settings of staging."""
        # Backwards compatible for delete_zip setting that was more explicitly named delete_local_zip
        settings = self.zappa_settings[self.api_stage]
        if u'delete_zip' in settings:
            settings[u'delete_local_zip'] = settings.get(u'delete_zip')
        return settings

    def handle(self, argv=None):
        """
        Main function.

        Parses command, load settings and dispatches accordingly.

        """
        help_message = "Please supply a command to execute. Can be one of: {}".format(', '.join(x for x in sorted(CLI_COMMANDS)))

        parser = argparse.ArgumentParser(description='Zappa - Deploy Python applications to AWS Lambda and API Gateway.\n')
        parser.add_argument('command_env', metavar='U', type=str, nargs='*', help=help_message)
        parser.add_argument('-n', '--num-rollback', type=int, default=0,
                            help='The number of versions to rollback.')
        parser.add_argument('-s', '--settings_file', type=str, default='zappa_settings.json',
                            help='The path to a zappa settings file.')
        parser.add_argument('-a', '--app_function', type=str, default=None,
                            help='The WSGI application function.')
        parser.add_argument('-v', '--version', action='store_true', help='Print the zappa version', default=False)
        parser.add_argument('-y', '--yes', action='store_true', help='Auto confirm yes', default=False)
        parser.add_argument('--remove-logs', action='store_true', help='Removes log groups of api gateway and lambda task during the undeployment.', default=False)
        parser.add_argument('--raw', action='store_true', help='When invoking remotely, invoke this python as a string, not as a modular path.', default=False)
        parser.add_argument('--no-cleanup', action='store_true', help="Don't remove certificate files from /tmp during certify. Dangerous.", default=False)

        args = parser.parse_args(argv)

        vargs = vars(args)
        vargs_nosettings = vargs.copy()
        vargs_nosettings.pop('settings_file')
        if not any(vargs_nosettings.values()): # pragma: no cover
            parser.error(help_message)
            return

        # Version requires no arguments
        if args.version: # pragma: no cover
            self.print_version()
            sys.exit(0)

        # Parse the input
        command_env = vargs['command_env']
        command = command_env[0]

        if command not in CLI_COMMANDS:
            print("The command '{}' is not recognized. {}".format(command, help_message))
            return

        # Settings-based interactions will fail
        # before a project has been initialized.
        if command != 'init':

             # Load and Validate Settings File
            self.load_settings_file(vargs['settings_file'])

            if len(command_env) < 2: # pragma: no cover
                # If there's only one environment defined in the settings,
                # use that as the default.
                if len(self.zappa_settings.keys()) is 1:
                    self.api_stage = self.zappa_settings.keys()[0]
                else:
                    parser.error("Please supply an environment to interact with.")
                    return
            else:
                self.api_stage = command_env[1]

            if vargs['app_function'] is not None:
                self.app_function = vargs['app_function']

            # Load our settings
            try:
                self.load_settings(vargs['settings_file'])
            except ValueError as e:
                print("Error: {}".format(e.message))
                sys.exit(-1)
            self.callback('settings')

        # Hand it off
        if command == 'deploy': # pragma: no cover
            self.deploy()
        elif command == 'update': # pragma: no cover
            self.update()
        elif command == 'rollback': # pragma: no cover
            if vargs['num_rollback'] < 1: # pragma: no cover
                parser.error("Please enter the number of iterations to rollback.")
                return
            self.rollback(vargs['num_rollback'])
        elif command == 'invoke': # pragma: no cover

            if len(command_env) < 2:
                parser.error("Please enter the function to invoke.")
                return

            self.invoke(command_env[-1], raw_python=vargs['raw'])
        elif command == 'manage': # pragma: no cover

            if len(command_env) < 2:
                parser.error("Please enter the management command to invoke.")
                return

            if not self.django_settings:
                print("This command is for Django projects only!")
                print("If this is a Django project, please define django_settings in your zappa_settings.")
                return

            command_tail = command_env[2:]
            if len(command_tail) > 1:
                command = " ".join(command_tail) # ex: zappa manage dev "shell --version"
            else:
                command = command_tail[0] # ex: zappa manage dev showmigrations admin

            self.invoke(command, "manage")

        elif command == 'tail': # pragma: no cover
            self.tail()
        elif command == 'undeploy': # pragma: no cover
            self.undeploy(noconfirm=vargs['yes'], remove_logs=vargs['remove_logs'])
        elif command == 'schedule': # pragma: no cover
            self.schedule()
        elif command == 'unschedule': # pragma: no cover
            self.unschedule()
        elif command == 'status': # pragma: no cover
            self.status()
        elif command == 'init': # pragma: no cover
            self.init()
        elif command == 'certify': # pragma: no cover
            self.certify(no_cleanup=vargs['no_cleanup'])

    ##
    # The Commands
    ##

    def deploy(self):
        """
        Package your project, upload it to S3, register the Lambda function
        and create the API Gateway routes.

        """

        # Execute the prebuild script
        if self.prebuild_script:
            self.execute_prebuild_script()

        # Make sure this isn't already deployed.
        deployed_versions = self.zappa.get_lambda_function_versions(self.lambda_name)
        if len(deployed_versions) > 0:
            click.echo("This application is " + click.style("already deployed", fg="red") + " - did you mean to call " + click.style("update", bold=True) + "?")
            return

        # Make sure there isn't a new version available
        self.check_for_update()

        # Make sure the necessary IAM execution roles are available
        if self.manage_roles:
            try:
                self.zappa.create_iam_roles()
            except botocore.client.ClientError:
                click.echo(click.style("Failed", fg="red") + " to " + click.style("manage IAM roles", bold=True) + "!")
                click.echo("You may " + click.style("lack the necessary AWS permissions", bold=True) + " to automatically manage a Zappa execution role.")
                click.echo("To fix this, see here: " + click.style("https://github.com/Miserlou/Zappa#using-custom-aws-iam-roles-and-policie", bold=True))
                sys.exit(-1)

        # Create the Lambda Zip
        self.create_package()
        self.callback('zip')

        # Upload it to S3
        success = self.zappa.upload_to_s3(
                self.zip_path, self.s3_bucket_name)
        if not success: # pragma: no cover
            print("Unable to upload to S3. Quitting.")
            sys.exit(-1)

        # Register the Lambda function with that zip as the source
        # You'll also need to define the path to your lambda_handler code.
        self.lambda_arn = self.zappa.create_lambda_function(bucket=self.s3_bucket_name,
                                                       s3_key=self.zip_path,
                                                       function_name=self.lambda_name,
                                                       handler=self.lambda_handler,
                                                       description=self.lambda_description,
                                                       vpc_config=self.vpc_config,
                                                       timeout=self.timeout_seconds,
                                                       memory_size=self.memory_size)

        # Schedule events for this deployment
        self.schedule()

        endpoint_url = ''
        deployment_string = click.style("Deployment complete", fg="green", bold=True) + "!"
        if self.use_apigateway:

            # Create and configure the API Gateway

            template = self.zappa.create_stack_template(self.lambda_arn,
                                                        self.lambda_name,
                                                        self.api_key_required,
                                                        self.integration_content_type_aliases,
                                                        self.iam_authorization,
                                                        self.authorizer)

            self.zappa.update_stack(self.lambda_name, self.s3_bucket_name, wait=True)
            api_id = self.zappa.get_api_id(self.lambda_name)

            # Deploy the API!
            cache_cluster_enabled = self.stage_config.get('cache_cluster_enabled', False)
            cache_cluster_size = str(self.stage_config.get('cache_cluster_size', .5))
            endpoint_url = self.zappa.deploy_api_gateway(
                                        api_id=api_id,
                                        stage_name=self.api_stage,
                                        cache_cluster_enabled=cache_cluster_enabled,
                                        cache_cluster_size=cache_cluster_size,
                                        cloudwatch_log_level=self.zappa_settings[self.api_stage].get('cloudwatch_log_level', 'OFF'),
                                        cloudwatch_data_trace=self.zappa_settings[self.api_stage].get('cloudwatch_data_trace', False),
                                        cloudwatch_metrics_enabled=self.zappa_settings[self.api_stage].get('cloudwatch_metrics_enabled', False),
                                    )
            deployment_string = deployment_string + ": {}".format(endpoint_url)

            # Create/link API key
            if self.api_key_required:
                if self.api_key is None:
                    self.zappa.create_api_key(api_id=api_id, stage_name=self.api_stage)
                else:
                    self.zappa.add_api_stage_to_api_key(api_key=self.api_key, api_id=api_id, stage_name=self.api_stage)

            if self.stage_config.get('touch', True):
                requests.get(endpoint_url)

        # Finally, delete the local copy our zip package
        if self.stage_config.get('delete_local_zip', True):
            self.remove_local_zip()

        # Remove the uploaded zip from S3, because it is now registered..
        if self.stage_config.get('delete_s3_zip', True):
            self.zappa.remove_from_s3(self.zip_path, self.s3_bucket_name)

        self.callback('post')

        click.echo(deployment_string)

    def update(self):
        """
        Repackage and update the function code.
        """

        # Execute the prebuild script
        if self.prebuild_script:
            self.execute_prebuild_script()

        # Make sure there isn't a new version available
        self.check_for_update()

        # Temporary version check
        try:
            updated_time = 1472581018
            function_response = self.zappa.lambda_client.get_function(FunctionName=self.lambda_name)
            conf = function_response['Configuration']
            last_updated = parser.parse(conf['LastModified'])
            last_updated_unix = time.mktime(last_updated.timetuple())
        except Exception as e:
            click.echo(click.style("Warning!", fg="red") + " Couldn't get function - have you deployed yet?")
            sys.exit(-1)

        if last_updated_unix <= updated_time:
            click.echo(click.style("Warning!", fg="red") + " You may have upgraded Zappa since deploying this application. You will need to " + click.style("redeploy", bold=True) + " for this deployment to work properly!")

        # Make sure the necessary IAM execution roles are available
        if self.manage_roles:
            try:
                self.zappa.create_iam_roles()
            except botocore.client.ClientError:
                click.echo(click.style("Failed", fg="red") + " to " + click.style("manage IAM roles", bold=True) + "!")
                click.echo("You may " + click.style("lack the necessary AWS permissions", bold=True) + " to automatically manage a Zappa execution role.")
                click.echo("To fix this, see here: " + click.style("https://github.com/Miserlou/Zappa#using-custom-aws-iam-roles-and-policie", bold=True))
                sys.exit(-1)

        # Create the Lambda Zip,
        self.create_package()
        self.callback('zip')

        # Upload it to S3
        success = self.zappa.upload_to_s3(self.zip_path, self.s3_bucket_name)
        if not success: # pragma: no cover
            print("Unable to upload to S3. Quitting.")
            sys.exit(-1)

        # Register the Lambda function with that zip as the source
        # You'll also need to define the path to your lambda_handler code.
        self.lambda_arn = self.zappa.update_lambda_function(
            self.s3_bucket_name, self.zip_path, self.lambda_name)

        # Remove the uploaded zip from S3, because it is now registered..
        if self.stage_config.get('delete_s3_zip', True):
            self.zappa.remove_from_s3(self.zip_path, self.s3_bucket_name)

        # Update the configuration, in case there are changes.
        self.lambda_arn = self.zappa.update_lambda_configuration(lambda_arn=self.lambda_arn,
                                                       function_name=self.lambda_name,
                                                       handler=self.lambda_handler,
                                                       description=self.lambda_description,
                                                       vpc_config=self.vpc_config,
                                                       timeout=self.timeout_seconds,
                                                       memory_size=self.memory_size)

        # Finally, delete the local copy our zip package
        if self.stage_config.get('delete_local_zip', True):
            self.remove_local_zip()

        if self.use_apigateway:

            self.zappa.create_stack_template(self.lambda_arn,
                                                        self.lambda_name,
                                                        self.api_key_required,
                                                        self.integration_content_type_aliases,
                                                        self.iam_authorization,
                                                        self.authorizer)
            self.zappa.update_stack(self.lambda_name, self.s3_bucket_name, wait=True, update_only=True)

            self.zappa.update_stage_config(
                self.lambda_name,
                self.api_stage,
                self.zappa_settings[self.api_stage].get('cloudwatch_log_level', 'OFF'),
                self.zappa_settings[self.api_stage].get('cloudwatch_data_trace', False),
                self.zappa_settings[self.api_stage].get('cloudwatch_metrics_enabled', False)
            )

            if self.stage_config.get('domain', None):
                endpoint_url = self.stage_config.get('domain')
            else:
                endpoint_url = self.zappa.get_api_url(self.lambda_name, self.api_stage)
        else:
            endpoint_url = None

        self.schedule()

        self.callback('post')

        if endpoint_url and 'https://' not in endpoint_url:
            endpoint_url = 'https://' + endpoint_url

        deployed_string = "Your updated Zappa deployment is " + click.style("live", fg='green', bold=True) + "!"
        if self.use_apigateway:
            deployed_string = deployed_string + ": " + click.style("{}".format(endpoint_url), bold=True)

            api_url = None
            if endpoint_url and 'amazonaws.com' not in endpoint_url:
                api_url = self.zappa.get_api_url(
                    self.lambda_name,
                    self.api_stage)

                if endpoint_url != api_url:
                    deployed_string = deployed_string + " (" + api_url + ")"

            if self.stage_config.get('touch', True):
                if api_url:
                    requests.get(api_url)
                elif endpoint_url:
                    requests.get(endpoint_url)

        click.echo(deployed_string)

    def rollback(self, revision):
        """
        Rollsback the currently deploy lambda code to a previous revision.
        """

        print("Rolling back..")

        self.zappa.rollback_lambda_function_version(
            self.lambda_name, versions_back=revision)
        print("Done!")

    def tail(self, keep_open=True):
        """
        Tail this function's logs.

        """

        try:
            # Tail the available logs
            all_logs = self.zappa.fetch_logs(self.lambda_name)
            self.print_logs(all_logs)

            # Keep polling, and print any new logs.
            loop = True
            while loop:
                all_logs_again = self.zappa.fetch_logs(self.lambda_name)
                new_logs = []
                for log in all_logs_again:
                    if log not in all_logs:
                        new_logs.append(log)

                self.print_logs(new_logs)
                all_logs = all_logs + new_logs
                if not keep_open:
                    loop = False
        except KeyboardInterrupt: # pragma: no cover
            # Die gracefully
            try:
                sys.exit(0)
            except SystemExit:
                os._exit(130)

    def undeploy(self, noconfirm=False, remove_logs=False):
        """
        Tear down an exiting deployment.
        """

        if not noconfirm: # pragma: no cover
            confirm = raw_input("Are you sure you want to undeploy? [y/n] ")
            if confirm != 'y':
                return

        if self.use_apigateway:
            if remove_logs:
                self.zappa.remove_api_gateway_logs(self.lambda_name)

            domain_name = self.stage_config.get('domain', None)

            # Only remove the api key when not specified
            if self.api_key_required and self.api_key is None:
                api_id = self.zappa.get_api_id(self.lambda_name)
                self.zappa.remove_api_key(api_id, self.api_stage)

            gateway_id = self.zappa.undeploy_api_gateway(
                self.lambda_name,
                domain_name=domain_name
            )

        self.unschedule()  # removes event triggers, including warm up event.

        self.zappa.delete_lambda_function(self.lambda_name)
        if remove_logs:
            self.zappa.remove_lambda_function_logs(self.lambda_name)

        click.echo(click.style("Done", fg="green", bold=True) + "!")

    def schedule(self):
        """
        Given a a list of functions and a schedule to execute them,
        setup up regular execution.

        """
        events = self.stage_config.get('events', [])

        if events:
            if not isinstance(events, list): # pragma: no cover
                print("Events must be supplied as a list.")
                return

        for event in events:
            self.collision_warning(event.get('function'))

        if self.zappa_settings[self.api_stage].get('keep_warm', True):
            if not events:
                events = []

            keep_warm_rate = self.zappa_settings[self.api_stage].get('keep_warm_expression', "rate(4 minutes)")
            events.append({'name': 'zappa-keep-warm',
                           'function': 'handler.keep_warm_callback',
                           'expression': keep_warm_rate,
                           'description': 'Zappa Keep Warm - {}'.format(self.lambda_name)})


        if self.zappa_settings[self.api_stage].get('lets_encrypt_expression'):

            function_response = self.zappa.lambda_client.get_function(FunctionName=self.lambda_name)
            conf = function_response['Configuration']
            timeout = conf['Timeout']

            if timeout < 60:
                click.echo(click.style("Unable to schedule certificate autorenewer!", fg="red", bold=True) + " Please redeploy with a " + click.style("timeout_seconds", bold=True) + " greater than 60!")
            else:
                events.append({'name': 'zappa-le-certify',
                               'function': 'handler.certify_callback',
                               'expression': self.zappa_settings[self.api_stage].get('lets_encrypt_expression'),
                               'description': 'Zappa LE Certificate Renewer - {}'.format(self.lambda_name)})

        if events:
            try:
                function_response = self.zappa.lambda_client.get_function(FunctionName=self.lambda_name)
            except botocore.exceptions.ClientError as e: # pragma: no cover
                click.echo(click.style("Function does not exist", fg=yellow) + ", please " + click.style("deploy", bold=True) + "first. Ex:" + click.style("zappa deploy {}.".format(self.api_stage), bold=True))
                sys.exit(-1)

            print("Scheduling..")
            self.zappa.schedule_events(
                lambda_arn=function_response['Configuration']['FunctionArn'],
                lambda_name=self.lambda_name,
                events=events
                )


    def unschedule(self):
        """
        Given a a list of scheduled functions,
        tear down their regular execution.

        """

        # Run even if events are not defined to remove previously existing ones (thus default to []).
        events = self.stage_config.get('events', [])

        if not isinstance(events, list): # pragma: no cover
            print("Events must be supplied as a list.")
            return

        function_arn = None
        try:
            function_response = self.zappa.lambda_client.get_function(FunctionName=self.lambda_name)
            function_arn = function_response['Configuration']['FunctionArn']
        except botocore.exceptions.ClientError as e: # pragma: no cover
            print("Function does not exist, you should deploy first. Ex: zappa deploy {}. "
                  "Proceeding to unschedule CloudWatch based events.".format(self.api_stage))
            sys.exit(-1)

        print("Unscheduling..")
        self.zappa.unschedule_events(
            lambda_name=self.lambda_name,
            lambda_arn=function_arn,
            events=events,
            )


    def invoke(self, function_name, raw_python=False):
        """
        Invoke a remote function.
        """

        # Invoke it!
        if raw_python:
            command = {'raw_command': function_name}
        else:
            command = {'command': function_name} # This is really a string

        # Can't use hjson
        import json as json

        response = self.zappa.invoke_lambda_function(
            self.lambda_name,
            json.dumps(command),
            invocation_type='RequestResponse',
        )

        if 'LogResult' in response:
            print(base64.b64decode(response['LogResult']))
        else:
            print(response)

    def status(self):
        """
        Describe the status of the current deployment.
        """

        click.echo("Status for " + click.style(self.lambda_name, bold=True) + ": ")

        def tabular_print(title, value):
            """
            Convience function for priting formatted table items.
            """
            click.echo('%-*s%s' % (32, click.style("\t" + title, fg='green') + ':', str(value)))
            return

        # Lambda Env Details
        lambda_versions = self.zappa.get_lambda_function_versions(self.lambda_name)
        if not lambda_versions:
            click.echo(click.style("\tNo Lambda detected - have you deployed yet?", fg='red'))
            return False
        else:
            tabular_print("Lambda Versions", len(lambda_versions))
        function_response = self.zappa.lambda_client.get_function(FunctionName=self.lambda_name)
        conf = function_response['Configuration']
        tabular_print("Lambda Name", self.lambda_name)
        tabular_print("Lambda ARN", conf['FunctionArn'])
        tabular_print("Lambda Role ARN", conf['Role'])
        tabular_print("Lambda Handler", conf['Handler'])
        tabular_print("Lambda Code Size", conf['CodeSize'])
        tabular_print("Lambda Version", conf['Version'])
        tabular_print("Lambda Last Modified", conf['LastModified'])
        tabular_print("Lambda Memory Size", conf['MemorySize'])
        tabular_print("Lambda Timeout", conf['Timeout'])
        tabular_print("Lambda Runtime", conf['Runtime'])
        if 'VpcConfig' in conf.keys():
            tabular_print("Lambda VPC ID", conf.get('VpcConfig', {}).get('VpcId', 'Not assigned'))
        else:
            tabular_print("Lambda VPC ID", None)

        # Calculated statistics
        try:
            function_invocations = self.zappa.cloudwatch.get_metric_statistics(
                                       Namespace='AWS/Lambda',
                                       MetricName='Invocations',
                                       StartTime=datetime.utcnow()-timedelta(days=1),
                                       EndTime=datetime.utcnow(),
                                       Period=1440,
                                       Statistics=['Sum'],
                                       Dimensions=[{'Name': 'FunctionName',
                                                    'Value': '{}'.format(self.lambda_name)}]
                                       )['Datapoints'][0]['Sum']
        except Exception as e:
            function_invocations = 0
        try:
            function_errors = self.zappa.cloudwatch.get_metric_statistics(
                                       Namespace='AWS/Lambda',
                                       MetricName='Errors',
                                       StartTime=datetime.utcnow()-timedelta(days=1),
                                       EndTime=datetime.utcnow(),
                                       Period=1440,
                                       Statistics=['Sum'],
                                       Dimensions=[{'Name': 'FunctionName',
                                                    'Value': '{}'.format(self.lambda_name)}]
                                       )['Datapoints'][0]['Sum']
        except Exception as e:
            function_errors = 0

        try:
            error_rate = "{0:.2f}%".format(function_errors / function_invocations * 100)
        except:
            error_rate = "Error calculating"
        tabular_print("Invocations (24h)", int(function_invocations))
        tabular_print("Errors (24h)", int(function_errors))
        tabular_print("Error Rate (24h)", error_rate)

        # URLs
        if self.zappa_settings[self.api_stage].get('use_apigateway', True):
            api_url = self.zappa.get_api_url(
                self.lambda_name,
                self.api_stage)

            tabular_print("API Gateway URL", api_url)

            # Api Keys
            api_id = self.zappa.get_api_id(self.lambda_name)
            for api_key in self.zappa.get_api_keys(api_id, self.api_stage):
                tabular_print("API Gateway x-api-key", api_key)

            # There literally isn't a better way to do this.
            # AWS provides no way to tie a APIGW domain name to its Lambda funciton.
            domain_url = self.stage_config.get('domain', None)
            if domain_url:
                tabular_print("Domain URL", 'https://' + domain_url)
            else:
                tabular_print("Domain URL", "None Supplied")

        # Scheduled Events
        event_rules = self.zappa.get_event_rules_for_lambda(lambda_name=self.lambda_name)
        tabular_print("Num. Event Rules", len(event_rules))
        for rule in event_rules:
            rule_name = rule['Name']
            print('')
            tabular_print("Event Rule Name", rule_name)
            tabular_print("Event Rule Schedule", rule.get(u'ScheduleExpression', None))
            tabular_print("Event Rule State", rule.get(u'State', None).title())
            tabular_print("Event Rule ARN", rule.get(u'Arn', None))

        # TODO: S3/SQS/etc. type events?

        return True

    def print_version(self): # pragma: no cover
        """
        Print the current zappa version.
        """
        version = pkg_resources.require("zappa")[0].version
        print(version)

    def check_stage_name(self, stage_name):
        """
        Make sure the stage name matches the AWS-allowed pattern

        (calls to apigateway_client.create_deployment, will fail with error
        message "ClientError: An error occurred (BadRequestException) when
        calling the CreateDeployment operation: Stage name only allows
        a-zA-Z0-9_" if the pattern does not match)
        """
        if self.stage_name_env_pattern.match(stage_name):
            return True
        raise ValueError("AWS requires stage name to match a-zA-Z0-9_")


    def init(self, settings_file="zappa_settings.json"):
        """
        Initialize a new Zappa project by creating a new zappa_settings.json in a guided process.

        This should probably be broken up into few separate componants once it's stable.
        Testing these raw_inputs requires monkeypatching with mock, which isn't pretty.

        """

        # Ensure that we don't already have a zappa_settings file.
        if os.path.isfile(settings_file):
            click.echo("This project is " + click.style("already initialized", fg="red", bold=True) + "!")
            sys.exit() # pragma: no cover

        # Ensure P2 until Lambda supports it.
        if sys.version_info >= (3,0): # pragma: no cover
            print("Zappa curently only works with Python 2, until AWS Lambda adds Python 3 support.")
            sys.exit() # pragma: no cover

        # Ensure inside virtualenv.
        if not ( hasattr(sys, 'prefix') or hasattr(sys, 'real_prefix') or hasattr(sys, 'base_prefix') ): # pragma: no cover
            print("Zappa must be run inside of a virtual environment!")
            print("Learn more about virtual environments here: http://docs.python-guide.org/en/latest/dev/virtualenvs/")
            sys.exit()

        # Explain system.
        click.echo(click.style(u"""\n███████╗ █████╗ ██████╗ ██████╗  █████╗
╚══███╔╝██╔══██╗██╔══██╗██╔══██╗██╔══██╗
  ███╔╝ ███████║██████╔╝██████╔╝███████║
 ███╔╝  ██╔══██║██╔═══╝ ██╔═══╝ ██╔══██║
███████╗██║  ██║██║     ██║     ██║  ██║
╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝     ╚═╝  ╚═╝\n""", fg='green', bold=True))

        click.echo(click.style("Welcome to ", bold=True) + click.style("Zappa", fg='green', bold=True) + click.style("!\n", bold=True))
        click.echo(click.style("Zappa", bold=True) + " is a system for running server-less Python web applications on AWS Lambda and AWS API Gateway.")
        click.echo("This `init` command will help you create and configure your new Zappa deployment.")
        click.echo("Let's get started!\n")

        # Create Env
        while True:
            click.echo("Your Zappa configuration can support multiple production environments, like '" + click.style("dev", bold=True)  + "', '" + click.style("staging", bold=True)  + "', and '" + click.style("production", bold=True)  + "'.")
            env = raw_input("What do you want to call this environment (default 'dev'): ") or "dev"
            try:
                self.check_stage_name(env)
                break
            except ValueError:
                click.echo(click.style("Environment names must match a-zA-Z0-9_", fg='red'))

        # Create Bucket
        click.echo("\nYour Zappa deployments will need to be uploaded to a " + click.style("private S3 bucket", bold=True)  + ".")
        click.echo("If you don't have a bucket yet, we'll create one for you too.")
        default_bucket = "zappa-" + ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(9))
        bucket = raw_input("What do you want call your bucket? (default '%s'): " % default_bucket) or default_bucket
        # TODO actually create bucket.

        # Detect Django/Flask
        try: # pragma: no cover
            import django
            has_django = True
        except ImportError, e:
            has_django = False

        try: # pragma: no cover
            import flask
            has_flask = True
        except ImportError, e:
            has_flask = False

        print('')
        # App-specific
        if has_django: # pragma: no cover
            click.echo("It looks like this is a " + click.style("Django", bold=True)  + " application!")
            click.echo("What is the " + click.style("module path", bold=True)  + " to your projects's Django settings?")
            django_settings = None

            matches = detect_django_settings()
            while django_settings in [None, '']:
                if matches:
                    click.echo("We discovered: " + click.style(', '.join('{}'.format(i) for v, i in enumerate(matches)), bold=True))
                    django_settings = raw_input("Where are your project's settings? (default '%s'): " % matches[0]) or matches[0]
                else:
                    click.echo("(This will likely be something like 'your_project.settings')")
                    django_settings = raw_input("Where are your project's settings?: ")
            django_settings = django_settings.replace("'", "")
            django_settings = django_settings.replace('"', "")
        else:
            matches = None
            if has_flask:
                click.echo("It looks like this is a " + click.style("Flask", bold=True)  + " application.")
                matches = detect_flask_apps()
            click.echo("What's the " + click.style("modular path", bold=True)  + " to your app's function?")
            click.echo("This will likely be something like 'your_module.app'.")
            app_function = None
            while app_function in [None, '']:
                if matches:
                    click.echo("We discovered: " + click.style(', '.join('{}'.format(i) for v, i in enumerate(matches)), bold=True))
                    app_function = raw_input("Where is your app's function? (default '%s'): " % matches[0]) or matches[0]
                else:
                    app_function = raw_input("Where is your app's function?: ")
            app_function = app_function.replace("'", "")
            app_function = app_function.replace('"', "")

        # TODO: Create VPC?
        # Memory size? Time limit?

        # Confirm
        zappa_settings = {
            env: {
                's3_bucket': bucket,
            }
        }
        if has_django:
            zappa_settings[env]['django_settings'] = django_settings
        else:
            zappa_settings[env]['app_function'] = app_function

        import json as json # hjson is fine for loading, not fine for writing.
        zappa_settings_json = json.dumps(zappa_settings, sort_keys=True, indent=4)

        click.echo("\nOkay, here's your " + click.style("zappa_settings.js", bold=True) + ":\n")
        click.echo(click.style(zappa_settings_json, fg="yellow", bold=False))

        confirm = raw_input("\nDoes this look " + click.style("okay", bold=True, fg="green")  + "? (default y) [y/n]: ") or 'yes'
        if confirm[0] not in ['y', 'Y', 'yes', 'YES']:
            click.echo("" + click.style("Sorry", bold=True, fg='red') + " to hear that! Please init again.")
            return

        # Write
        with open("zappa_settings.json", "w") as zappa_settings_file:
            zappa_settings_file.write(zappa_settings_json)

        click.echo("\n" + click.style("Done", bold=True) + "! Now you can " + click.style("deploy", bold=True)  + " your Zappa application by executing:\n")
        click.echo(click.style("\t$ zappa deploy %s" % env, bold=True))

        click.echo("\nAfter that, you can " + click.style("update", bold=True) + " your application code with:\n")
        click.echo(click.style("\t$ zappa update %s" % env, bold=True))

        click.echo("\nTo learn more, check out our project page on " + click.style("GitHub", bold=True) + " here: " + click.style("https://github.com/Miserlou/Zappa", fg="cyan", bold=True))
        click.echo("and stop by our " + click.style("Slack", bold=True) + " channel here: " + click.style("http://bit.do/zappa", fg="cyan", bold=True))
        click.echo("\nEnjoy!,")
        click.echo(" ~ Team " + click.style("Zappa", bold=True) + "!")

        return

    def certify(self, no_cleanup=False):
        """
        Register or update a domain certificate for this env.
        """

        # Give warning on --no-cleanup
        if no_cleanup:
            clean_up = False
            click.echo(click.style("Warning!", fg="yellow", bold=True) + " You are calling certify with " + click.style("--no-cleanup", bold=True) + ". Your certificate files will remain in the system temporary directory after this command exectutes!")
        else:
            clean_up = True

        # Make sure this isn't already deployed.
        deployed_versions = self.zappa.get_lambda_function_versions(self.lambda_name)
        if len(deployed_versions) == 0:
            click.echo("This application " + click.style("isn't deployed yet", fg="red") + " - did you mean to call " + click.style("deploy", bold=True) + "?")
            return

        # Get install account_key to /tmp/account_key.pem
        account_key_location = self.stage_config.get('lets_encrypt_key')
        domain = self.stage_config.get('domain')

        if not account_key_location:
            click.echo("Can't certify a domain without " + click.style("lets_encrypt_key", fg="red", bold=True) + " configured!")
            return
        if not domain:
            click.echo("Can't certify a domain without " + click.style("domain", fg="red", bold=True) + " configured!")
            return

        if 's3://' in account_key_location:
            bucket = account_key_location.split('s3://')[1].split('/')[0]
            key_name = account_key_location.split('s3://')[1].split('/')[1]
            self.zappa.s3_client.download_file(bucket, key_name, '/tmp/account.key')
        else:
            from shutil import copyfile
            copyfile(account_key_location, '/tmp/account.key')

        click.echo("Certifying domain " + click.style(domain, fg="green", bold=True) + "..")

        # Get cert and update domain.
        from letsencrypt import get_cert_and_update_domain, cleanup
        cert_success = get_cert_and_update_domain(
                self.zappa,
                self.lambda_name,
                self.api_stage,
                domain,
                clean_up
            )

        # Deliberately undocumented feature (for now, at least.)
        # We are giving the user the ability to shoot themselves in the foot.
        # _This is probably not a good idea._
        # However, I am sick and tired of hitting the Let's Encrypt cert
        # limit while testing.
        if clean_up:
            cleanup()

        if cert_success:
            click.echo("Certificate " + click.style("updated", fg="green", bold=True) + "!")
        else:
            click.echo(click.style("Failed", fg="red", bold=True) + " to generate or install certificate! :(")
            click.echo("\n==============\n")
            shamelessly_promote()

    ##
    # Utility
    ##

    def callback(self, position):
        """
        Allows the execution of custom code between creation of the zip file and deployment to AWS.

        :return: None
        """
        callbacks = self.stage_config.get('callbacks', {})
        callback = callbacks.get(position)

        if callback:
            (mod_name, cb_func) = callback.rsplit('.', 1)

            module_ = importlib.import_module(mod_name)
            getattr(module_, cb_func)(self)  # Call the function passing self

    def check_for_update(self):
        """
        Print a warning if there's a new Zappa version available.
        """
        try:
            version = pkg_resources.require("zappa")[0].version
            updateable = check_new_version_available(version)
            if updateable:
                click.echo(click.style("Important!", fg="yellow", bold=True) + " A new version of " + click.style("Zappa", bold=True) + " is available!")
                click.echo("Upgrade with: " + click.style("pip install zappa --upgrade", bold=True))
                click.echo("Visit the project page on GitHub to see the latest changes: " + click.style("https://github.com/Miserlou/Zappa", bold=True))
        except Exception as e: # pragma: no cover
            print(e)
            return

    def load_settings(self, settings_file="zappa_settings.json", session=None):
        """
        Load the local zappa_settings.json file.

        An existing boto session can be supplied, though this is likely for testing purposes.

        Returns the loaded Zappa object.
        """

        # Ensure we're passed a valid settings file.
        if not os.path.isfile(settings_file):
            print("Please configure your zappa_settings file.")
            sys.exit(-1) # pragma: no cover

        # Load up file
        self.load_settings_file(settings_file)

        # Make sure that the environments are valid names:
        for stage_name in self.zappa_settings.keys():
            try:
                self.check_stage_name(stage_name)
            except ValueError:
                raise ValueError("API stage names must match a-zA-Z0-9_ ; '{0!s}' does not.".format(stage_name))

        # Make sure that this environment is our settings
        if self.api_stage not in self.zappa_settings.keys():
            print("Please define '{0!s}' in your Zappa settings.".format(self.api_stage))
            sys.exit(-1) # pragma: no cover

        # We need a working title for this project. Use one if supplied, else cwd dirname.
        if 'project_name' in self.stage_config: # pragma: no cover
            self.project_name = self.stage_config['project_name']
        else:
            self.project_name = slugify.slugify(os.getcwd().split(os.sep)[-1])[:15]

        if len(self.project_name) > 15: # pragma: no cover
            click.echo(click.style("Warning", fg="red", bold=True) + "! Your " + click.style("project_name", bold=True) + " may be too long to deploy! Please make it <16 characters.")

        # The name of the actual AWS Lambda function, ex, 'helloworld-dev'
        # Django's slugify doesn't replace _, but this does.
        self.lambda_name = slugify.slugify(self.project_name + '-' + self.api_stage)

        # Load environment-specific settings
        self.s3_bucket_name = self.zappa_settings[
            self.api_stage].get('s3_bucket', "zappa-" + ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(9)))
        self.vpc_config = self.zappa_settings[
            self.api_stage].get('vpc_config', {})
        self.memory_size = self.zappa_settings[
            self.api_stage].get('memory_size', 512)
        self.app_function = self.zappa_settings[
            self.api_stage].get('app_function', None)
        self.exception_handler = self.zappa_settings[
            self.api_stage].get('exception_handler', None)
        self.aws_region = self.zappa_settings[
            self.api_stage].get('aws_region', 'us-east-1')
        self.debug = self.zappa_settings[
            self.api_stage].get('debug', True)
        self.prebuild_script = self.zappa_settings[
            self.api_stage].get('prebuild_script', None)
        self.profile_name = self.zappa_settings[
            self.api_stage].get('profile_name', None)
        self.log_level = self.zappa_settings[
            self.api_stage].get('log_level', "DEBUG")
        self.domain = self.zappa_settings[
            self.api_stage].get('domain', None)
        self.timeout_seconds = self.zappa_settings[
            self.api_stage].get('timeout_seconds', 30)
        self.use_apigateway = self.zappa_settings[
            self.api_stage].get('use_apigateway', True)
        self.integration_content_type_aliases = self.zappa_settings[
            self.api_stage].get('integration_content_type_aliases', {})
        self.lambda_handler = self.zappa_settings[
            self.api_stage].get('lambda_handler', 'handler.lambda_handler')
        self.remote_env_bucket = self.zappa_settings[
            self.api_stage].get('remote_env_bucket', None)
        self.remote_env_file = self.zappa_settings[
            self.api_stage].get('remote_env_file', None)
        self.settings_file = self.zappa_settings[
            self.api_stage].get('settings_file', None)
        self.django_settings = self.zappa_settings[
            self.api_stage].get('django_settings', None)
        self.manage_roles = self.zappa_settings[
            self.api_stage].get('manage_roles', True)
        self.api_key_required = self.stage_config.get('api_key_required', False)
        self.api_key = self.zappa_settings[
            self.api_stage].get('api_key')
        self.iam_authorization = self.stage_config.get('iam_authorization', False)
        self.lambda_description = self.zappa_settings[
            self.api_stage].get('lambda_description', "Zappa Deployment")
        self.environment_variables = self.zappa_settings[
            self.api_stage].get('environment_variables', {})
        self.authorizer = self.stage_config.get('authorizer', {})

        self.zappa = Zappa( boto_session=session,
                            profile_name=self.profile_name,
                            aws_region=self.aws_region,
                            load_credentials=self.load_credentials
                            )

        for setting in CUSTOM_SETTINGS:
            if setting in self.stage_config:
                setting_val = self.stage_config[setting]
                # Read the policy file contents.
                if setting.endswith('policy'):
                    with open(setting_val, 'r') as f:
                        setting_val = f.read()
                setattr(self.zappa, setting, setting_val)

        if self.app_function:
            self.collision_warning(self.app_function)
            if self.app_function[-3:] == '.py':
                click.echo(click.style("Warning!", fg="yellow", bold=True) + " Your app_function is pointing to a " + click.style("file and not a function", bold=True) + "! It should probably be something like 'my_file.app', not 'my_file.py'!")

        return self.zappa

    def load_settings_file(self, settings_file="zappa_settings.json"):
        """
        Load our settings file.
        """

        with open(settings_file) as json_file:
            try:
                self.zappa_settings = json.load(json_file)
            except ValueError:
                raise ValueError("Unable to load the zappa settings JSON. It may be malformed.")

    def create_package(self):
        """
        Ensure that the package can be properly configured,
        and then create it.

        """

        # Create the Lambda zip package (includes project and virtualenvironment)
        # Also define the path the handler file so it can be copied to the zip
        # root for Lambda.
        current_file = os.path.dirname(os.path.abspath(
            inspect.getfile(inspect.currentframe())))
        handler_file = os.sep.join(current_file.split(os.sep)[0:]) + os.sep + 'handler.py'

        # Create the zip file
        self.zip_path = self.zappa.create_lambda_zip(
                self.lambda_name,
                handler_file=handler_file,
                use_precompiled_packages=self.stage_config.get('use_precompiled_packages', True),
                exclude=self.stage_config.get('exclude', [])
            )

        # Throw custom setings into the zip file
        with zipfile.ZipFile(self.zip_path, 'a') as lambda_zip:

            settings_s = "# Generated by Zappa\n"

            if self.app_function:
                app_module, app_function = self.app_function.rsplit('.', 1)
                settings_s = settings_s + "APP_MODULE='{0!s}'\nAPP_FUNCTION='{1!s}'\n".format(app_module, app_function)

            if self.exception_handler:
                settings_s += "EXCEPTION_HANDLER='{0!s}'\n".format(self.exception_handler)
            else:
                settings_s += "EXCEPTION_HANDLER=None\n"

            if self.debug:
                settings_s = settings_s + "DEBUG=True\n"
            else:
                settings_s = settings_s + "DEBUG=False\n"

            settings_s = settings_s + "LOG_LEVEL='{0!s}'\n".format((self.log_level))

            # If we're on a domain, we don't need to define the /<<env>> in
            # the WSGI PATH
            if self.domain:
                settings_s = settings_s + "DOMAIN='{0!s}'\n".format((self.domain))
            else:
                settings_s = settings_s + "DOMAIN=None\n"

            # Pass through remote config bucket and path
            if self.remote_env_bucket and self.remote_env_file:
                settings_s = settings_s + "REMOTE_ENV_BUCKET='{0!s}'\n".format(
                    self.remote_env_bucket
                )
                settings_s = settings_s + "REMOTE_ENV_FILE='{0!s}'\n".format(
                    self.remote_env_file
                )

            # Local envs
            settings_s = settings_s + "ENVIRONMENT_VARIABLES={0}\n".format(
                    dict(self.environment_variables)
                )

            # We can be environment-aware
            settings_s = settings_s + "API_STAGE='{0!s}'\n".format((self.api_stage))
            settings_s = settings_s + "PROJECT_NAME='{0!s}'\n".format((self.project_name))

            if self.settings_file:
                settings_s = settings_s + "SETTINGS_FILE='{0!s}'\n".format((self.settings_file))
            else:
                settings_s = settings_s + "SETTINGS_FILE=None\n"

            if self.django_settings:
                settings_s = settings_s + "DJANGO_SETTINGS='{0!s}'\n".format((self.django_settings))
            else:
                settings_s = settings_s + "DJANGO_SETTINGS=None\n"

            # AWS Events function mapping
            event_mapping = {}
            events = self.stage_config.get('events', [])
            for event in events:
                arn = event.get('event_source', {}).get('arn')
                function = event.get('function')
                if arn and function:
                    event_mapping[arn] = function
            settings_s = settings_s + "AWS_EVENT_MAPPING={0!s}\n".format(event_mapping)

            # Authorizer config
            authorizer_function = self.authorizer.get('function', None)
            if authorizer_function:
                settings_s += "AUTHORIZER_FUNCTION='{0!s}'\n".format(authorizer_function)


            # Copy our Django app into root of our package.
            # It doesn't work otherwise.
            if self.django_settings:
                base = __file__.rsplit(os.sep, 1)[0]
                django_py = ''.join(os.path.join([base, os.sep, 'ext', os.sep, 'django_zappa.py']))
                lambda_zip.write(django_py, 'django_zappa_app.py')

            # Lambda requires a specific chmod
            temp_settings = tempfile.NamedTemporaryFile(delete=False)
            os.chmod(temp_settings.name, 0644)
            temp_settings.write(settings_s)
            temp_settings.close()
            lambda_zip.write(temp_settings.name, 'zappa_settings.py')
            os.remove(temp_settings.name)

    def remove_local_zip(self):
        """
        Remove our local zip file.
        """

        if self.stage_config.get('delete_local_zip', True):
            try:
                if os.path.isfile(self.zip_path):
                    os.remove(self.zip_path)
            except Exception as e: # pragma: no cover
                sys.exit(-1)

    def remove_uploaded_zip(self):
        """
        Remove the local and S3 zip file after uploading and updating.
        """

        # Remove the uploaded zip from S3, because it is now registered..
        if self.stage_config.get('delete_s3_zip', True):
            self.zappa.remove_from_s3(self.zip_path, self.s3_bucket_name)

    def print_logs(self, logs):
        """
        Parse, filter and print logs to the console.

        """

        for log in logs:
            timestamp = log['timestamp']
            message = log['message']
            if "START RequestId" in message:
                continue
            if "REPORT RequestId" in message:
                continue
            if "END RequestId" in message:
                continue

            print("[" + str(timestamp) + "] " + message.strip())

    def execute_prebuild_script(self):
        """
        Parse and execute the prebuild_script from the zappa_settings.

        """

        # Parse the string
        prebuild_module_s, prebuild_function_s = self.prebuild_script.rsplit('.', 1)

        # The module
        prebuild_module = imp.load_source(prebuild_module_s, prebuild_module_s + '.py')

        # The function
        prebuild_function = getattr(prebuild_module, prebuild_function_s)

        # Execute it
        prebuild_function()


    def collision_warning(self, item):
        """
        Given a string, print a warning if this could
        collide with a Zappa core package module.

        Use for app functions and events.
        """

        namespace_collisions = [
            "zappa.", "wsgi.", "middleware.", "handler.", "util.", "letsencrypt.", "cli."
        ]
        for namespace_collision in namespace_collisions:
            if namespace_collision in item:
                click.echo(click.style("Warning!", fg="yellow", bold=True) + " You may have a namespace collision with " + click.style(item, bold=True) + "! You may want to rename that file.")



####################################################################
# Main
####################################################################

def shamelessly_promote():
    """
    Shamelessly promote our little community.
    """

    click.echo("Need " + click.style("help", fg='green', bold=True) + "? Found a " + click.style("bug", fg='green', bold=True) + "? Let us " + click.style("know", fg='green', bold=True) + "! :D")
    click.echo("File bug reports on " + click.style("GitHub", bold=True) + " here: " + click.style("https://github.com/Miserlou/Zappa", fg='cyan', bold=True))
    click.echo("And join our " + click.style("Slack", bold=True) + " channel here: " + click.style("https://slack.zappa.io", fg='cyan', bold=True))
    click.echo("Love!,")
    click.echo(" ~ Team " + click.style("Zappa", bold=True) + "!")

def handle(): # pragma: no cover
    """
    Main program execution handler.
    """

    try:
        cli = ZappaCLI()
        sys.exit(cli.handle())
    except SystemExit as e: # pragma: no cover
        if cli.zip_path:
            cli.remove_uploaded_zip()
            cli.remove_local_zip()

        sys.exit(e.code)

    except KeyboardInterrupt: # pragma: no cover
        if cli.zip_path: # Remove the Zip from S3 upon failure.
            cli.remove_uploaded_zip()
            cli.remove_local_zip()
        sys.exit(130)
    except Exception as e:
        if cli.zip_path: # Remove the Zip from S3 upon failure.
            cli.remove_uploaded_zip()
            cli.remove_local_zip()

        click.echo("Oh no! An " + click.style("error occurred", fg='red', bold=True) + "! :(")
        click.echo("\n==============\n")
        import traceback
        traceback.print_exc()
        click.echo("\n==============\n")
        shamelessly_promote()

        sys.exit(-1)

if __name__ == '__main__': # pragma: no cover
    handle()
