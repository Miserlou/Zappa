#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Zappa CLI

Deploy arbitrary Python programs as serverless Zappa applications.

"""

from __future__ import unicode_literals
from __future__ import division
from past.builtins import basestring
from builtins import input, bytes

import argcomplete
import argparse
import base64
import pkgutil
import botocore
import click
import collections
import hjson as json
import inspect
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
import toml
import yaml
import zipfile

from click.exceptions import ClickException
from dateutil import parser
from datetime import datetime, timedelta

from .core import Zappa, logger, API_GATEWAY_REGIONS
from .utilities import (check_new_version_available, detect_django_settings,
                  detect_flask_apps, parse_s3_url, human_size,
                  validate_name, InvalidAwsLambdaName,
                  get_runtime_from_python_version, string_to_timestamp)


CUSTOM_SETTINGS = [
    'assume_policy',
    'attach_policy',
    'aws_region',
    'delete_local_zip',
    'delete_s3_zip',
    'exclude',
    'extra_permissions',
    'include',
    'role_name',
    'touch',
]

BOTO3_CONFIG_DOCS_URL = 'https://boto3.readthedocs.io/en/latest/guide/quickstart.html#configuration'

##
# Main Input Processing
##

class ZappaCLI(object):
    """
    ZappaCLI object is responsible for loading the settings,
    handling the input arguments and executing the calls to the core library.

    """

    # CLI
    vargs = None
    command = None
    stage_env = None

    # Zappa settings
    zappa = None
    zappa_settings = None
    load_credentials = True
    disable_progress = False

    # Specific settings
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
    handler_path = None
    vpc_config = None
    memory_size = None
    use_apigateway = None
    lambda_handler = None
    django_settings = None
    manage_roles = True
    exception_handler = None
    environment_variables = None
    authorizer = None
    aws_kms_key_arn = ''
    context_header_mappings = None

    stage_name_env_pattern = re.compile('^[a-zA-Z0-9_]+$')

    def __init__(self):
        self._stage_config_overrides = {}  # change using self.override_stage_config_setting(key, val)

    @property
    def stage_config(self):
        """
        A shortcut property for settings of a stage.
        """

        def get_stage_setting(stage, extended_stages=None):
            if extended_stages is None:
                extended_stages = []

            if stage in extended_stages:
                raise RuntimeError(stage + " has already been extended to these settings. "
                                           "There is a circular extends within the settings file.")
            extended_stages.append(stage)

            try:
                stage_settings = dict(self.zappa_settings[stage].copy())
            except KeyError:
                raise ClickException("Cannot extend settings for undefined stage '" + stage + "'.")

            extends_stage = self.zappa_settings[stage].get('extends', None)
            if not extends_stage:
                return stage_settings
            extended_settings = get_stage_setting(stage=extends_stage, extended_stages=extended_stages)
            extended_settings.update(stage_settings)
            return extended_settings

        settings = get_stage_setting(stage=self.api_stage)

        # Backwards compatible for delete_zip setting that was more explicitly named delete_local_zip
        if u'delete_zip' in settings:
            settings[u'delete_local_zip'] = settings.get(u'delete_zip')

        settings.update(self.stage_config_overrides)

        return settings

    @property
    def stage_config_overrides(self):
        """
        Returns zappa_settings we forcefully override for the current stage
        set by `self.override_stage_config_setting(key, value)`
        """
        return getattr(self, '_stage_config_overrides', {}).get(self.api_stage, {})

    def override_stage_config_setting(self, key, val):
        """
        Forcefully override a setting set by zappa_settings (for the current stage only)
        :param key: settings key
        :param val: value
        """
        self._stage_config_overrides = getattr(self, '_stage_config_overrides', {})
        self._stage_config_overrides.setdefault(self.api_stage, {})[key] = val

    def handle(self, argv=None):
        """
        Main function.

        Parses command, load settings and dispatches accordingly.

        """

        desc = ('Zappa - Deploy Python applications to AWS Lambda'
                ' and API Gateway.\n')
        parser = argparse.ArgumentParser(description=desc)
        parser.add_argument(
            '-v', '--version', action='version',
            version=pkg_resources.get_distribution("zappa").version,
            help='Print the zappa version'
        )


        env_parser = argparse.ArgumentParser(add_help=False)
        me_group = env_parser.add_mutually_exclusive_group()
        all_help = ('Execute this command for all of our defined '
                    'Zappa stages.')
        me_group.add_argument('--all', action='store_true', help=all_help)
        me_group.add_argument('stage_env', nargs='?')

        group = env_parser.add_argument_group()
        group.add_argument(
            '-a', '--app_function', help='The WSGI application function.'
        )
        group.add_argument(
            '-s', '--settings_file', help='The path to a Zappa settings file.'
        )
        group.add_argument(
            '-q', '--quiet', action='store_true', help='Silence all output.'
        )
        # https://github.com/Miserlou/Zappa/issues/407
        # Moved when 'template' command added.
        # Fuck Terraform.
        group.add_argument(
            '-j', '--json', action='store_true', help='Make the output of this command be machine readable.'
        )
        # https://github.com/Miserlou/Zappa/issues/891
        group.add_argument(
            '--disable_progress', action='store_true', help='Disable progress bars.'
        )

        ##
        # Certify
        ##
        subparsers = parser.add_subparsers(title='subcommands', dest='command')
        cert_parser = subparsers.add_parser(
            'certify', parents=[env_parser],
            help='Create and install SSL certificate'
        )
        cert_parser.add_argument(
            '--no-cleanup', action='store_true',
            help=("Don't remove certificate files from /tmp during certify."
                  " Dangerous.")
        )
        cert_parser.add_argument(
            '--manual', action='store_true',
            help=("Gets new Let's Encrypt certificates, but prints them to console."
                "Does not update API Gateway domains.")
        )
        cert_parser.add_argument(
            '-y', '--yes', action='store_true', help='Auto confirm yes.'
        )

        ##
        # Deploy
        ##
        deploy_parser = subparsers.add_parser(
            'deploy', parents=[env_parser], help='Deploy application.'
        )

        ##
        # Init
        ##
        init_parser = subparsers.add_parser('init', help='Initialize Zappa app.')

        ##
        # Package
        ##
        package_parser = subparsers.add_parser(
            'package', parents=[env_parser], help='Build the application zip package locally.'
        )
        package_parser.add_argument(
            '-o', '--output', help='Name of file to output the package to.'
        )

        ##
        # Template
        ##
        template_parser = subparsers.add_parser(
            'template', parents=[env_parser], help='Create a CloudFormation template for this API Gateway.'
        )
        template_parser.add_argument(
            '-l', '--lambda-arn', required=True, help='ARN of the Lambda function to template to.'
        )
        template_parser.add_argument(
            '-r', '--role-arn', required=True, help='ARN of the Role to template with.'
        )
        template_parser.add_argument(
            '-o', '--output', help='Name of file to output the template to.'
        )

        ##
        # Invocation
        ##
        invoke_parser = subparsers.add_parser(
            'invoke', parents=[env_parser],
            help='Invoke remote function.'
        )
        invoke_parser.add_argument(
            '--raw', action='store_true',
            help=('When invoking remotely, invoke this python as a string,'
                  ' not as a modular path.')
        )
        invoke_parser.add_argument(
            '--no-color', action='store_true',
            help=("Don't color the output")
        )
        invoke_parser.add_argument('command_rest')

        ##
        # Manage
        ##
        manage_parser = subparsers.add_parser(
            'manage',
            help='Invoke remote Django manage.py commands.'
        )
        rest_help = ("Command in the form of <env> <command>. <env> is not "
                     "required if --all is specified")
        manage_parser.add_argument('--all', action='store_true', help=all_help)
        manage_parser.add_argument('command_rest', nargs='+', help=rest_help)
        manage_parser.add_argument(
            '--no-color', action='store_true',
            help=("Don't color the output")
        )

        ##
        # Rollback
        ##
        def positive_int(s):
            """ Ensure an arg is positive """
            i = int(s)
            if i < 0:
                msg = "This argument must be positive (got {})".format(s)
                raise argparse.ArgumentTypeError(msg)
            return i

        rollback_parser = subparsers.add_parser(
            'rollback', parents=[env_parser],
            help='Rollback deployed code to a previous version.'
        )
        rollback_parser.add_argument(
            '-n', '--num-rollback', type=positive_int, default=1,
            help='The number of versions to rollback.'
        )

        ##
        # Scheduling
        ##
        subparsers.add_parser(
            'schedule', parents=[env_parser],
            help='Schedule functions to occur at regular intervals.'
        )

        ##
        # Status
        ##
        status_parser = subparsers.add_parser(
            'status', parents=[env_parser],
            help='Show deployment status and event schedules.'
        )

        ##
        # Log Tailing
        ##
        tail_parser = subparsers.add_parser(
            'tail', parents=[env_parser], help='Tail deployment logs.'
        )
        tail_parser.add_argument(
            '--no-color', action='store_true',
            help="Don't color log tail output."
        )
        tail_parser.add_argument(
            '--http', action='store_true',
            help='Only show HTTP requests in tail output.'
        )
        tail_parser.add_argument(
            '--non-http', action='store_true',
            help='Only show non-HTTP requests in tail output.'
        )
        tail_parser.add_argument(
            '--since', type=str, default="100000s",
            help="Only show lines since a certain timeframe."
        )
        tail_parser.add_argument(
            '--filter', type=str, default="",
            help="Apply a filter pattern to the logs."
        )

        ##
        # Undeploy
        ##
        undeploy_parser = subparsers.add_parser(
            'undeploy', parents=[env_parser], help='Undeploy application.'
        )
        undeploy_parser.add_argument(
            '--remove-logs', action='store_true',
            help=('Removes log groups of api gateway and lambda task'
                  ' during the undeployment.'),
        )
        undeploy_parser.add_argument(
            '-y', '--yes', action='store_true', help='Auto confirm yes.'
        )

        ##
        # Unschedule
        ##
        subparsers.add_parser('unschedule', parents=[env_parser],
                              help='Unschedule functions.')

        ##
        # Updating
        ##
        subparsers.add_parser(
            'update', parents=[env_parser], help='Update deployed application.'
        )

        ##
        # Debug
        ##
        subparsers.add_parser(
            'shell', parents=[env_parser], help='A debug shell with a loaded Zappa object.'
        )

        argcomplete.autocomplete(parser)
        args = parser.parse_args(argv)
        self.vargs = vars(args)

        # Parse the input
        # NOTE(rmoe): Special case for manage command
        # The manage command can't have both stage_env and command_rest
        # arguments. Since they are both positional arguments argparse can't
        # differentiate the two. This causes problems when used with --all.
        # (e.g. "manage --all showmigrations admin" argparse thinks --all has
        # been specified AND that stage_env='showmigrations')
        # By having command_rest collect everything but --all we can split it
        # apart here instead of relying on argparse.
        if args.command == 'manage' and not self.vargs.get('all'):
            self.stage_env = self.vargs['command_rest'].pop(0)
        else:
            self.stage_env = self.vargs.get('stage_env')

        if args.command == 'package':
            self.load_credentials = False

        self.command = args.command

        self.disable_progress = self.vargs.get('disable_progress')
        if self.vargs.get('quiet'):
            self.silence()

        # We don't have any settings yet, so make those first!
        # (Settings-based interactions will fail
        # before a project has been initialized.)
        if self.command == 'init':
            self.init()
            return

        # Make sure there isn't a new version available
        if not self.vargs.get('json'):
            self.check_for_update()

        # Load and Validate Settings File
        self.load_settings_file(self.vargs.get('settings_file'))

        # Should we execute this for all stages, or just one?
        all_stages = self.vargs.get('all')
        stages = []

        if all_stages: # All stages!
            stages = self.zappa_settings.keys()
        else: # Just one env.
            if not self.stage_env:
                # If there's only one stage defined in the settings,
                # use that as the default.
                if len(self.zappa_settings.keys()) == 1:
                    stages.append(list(self.zappa_settings.keys())[0])
                else:
                    parser.error("Please supply an stage to interact with.")
            else:
                stages.append(self.stage_env)

        for stage in stages:
            try:
                self.dispatch_command(self.command, stage)
            except ClickException as e:
                # Discussion on exit codes: https://github.com/Miserlou/Zappa/issues/407
                e.show()
                sys.exit(e.exit_code)

    def dispatch_command(self, command, stage):
        """
        Given a command to execute and stage,
        execute that command.
        """

        self.api_stage = stage

        if command not in ['status', 'manage']:
            if not self.vargs['json']:
                click.echo("Calling " + click.style(command, fg="green", bold=True) + " for stage " +
                           click.style(self.api_stage, bold=True) + ".." )

        # Explicity define the app function.
        # Related: https://github.com/Miserlou/Zappa/issues/832
        if self.vargs.get('app_function', None):
            self.app_function = self.vargs['app_function']

        # Load our settings, based on api_stage.
        try:
            self.load_settings(self.vargs.get('settings_file'))
        except ValueError as e:
            print("Error: {}".format(e.message))
            sys.exit(-1)
        self.callback('settings')

        # Hand it off
        if command == 'deploy': # pragma: no cover
            self.deploy()
        if command == 'package': # pragma: no cover
            self.package(self.vargs['output'])
        if command == 'template': # pragma: no cover
            self.template(      self.vargs['lambda_arn'],
                                self.vargs['role_arn'],
                                output=self.vargs['output'],
                                json=self.vargs['json']
                            )
        elif command == 'update': # pragma: no cover
            self.update()
        elif command == 'rollback': # pragma: no cover
            self.rollback(self.vargs['num_rollback'])
        elif command == 'invoke': # pragma: no cover

            if not self.vargs.get('command_rest'):
                print("Please enter the function to invoke.")
                return

            self.invoke(
                self.vargs['command_rest'],
                raw_python=self.vargs['raw'],
                no_color=self.vargs['no_color'],
            )
        elif command == 'manage': # pragma: no cover

            if not self.vargs.get('command_rest'):
                print("Please enter the management command to invoke.")
                return

            if not self.django_settings:
                print("This command is for Django projects only!")
                print("If this is a Django project, please define django_settings in your zappa_settings.")
                return

            command_tail = self.vargs.get('command_rest')
            if len(command_tail) > 1:
                command = " ".join(command_tail) # ex: zappa manage dev "shell --version"
            else:
                command = command_tail[0] # ex: zappa manage dev showmigrations admin

            self.invoke(
                command,
                command="manage",
                no_color=self.vargs['no_color'],
            )

        elif command == 'tail': # pragma: no cover
            self.tail(
                colorize=(not self.vargs['no_color']),
                http=self.vargs['http'],
                non_http=self.vargs['non_http'],
                since=self.vargs['since'],
                filter_pattern=self.vargs['filter'],
            )
        elif command == 'undeploy': # pragma: no cover
            self.undeploy(
                no_confirm=self.vargs['yes'],
                remove_logs=self.vargs['remove_logs']
            )
        elif command == 'schedule': # pragma: no cover
            self.schedule()
        elif command == 'unschedule': # pragma: no cover
            self.unschedule()
        elif command == 'status': # pragma: no cover
            self.status(return_json=self.vargs['json'])
        elif command == 'certify': # pragma: no cover
            self.certify(
                no_cleanup=self.vargs['no_cleanup'],
                no_confirm=self.vargs['yes'],
                manual=self.vargs['manual']
            )
        elif command == 'shell': # pragma: no cover
            self.shell()

    ##
    # The Commands
    ##

    def package(self, output=None):
        """
        Only build the package
        """
        # Make sure we're in a venv.
        self.check_venv()

        # force not to delete the local zip
        self.override_stage_config_setting('delete_local_zip', False)
        # Execute the prebuild script
        if self.prebuild_script:
            self.execute_prebuild_script()
        # Create the Lambda Zip
        self.create_package(output)
        self.callback('zip')
        size = human_size(os.path.getsize(self.zip_path))
        click.echo(click.style("Package created", fg="green", bold=True) + ": " + click.style(self.zip_path, bold=True) + " (" + size + ")")

    def template(self, lambda_arn, role_arn, output=None, json=False):
        """
        Only build the template file.
        """

        if not lambda_arn:
            raise ClickException("Lambda ARN is required to template.")

        if not role_arn:
            raise ClickException("Role ARN is required to template.")

        self.zappa.credentials_arn = role_arn

        # Create the template!
        template = self.zappa.create_stack_template(
                                            lambda_arn=lambda_arn,
                                            lambda_name=self.lambda_name,
                                            api_key_required=self.api_key_required,
                                            iam_authorization=self.iam_authorization,
                                            authorizer=self.authorizer,
                                            cors_options=self.cors,
                                            description=self.apigateway_description
                                        )

        if not output:
            template_file = self.lambda_name + '-template-' + str(int(time.time())) + '.json'
        else:
            template_file = output
        with open(template_file, 'wb') as out:
            out.write(bytes(template.to_json(indent=None, separators=(',',':')), "utf-8"))

        if not json:
            click.echo(click.style("Template created", fg="green", bold=True) + ": " + click.style(template_file, bold=True))
        else:
            with open(template_file, 'r') as out:
                print(out.read())

    def deploy(self):
        """
        Package your project, upload it to S3, register the Lambda function
        and create the API Gateway routes.

        """

        # Make sure we're in a venv.
        self.check_venv()

        # Execute the prebuild script
        if self.prebuild_script:
            self.execute_prebuild_script()

        # Make sure this isn't already deployed.
        deployed_versions = self.zappa.get_lambda_function_versions(self.lambda_name)
        if len(deployed_versions) > 0:
            raise ClickException("This application is " + click.style("already deployed", fg="red") +
                                 " - did you mean to call " + click.style("update", bold=True) + "?")

        # Make sure the necessary IAM execution roles are available
        if self.manage_roles:
            try:
                self.zappa.create_iam_roles()
            except botocore.client.ClientError:
                raise ClickException(
                    click.style("Failed", fg="red") + " to " + click.style("manage IAM roles", bold=True) + "!\n" +
                    "You may " + click.style("lack the necessary AWS permissions", bold=True) +
                    " to automatically manage a Zappa execution role.\n" +
                    "To fix this, see here: " +
                    click.style("https://github.com/Miserlou/Zappa#using-custom-aws-iam-roles-and-policies", bold=True)
                    + '\n')

        # Create the Lambda Zip
        self.create_package()
        self.callback('zip')

        # Upload it to S3
        success = self.zappa.upload_to_s3(
                self.zip_path, self.s3_bucket_name, disable_progress=self.disable_progress)
        if not success: # pragma: no cover
            raise ClickException("Unable to upload to S3. Quitting.")

        # If using a slim handler, upload it to S3 and tell lambda to use this slim handler zip
        if self.stage_config.get('slim_handler', False):
            # https://github.com/Miserlou/Zappa/issues/510
            success = self.zappa.upload_to_s3(self.handler_path, self.s3_bucket_name, disable_progress=self.disable_progress)
            if not success:  # pragma: no cover
                raise ClickException("Unable to upload handler to S3. Quitting.")

            # Copy the project zip to the current project zip
            current_project_name = '{0!s}_current_project.zip'.format(self.project_name)
            success = self.zappa.copy_on_s3(src_file_name=self.zip_path, dst_file_name=current_project_name,
                                            bucket_name=self.s3_bucket_name)
            if not success:  # pragma: no cover
                raise ClickException("Unable to copy the zip to be the current project. Quitting.")

            handler_file = self.handler_path
        else:
            handler_file = self.zip_path


        # Fixes https://github.com/Miserlou/Zappa/issues/613
        try:
            self.lambda_arn = self.zappa.get_lambda_function(
                function_name=self.lambda_name)
        except botocore.client.ClientError:
            # Register the Lambda function with that zip as the source
            # You'll also need to define the path to your lambda_handler code.
            self.lambda_arn = self.zappa.create_lambda_function(
                bucket=self.s3_bucket_name,
                s3_key=handler_file,
                function_name=self.lambda_name,
                handler=self.lambda_handler,
                description=self.lambda_description,
                vpc_config=self.vpc_config,
                dead_letter_config=self.dead_letter_config,
                timeout=self.timeout_seconds,
                memory_size=self.memory_size,
                runtime=self.runtime,
                aws_environment_variables=self.aws_environment_variables,
                aws_kms_key_arn=self.aws_kms_key_arn
            )

        # Schedule events for this deployment
        self.schedule()

        endpoint_url = ''
        deployment_string = click.style("Deployment complete", fg="green", bold=True) + "!"
        if self.use_apigateway:

            # Create and configure the API Gateway
            template = self.zappa.create_stack_template(
                                                        lambda_arn=self.lambda_arn,
                                                        lambda_name=self.lambda_name,
                                                        api_key_required=self.api_key_required,
                                                        iam_authorization=self.iam_authorization,
                                                        authorizer=self.authorizer,
                                                        cors_options=self.cors,
                                                        description=self.apigateway_description
                                                    )

            self.zappa.update_stack(
                                    self.lambda_name,
                                    self.s3_bucket_name,
                                    wait=True,
                                    disable_progress=self.disable_progress
                                )

            api_id = self.zappa.get_api_id(self.lambda_name)

            # Add binary support
            if self.binary_support:
                self.zappa.add_binary_support(api_id=api_id, cors=self.cors)

            # Deploy the API!
            endpoint_url = self.deploy_api_gateway(api_id)
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

        # Remove the project zip from S3.
        self.remove_uploaded_zip()

        self.callback('post')

        click.echo(deployment_string)

    def update(self):
        """
        Repackage and update the function code.
        """

        # Make sure we're in a venv.
        self.check_venv()

        # Execute the prebuild script
        if self.prebuild_script:
            self.execute_prebuild_script()

        # Temporary version check
        try:
            updated_time = 1472581018
            function_response = self.zappa.lambda_client.get_function(FunctionName=self.lambda_name)
            conf = function_response['Configuration']
            last_updated = parser.parse(conf['LastModified'])
            last_updated_unix = time.mktime(last_updated.timetuple())
        except botocore.exceptions.BotoCoreError as e:
            click.echo(click.style(type(e).__name__, fg="red") + ": " + e.args[0])
            sys.exit(-1)
        except Exception as e:
            click.echo(click.style("Warning!", fg="red") + " Couldn't get function " + self.lambda_name +
                       " in " + self.zappa.aws_region + " - have you deployed yet?")
            sys.exit(-1)

        if last_updated_unix <= updated_time:
            click.echo(click.style("Warning!", fg="red") +
                       " You may have upgraded Zappa since deploying this application. You will need to " +
                       click.style("redeploy", bold=True) + " for this deployment to work properly!")

        # Make sure the necessary IAM execution roles are available
        if self.manage_roles:
            try:
                self.zappa.create_iam_roles()
            except botocore.client.ClientError:
                click.echo(click.style("Failed", fg="red") + " to " + click.style("manage IAM roles", bold=True) + "!")
                click.echo("You may " + click.style("lack the necessary AWS permissions", bold=True) +
                           " to automatically manage a Zappa execution role.")
                click.echo("To fix this, see here: " +
                           click.style("https://github.com/Miserlou/Zappa#using-custom-aws-iam-roles-and-policies",
                                       bold=True))
                sys.exit(-1)

        # Create the Lambda Zip,
        self.create_package()
        self.callback('zip')

        # Upload it to S3
        success = self.zappa.upload_to_s3(self.zip_path, self.s3_bucket_name, disable_progress=self.disable_progress)
        if not success:  # pragma: no cover
            raise ClickException("Unable to upload project to S3. Quitting.")

        # If using a slim handler, upload it to S3 and tell lambda to use this slim handler zip
        if self.stage_config.get('slim_handler', False):
            # https://github.com/Miserlou/Zappa/issues/510
            success = self.zappa.upload_to_s3(self.handler_path, self.s3_bucket_name, disable_progress=self.disable_progress)
            if not success:  # pragma: no cover
                raise ClickException("Unable to upload handler to S3. Quitting.")

            # Copy the project zip to the current project zip
            current_project_name = '{0!s}_current_project.zip'.format(self.project_name)
            success = self.zappa.copy_on_s3(src_file_name=self.zip_path, dst_file_name=current_project_name,
                                            bucket_name=self.s3_bucket_name)
            if not success:  # pragma: no cover
                raise ClickException("Unable to copy the zip to be the current project. Quitting.")

            handler_file = self.handler_path
        else:
            handler_file = self.zip_path

        # Register the Lambda function with that zip as the source
        # You'll also need to define the path to your lambda_handler code.
        self.lambda_arn = self.zappa.update_lambda_function(
                                        self.s3_bucket_name,
                                        handler_file,
                                        self.lambda_name
                                    )

        # Remove the uploaded zip from S3, because it is now registered..
        self.remove_uploaded_zip()

        # Update the configuration, in case there are changes.
        self.lambda_arn = self.zappa.update_lambda_configuration(
                                                        lambda_arn=self.lambda_arn,
                                                        function_name=self.lambda_name,
                                                        handler=self.lambda_handler,
                                                        description=self.lambda_description,
                                                        vpc_config=self.vpc_config,
                                                        timeout=self.timeout_seconds,
                                                        memory_size=self.memory_size,
                                                        runtime=self.runtime,
                                                        aws_environment_variables=self.aws_environment_variables,
                                                        aws_kms_key_arn=self.aws_kms_key_arn
                                                    )

        # Finally, delete the local copy our zip package
        if self.stage_config.get('delete_local_zip', True):
            self.remove_local_zip()

        if self.use_apigateway:

            self.zappa.create_stack_template(
                                            lambda_arn=self.lambda_arn,
                                            lambda_name=self.lambda_name,
                                            api_key_required=self.api_key_required,
                                            iam_authorization=self.iam_authorization,
                                            authorizer=self.authorizer,
                                            cors_options=self.cors,
                                            description=self.apigateway_description
                                        )
            self.zappa.update_stack(
                                    self.lambda_name,
                                    self.s3_bucket_name,
                                    wait=True,
                                    update_only=True,
                                    disable_progress=self.disable_progress)

            api_id = self.zappa.get_api_id(self.lambda_name)

            # update binary support
            if self.binary_support:
                self.zappa.add_binary_support(api_id=api_id, cors=self.cors)
            else:
                self.zappa.remove_binary_support(api_id=api_id, cors=self.cors)

            endpoint_url = self.deploy_api_gateway(api_id)


            if self.stage_config.get('domain', None):
                endpoint_url = self.stage_config.get('domain')

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

    def tail(self, since, filter_pattern, limit=10000, keep_open=True, colorize=True, http=False, non_http=False):
        """
        Tail this function's logs.

        if keep_open, do so repeatedly, printing any new logs
        """

        try:
            since_stamp = string_to_timestamp(since)

            last_since = since_stamp
            while True:
                new_logs = self.zappa.fetch_logs(
                    self.lambda_name,
                    start_time=since_stamp,
                    limit=limit,
                    filter_pattern=filter_pattern,
                    )

                new_logs = [ e for e in new_logs if e['timestamp'] > last_since ]
                self.print_logs(new_logs, colorize, http, non_http)

                if not keep_open:
                    break
                if new_logs:
                    last_since = new_logs[-1]['timestamp']
                time.sleep(1)
        except KeyboardInterrupt: # pragma: no cover
            # Die gracefully
            try:
                sys.exit(0)
            except SystemExit:
                os._exit(130)

    def undeploy(self, no_confirm=False, remove_logs=False):
        """
        Tear down an exiting deployment.
        """

        if not no_confirm: # pragma: no cover
            confirm = input("Are you sure you want to undeploy? [y/n] ")
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

        if self.stage_config.get('keep_warm', True):
            if not events:
                events = []

            keep_warm_rate = self.stage_config.get('keep_warm_expression', "rate(4 minutes)")
            events.append({'name': 'zappa-keep-warm',
                           'function': 'handler.keep_warm_callback',
                           'expression': keep_warm_rate,
                           'description': 'Zappa Keep Warm - {}'.format(self.lambda_name)})

        if events:
            try:
                function_response = self.zappa.lambda_client.get_function(FunctionName=self.lambda_name)
            except botocore.exceptions.ClientError as e: # pragma: no cover
                click.echo(click.style("Function does not exist", fg="yellow") + ", please " +
                           click.style("deploy", bold=True) + "first. Ex:" +
                           click.style("zappa deploy {}.".format(self.api_stage), bold=True))
                sys.exit(-1)

            print("Scheduling..")
            self.zappa.schedule_events(
                lambda_arn=function_response['Configuration']['FunctionArn'],
                lambda_name=self.lambda_name,
                events=events
            )

        # Add async tasks SNS
        if self.stage_config.get('async_source', None) == 'sns' \
           and self.stage_config.get('async_resources', True):
            self.lambda_arn = self.zappa.get_lambda_function(
                function_name=self.lambda_name)
            topic_arn = self.zappa.create_async_sns_topic(
                lambda_name=self.lambda_name,
                lambda_arn=self.lambda_arn
            )
            click.echo('SNS Topic created: %s' % topic_arn)

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
            raise ClickException("Function does not exist, you should deploy first. Ex: zappa deploy {}. "
                  "Proceeding to unschedule CloudWatch based events.".format(self.api_stage))

        print("Unscheduling..")
        self.zappa.unschedule_events(
            lambda_name=self.lambda_name,
            lambda_arn=function_arn,
            events=events,
            )

        # Remove async task SNS
        if self.stage_config.get('async_source', None) == 'sns' \
           and self.stage_config.get('async_resources', True):
            removed_arns = self.zappa.remove_async_sns_topic(self.lambda_name)
            click.echo('SNS Topic removed: %s' % ', '.join(removed_arns))

    def invoke(self, function_name, raw_python=False, command=None, no_color=False):
        """
        Invoke a remote function.
        """

        # There are three likely scenarios for 'command' here:
        #   command, which is a modular function path
        #   raw_command, which is a string of python to execute directly
        #   manage, which is a Django-specific management command invocation
        key = command if command is not None else 'command'
        if raw_python:
            command = {'raw_command': function_name}
        else:
            command = {key: function_name}

        # Can't use hjson
        import json as json

        response = self.zappa.invoke_lambda_function(
            self.lambda_name,
            json.dumps(command),
            invocation_type='RequestResponse',
        )

        if 'LogResult' in response:
            if no_color:
                print(base64.b64decode(response['LogResult']))
            else:
                decoded = base64.b64decode(response['LogResult']).decode()
                formated = self.format_invoke_command(decoded)
                colorized = self.colorize_invoke_command(formated)
                print(colorized)
        else:
            print(response)

    def format_invoke_command(self, string):
        """
        Formats correctly the string ouput from the invoke() method,
        replacing line breaks and tabs when necessary.
        """

        string = string.replace('\\n', '\n')

        formated_response = ''
        for line in string.splitlines():
            if line.startswith('REPORT'):
                line = line.replace('\t', '\n')
            if line.startswith('[DEBUG]'):
                line = line.replace('\t', ' ')
            formated_response += line + '\n'
        formated_response = formated_response.replace('\n\n', '\n')

        return formated_response

    def colorize_invoke_command(self, string):
        """
        Apply various heuristics to return a colorized version the invoke
        comman string. If these fail, simply return the string in plaintext.

        Inspired by colorize_log_entry().
        """

        final_string = string

        try:

            # Line headers
            try:
                for token in ['START', 'END', 'REPORT', '[DEBUG]']:
                    if token in final_string:
                        format_string = '{}' if token == '[DEBUG]' else '[{}]'
                        final_string = final_string.replace(token, click.style(
                            format_string.format(token),
                            bold=True,
                            fg='cyan'
                        ))
            except Exception: # pragma: no cover
                pass

            # Green bold Tokens
            try:
                for token in [
                    'Zappa Event:',
                    'RequestId:',
                    'Version:',
                    'Duration:',
                    'Billed',
                    'Memory Size:',
                    'Max Memory Used:'
                ]:
                    if token in final_string:
                        final_string = final_string.replace(token, click.style(
                            token,
                            bold=True,
                            fg='green'
                        ))
            except Exception: # pragma: no cover
                pass

            # UUIDs
            for token in final_string.replace('\t', ' ').split(' '):
                try:
                    if token.count('-') is 4 and token.replace('-', '').isalnum():
                        final_string = final_string.replace(
                            token,
                            click.style(token, fg='magenta')
                        )
                except Exception: # pragma: no cover
                    pass

            return final_string
        except Exception:
            return string

    def status(self, return_json=False):
        """
        Describe the status of the current deployment.
        """

        def tabular_print(title, value):
            """
            Convience function for priting formatted table items.
            """
            click.echo('%-*s%s' % (32, click.style("\t" + title, fg='green') + ':', str(value)))
            return

        # Lambda Env Details
        lambda_versions = self.zappa.get_lambda_function_versions(self.lambda_name)

        if not lambda_versions:
            raise ClickException(click.style("No Lambda %s detected in %s - have you deployed yet?" %
                                             (self.lambda_name, self.zappa.aws_region), fg='red'))

        status_dict = collections.OrderedDict()
        status_dict["Lambda Versions"] = len(lambda_versions)
        function_response = self.zappa.lambda_client.get_function(FunctionName=self.lambda_name)
        conf = function_response['Configuration']
        self.lambda_arn = conf['FunctionArn']
        status_dict["Lambda Name"] = self.lambda_name
        status_dict["Lambda ARN"] = self.lambda_arn
        status_dict["Lambda Role ARN"] = conf['Role']
        status_dict["Lambda Handler"] = conf['Handler']
        status_dict["Lambda Code Size"] = conf['CodeSize']
        status_dict["Lambda Version"] = conf['Version']
        status_dict["Lambda Last Modified"] = conf['LastModified']
        status_dict["Lambda Memory Size"] = conf['MemorySize']
        status_dict["Lambda Timeout"] = conf['Timeout']
        status_dict["Lambda Runtime"] = conf['Runtime']
        if 'VpcConfig' in conf.keys():
            status_dict["Lambda VPC ID"] = conf.get('VpcConfig', {}).get('VpcId', 'Not assigned')
        else:
            status_dict["Lambda VPC ID"] = None

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
        status_dict["Invocations (24h)"] = int(function_invocations)
        status_dict["Errors (24h)"] = int(function_errors)
        status_dict["Error Rate (24h)"] = error_rate

        # URLs
        if self.use_apigateway:
            api_url = self.zappa.get_api_url(
                self.lambda_name,
                self.api_stage)

            status_dict["API Gateway URL"] = api_url

            # Api Keys
            api_id = self.zappa.get_api_id(self.lambda_name)
            for api_key in self.zappa.get_api_keys(api_id, self.api_stage):
                status_dict["API Gateway x-api-key"] = api_key

            # There literally isn't a better way to do this.
            # AWS provides no way to tie a APIGW domain name to its Lambda funciton.
            domain_url = self.stage_config.get('domain', None)
            if domain_url:
                status_dict["Domain URL"] = 'https://' + domain_url
            else:
                status_dict["Domain URL"] = "None Supplied"

        # Scheduled Events
        event_rules = self.zappa.get_event_rules_for_lambda(lambda_arn=self.lambda_arn)
        status_dict["Num. Event Rules"] = len(event_rules)
        if len(event_rules) > 0:
            status_dict['Events'] = []
        for rule in event_rules:
            event_dict = {}
            rule_name = rule['Name']
            event_dict["Event Rule Name"] = rule_name
            event_dict["Event Rule Schedule"] = rule.get(u'ScheduleExpression', None)
            event_dict["Event Rule State"] = rule.get(u'State', None).title()
            event_dict["Event Rule ARN"] = rule.get(u'Arn', None)
            status_dict['Events'].append(event_dict)

        if return_json:
            # Putting the status in machine readable format
            # https://github.com/Miserlou/Zappa/issues/407
            print(json.dumpsJSON(status_dict))
        else:
            click.echo("Status for " + click.style(self.lambda_name, bold=True) + ": ")
            for k, v in status_dict.items():
                if k == 'Events':
                    # Events are a list of dicts
                    for event in v:
                        for item_k, item_v in event.items():
                            tabular_print(item_k, item_v)
                else:
                    tabular_print(k, v)

        # TODO: S3/SQS/etc. type events?

        return True

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

    def check_environment(self, environment):
        """
        Make sure the environment contains only strings

        (since putenv needs a string)
        """

        non_strings = []
        for (k,v) in environment.items():
            if not isinstance(v, basestring):
                non_strings.append(k)
        if non_strings:
            raise ValueError("The following environment variables are not strings: {}".format(", ".join(non_strings)))
        else:
            return True

    def init(self, settings_file="zappa_settings.json"):
        """
        Initialize a new Zappa project by creating a new zappa_settings.json in a guided process.

        This should probably be broken up into few separate componants once it's stable.
        Testing these inputs requires monkeypatching with mock, which isn't pretty.

        """

        # Make sure we're in a venv.
        self.check_venv()

        # Ensure that we don't already have a zappa_settings file.
        if os.path.isfile(settings_file):
            raise ClickException("This project already has a " + click.style("{0!s} file".format(settings_file), fg="red", bold=True) + "!")

        # Explain system.
        click.echo(click.style(u"""\n███████╗ █████╗ ██████╗ ██████╗  █████╗
╚══███╔╝██╔══██╗██╔══██╗██╔══██╗██╔══██╗
  ███╔╝ ███████║██████╔╝██████╔╝███████║
 ███╔╝  ██╔══██║██╔═══╝ ██╔═══╝ ██╔══██║
███████╗██║  ██║██║     ██║     ██║  ██║
╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝     ╚═╝  ╚═╝\n""", fg='green', bold=True))

        click.echo(click.style("Welcome to ", bold=True) + click.style("Zappa", fg='green', bold=True) + click.style("!\n", bold=True))
        click.echo(click.style("Zappa", bold=True) + " is a system for running server-less Python web applications"
                                                     " on AWS Lambda and AWS API Gateway.")
        click.echo("This `init` command will help you create and configure your new Zappa deployment.")
        click.echo("Let's get started!\n")

        # Create Env
        while True:
            click.echo("Your Zappa configuration can support multiple production stages, like '" +
                       click.style("dev", bold=True)  + "', '" + click.style("staging", bold=True)  + "', and '" +
                       click.style("production", bold=True)  + "'.")
            env = input("What do you want to call this environment (default 'dev'): ") or "dev"
            try:
                self.check_stage_name(env)
                break
            except ValueError:
                click.echo(click.style("Stage names must match a-zA-Z0-9_", fg="red"))

        # Detect AWS profiles and regions
        # If anyone knows a more straightforward way to easily detect and parse AWS profiles I'm happy to change this, feels like a hack
        session = botocore.session.Session()
        config  = session.full_config
        profiles = config.get("profiles", {})
        profile_names = list(profiles.keys())

        click.echo("\nAWS Lambda and API Gateway are only available in certain regions. "\
                   "Let's check to make sure you have a profile set up in one that will work.")

        if not profile_names:
            profile_name, profile = None, None
            click.echo("We couldn't find an AWS profile to use. Before using Zappa, you'll need to set one up. See here for more info: {}"
                       .format(click.style(BOTO3_CONFIG_DOCS_URL, fg="blue", underline=True)))
        elif len(profile_names) == 1:
            profile_name = profile_names[0]
            profile = profiles[profile_name]
            click.echo("Okay, using profile {}!".format(click.style(profile_name, bold=True)))
        else:
            if "default" in profile_names:
                default_profile = [p for p in profile_names if p == "default"][0]
            else:
                default_profile = profile_names[0]

            while True:
                profile_name = input("We found the following profiles: {}, and {}. "\
                                         "Which would you like us to use? (default '{}'): "
                                         .format(
                                             ', '.join(profile_names[:-1]),
                                             profile_names[-1],
                                             default_profile
                                         )) or default_profile
                if profile_name in profiles:
                    profile = profiles[profile_name]
                    break
                else:
                    click.echo("Please enter a valid name for your AWS profile.")

        profile_region = profile.get("region") if profile else None

        # Create Bucket
        click.echo("\nYour Zappa deployments will need to be uploaded to a " + click.style("private S3 bucket", bold=True)  + ".")
        click.echo("If you don't have a bucket yet, we'll create one for you too.")
        default_bucket = "zappa-" + ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(9))
        bucket = input("What do you want call your bucket? (default '%s'): " % default_bucket) or default_bucket

        # Detect Django/Flask
        try: # pragma: no cover
            import django
            has_django = True
        except ImportError as e:
            has_django = False

        try: # pragma: no cover
            import flask
            has_flask = True
        except ImportError as e:
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
                    django_settings = input("Where are your project's settings? (default '%s'): " % matches[0]) or matches[0]
                else:
                    click.echo("(This will likely be something like 'your_project.settings')")
                    django_settings = input("Where are your project's settings?: ")
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
                    app_function = input("Where is your app's function? (default '%s'): " % matches[0]) or matches[0]
                else:
                    app_function = input("Where is your app's function?: ")
            app_function = app_function.replace("'", "")
            app_function = app_function.replace('"', "")

        # TODO: Create VPC?
        # Memory size? Time limit?
        # Domain? LE keys? Region?
        # 'Advanced Settings' mode?

        # Globalize
        click.echo("\nYou can optionally deploy to " + click.style("all available regions", bold=True)  + " in order to provide fast global service.")
        click.echo("If you are using Zappa for the first time, you probably don't want to do this!")
        global_deployment = False
        while True:
            global_type = input("Would you like to deploy this application " + click.style("globally", bold=True)  + "? (default 'n') [y/n/(p)rimary]: ")
            if not global_type:
                break
            if global_type.lower() in ["y", "yes", "p", "primary"]:
                global_deployment = True
                break
            if global_type.lower() in ["n", "no"]:
                global_deployment = False
                break

        if global_deployment:
            regions = API_GATEWAY_REGIONS
            if global_type.lower() in ["p", "primary"]:
                envs = [{env + '_' + region.replace('-', '_'): { 'aws_region': region}} for region in regions if '-1' in region]
            else:
                envs = [{env + '_' + region.replace('-', '_'): { 'aws_region': region}} for region in regions]
        else:
            envs = [{env: {}}]

        zappa_settings = {}
        for each_env in envs:

            # Honestly, this could be cleaner.
            env_name = list(each_env.keys())[0]
            env_dict = each_env[env_name]

            env_bucket = bucket
            if global_deployment:
            # `zappa init` doesn't generate compatible s3_bucket names #828
                env_bucket = (bucket + '-' + env_name).replace('_', '-')

            env_zappa_settings = {
                env_name: {
                    's3_bucket': env_bucket,
                }
            }

            if profile_name:
                env_zappa_settings[env_name]['profile_name'] = profile_name

            if 'aws_region' in env_dict:
                env_zappa_settings[env_name]['aws_region'] = env_dict.get('aws_region')
            elif profile_region:
                env_zappa_settings[env_name]['aws_region'] = profile_region

            zappa_settings.update(env_zappa_settings)

            if has_django:
                zappa_settings[env_name]['django_settings'] = django_settings
            else:
                zappa_settings[env_name]['app_function'] = app_function

        import json as json # hjson is fine for loading, not fine for writing.
        zappa_settings_json = json.dumps(zappa_settings, sort_keys=True, indent=4)

        click.echo("\nOkay, here's your " + click.style("zappa_settings.json", bold=True) + ":\n")
        click.echo(click.style(zappa_settings_json, fg="yellow", bold=False))

        confirm = input("\nDoes this look " + click.style("okay", bold=True, fg="green")  + "? (default 'y') [y/n]: ") or 'yes'
        if confirm[0] not in ['y', 'Y', 'yes', 'YES']:
            click.echo("" + click.style("Sorry", bold=True, fg='red') + " to hear that! Please init again.")
            return

        # Write
        with open("zappa_settings.json", "w") as zappa_settings_file:
            zappa_settings_file.write(zappa_settings_json)

        if global_deployment:
            click.echo("\n" + click.style("Done", bold=True) + "! You can also " + click.style("deploy all", bold=True)  + " by executing:\n")
            click.echo(click.style("\t$ zappa deploy --all", bold=True))

            click.echo("\nAfter that, you can " + click.style("update", bold=True) + " your application code with:\n")
            click.echo(click.style("\t$ zappa update --all", bold=True))
        else:
            click.echo("\n" + click.style("Done", bold=True) + "! Now you can " + click.style("deploy", bold=True)  + " your Zappa application by executing:\n")
            click.echo(click.style("\t$ zappa deploy %s" % env, bold=True))

            click.echo("\nAfter that, you can " + click.style("update", bold=True) + " your application code with:\n")
            click.echo(click.style("\t$ zappa update %s" % env, bold=True))

        click.echo("\nTo learn more, check out our project page on " + click.style("GitHub", bold=True) +
                   " here: " + click.style("https://github.com/Miserlou/Zappa", fg="cyan", bold=True))
        click.echo("and stop by our " + click.style("Slack", bold=True) + " channel here: " +
                   click.style("https://slack.zappa.io", fg="cyan", bold=True))
        click.echo("\nEnjoy!,")
        click.echo(" ~ Team " + click.style("Zappa", bold=True) + "!")

        return

    def certify(self, no_cleanup=False, no_confirm=True, manual=False):
        """
        Register or update a domain certificate for this env.
        """

        if not self.domain:
            raise ClickException("Can't certify a domain without " + click.style("domain", fg="red", bold=True) + " configured!")

        if not no_confirm: # pragma: no cover
            confirm = input("Are you sure you want to certify? [y/n] ")
            if confirm != 'y':
                return

        # Give warning on --no-cleanup
        if no_cleanup:
            clean_up = False
            click.echo(click.style("Warning!", fg="red", bold=True) + " You are calling certify with " +
                       click.style("--no-cleanup", bold=True) +
                       ". Your certificate files will remain in the system temporary directory after this command executes!")
        else:
            clean_up = True

        # Make sure this isn't already deployed.
        deployed_versions = self.zappa.get_lambda_function_versions(self.lambda_name)
        if len(deployed_versions) == 0:
            raise ClickException("This application " + click.style("isn't deployed yet", fg="red") +
                                 " - did you mean to call " + click.style("deploy", bold=True) + "?")


        account_key_location = self.stage_config.get('lets_encrypt_key', None)
        cert_location = self.stage_config.get('certificate', None)
        cert_key_location = self.stage_config.get('certificate_key', None)
        cert_chain_location = self.stage_config.get('certificate_chain', None)
        cert_arn = self.stage_config.get('certificate_arn', None)

        # These are sensitive
        certificate_body = None
        certificate_private_key = None
        certificate_chain = None

        # Prepare for custom Let's Encrypt
        if not cert_location and not cert_arn:
            if not account_key_location:
                raise ClickException("Can't certify a domain without " + click.style("lets_encrypt_key", fg="red", bold=True) +
                                     " or " + click.style("certificate", fg="red", bold=True)+
                                     " or " + click.style("certificate_arn", fg="red", bold=True) + " configured!")

            # Get install account_key to /tmp/account_key.pem
            if account_key_location.startswith('s3://'):
                bucket, key_name = parse_s3_url(account_key_location)
                self.zappa.s3_client.download_file(bucket, key_name, '/tmp/account.key')
            else:
                from shutil import copyfile
                copyfile(account_key_location, '/tmp/account.key')

        # Prepare for Custom SSL
        elif not account_key_location and not cert_arn:
            if not cert_location or not cert_key_location or not cert_chain_location:
                raise ClickException("Can't certify a domain without " +
                                     click.style("certificate, certificate_key and certificate_chain", fg="red", bold=True) + " configured!")

            # Read the supplied certificates.
            with open(cert_location) as f:
                certificate_body = f.read()

            with open(cert_key_location) as f:
                certificate_private_key = f.read()

            with open(cert_chain_location) as f:
                certificate_chain = f.read()


        click.echo("Certifying domain " + click.style(self.domain, fg="green", bold=True) + "..")

        # Get cert and update domain.

        # Let's Encrypt
        if not cert_location and not cert_arn:
            from .letsencrypt import get_cert_and_update_domain, cleanup
            cert_success = get_cert_and_update_domain(
                    self.zappa,
                    self.lambda_name,
                    self.api_stage,
                    self.domain,
                    clean_up,
                    manual
                )

            # Deliberately undocumented feature (for now, at least.)
            # We are giving the user the ability to shoot themselves in the foot.
            # _This is probably not a good idea._
            # However, I am sick and tired of hitting the Let's Encrypt cert
            # limit while testing.
            if clean_up:
                cleanup()

        # Custom SSL / ACM
        else:
            if not self.zappa.get_domain_name(self.domain):
                dns_name = self.zappa.create_domain_name(
                    domain_name=self.domain,
                    certificate_name=self.domain + "-Zappa-Cert",
                    certificate_body=certificate_body,
                    certificate_private_key=certificate_private_key,
                    certificate_chain=certificate_chain,
                    certificate_arn=cert_arn,
                    lambda_name=self.lambda_name,
                    stage=self.api_stage,
                )
                if self.stage_config.get('route53_enabled', True):
                    self.zappa.update_route53_records(self.domain, dns_name)
                print("Created a new domain name with supplied certificate. Please note that it can take up to 40 minutes for this domain to be "
                      "created and propagated through AWS, but it requires no further work on your part.")
            else:
                self.zappa.update_domain_name(
                    domain_name=self.domain,
                    certificate_name=self.domain + "-Zappa-Cert",
                    certificate_body=certificate_body,
                    certificate_private_key=certificate_private_key,
                    certificate_chain=certificate_chain,
                    certificate_arn=cert_arn,
                    lambda_name=self.lambda_name,
                    stage=self.api_stage,
                    route53=self.stage_config.get('route53_enabled', True)
                )

            cert_success = True

        if cert_success:
            click.echo("Certificate " + click.style("updated", fg="green", bold=True) + "!")
        else:
            click.echo(click.style("Failed", fg="red", bold=True) + " to generate or install certificate! :(")
            click.echo("\n==============\n")
            shamelessly_promote()

    ##
    # Shell
    ##
    def shell(self):
        """
        Spawn a debug shell.
        """
        click.echo(click.style("NOTICE!", fg="yellow", bold=True) + " This is a " + click.style("local", fg="green", bold=True) + " shell, inside a " + click.style("Zappa", bold=True) + " object!")
        self.zappa.shell()
        return

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
            (mod_path, cb_func_name) = callback.rsplit('.', 1)

            try:  # Prefer callback in working directory
                if mod_path.count('.') >= 1:  # Callback function is nested in a folder
                    (mod_folder_path, mod_name) = mod_path.rsplit('.', 1)
                    mod_folder_path_fragments = mod_folder_path.split('.')
                    working_dir = os.path.join(os.getcwd(), *mod_folder_path_fragments)
                else:
                    mod_name = mod_path
                    working_dir = os.getcwd()

                working_dir_importer = pkgutil.get_importer(working_dir)
                module_ = working_dir_importer.find_module(mod_name).load_module(mod_name)

            except (ImportError, AttributeError):

                try: # Callback func might be in virtualenv
                    module_ = importlib.import_module(mod_path)
                except ImportError: # pragma: no cover
                    raise ClickException(click.style("Failed ", fg="red") + 'to ' + click.style(
                        "import {position} callback ".format(position=position),
                        bold=True) + 'module: "{mod_path}"'.format(mod_path=click.style(mod_path, bold=True)))

            if not hasattr(module_, cb_func_name): # pragma: no cover
                raise ClickException(click.style("Failed ", fg="red") + 'to ' + click.style(
                    "find {position} callback ".format(position=position), bold=True) + 'function: "{cb_func_name}" '.format(
                    cb_func_name=click.style(cb_func_name, bold=True)) + 'in module "{mod_path}"'.format(mod_path=mod_path))


            cb_func = getattr(module_, cb_func_name)
            cb_func(self) # Call the function passing self

    def check_for_update(self):
        """
        Print a warning if there's a new Zappa version available.
        """
        try:
            version = pkg_resources.require("zappa")[0].version
            updateable = check_new_version_available(version)
            if updateable:
                click.echo(click.style("Important!", fg="yellow", bold=True) +
                           " A new version of " + click.style("Zappa", bold=True) + " is available!")
                click.echo("Upgrade with: " + click.style("pip install zappa --upgrade", bold=True))
                click.echo("Visit the project page on GitHub to see the latest changes: " +
                           click.style("https://github.com/Miserlou/Zappa", bold=True))
        except Exception as e: # pragma: no cover
            print(e)
            return

    def load_settings(self, settings_file=None, session=None):
        """
        Load the local zappa_settings file.

        An existing boto session can be supplied, though this is likely for testing purposes.

        Returns the loaded Zappa object.
        """

        # Ensure we're passed a valid settings file.
        if not settings_file:
            settings_file = self.get_json_or_yaml_settings()
        if not os.path.isfile(settings_file):
            raise ClickException("Please configure your zappa_settings file.")

        # Load up file
        self.load_settings_file(settings_file)

        # Make sure that the stages are valid names:
        for stage_name in self.zappa_settings.keys():
            try:
                self.check_stage_name(stage_name)
            except ValueError:
                raise ValueError("API stage names must match a-zA-Z0-9_ ; '{0!s}' does not.".format(stage_name))

        # Make sure that this stage is our settings
        if self.api_stage not in self.zappa_settings.keys():
            raise ClickException("Please define stage '{0!s}' in your Zappa settings.".format(self.api_stage))

        # We need a working title for this project. Use one if supplied, else cwd dirname.
        if 'project_name' in self.stage_config: # pragma: no cover
            # If the name is invalid, this will throw an exception with message up stack
            self.project_name = validate_name(self.stage_config['project_name'])
        else:
            self.project_name = slugify.slugify(os.getcwd().split(os.sep)[-1])[:15]

        # The name of the actual AWS Lambda function, ex, 'helloworld-dev'
        # Assume that we already have have validated the name beforehand.
        # Related:  https://github.com/Miserlou/Zappa/pull/664
        #           https://github.com/Miserlou/Zappa/issues/678
        #           And various others from Slack.
        self.lambda_name = slugify.slugify(self.project_name + '-' + self.api_stage)

        # Load stage-specific settings
        self.s3_bucket_name = self.stage_config.get('s3_bucket', "zappa-" + ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(9)))
        self.vpc_config = self.stage_config.get('vpc_config', {})
        self.memory_size = self.stage_config.get('memory_size', 512)
        self.app_function = self.stage_config.get('app_function', None)
        self.exception_handler = self.stage_config.get('exception_handler', None)
        self.aws_region = self.stage_config.get('aws_region', None)
        self.debug = self.stage_config.get('debug', True)
        self.prebuild_script = self.stage_config.get('prebuild_script', None)
        self.profile_name = self.stage_config.get('profile_name', None)
        self.log_level = self.stage_config.get('log_level', "DEBUG")
        self.domain = self.stage_config.get('domain', None)
        self.timeout_seconds = self.stage_config.get('timeout_seconds', 30)
        dead_letter_arn = self.stage_config.get('dead_letter_arn', '')
        self.dead_letter_config = {'TargetArn': dead_letter_arn} if dead_letter_arn else {}

        # Provide legacy support for `use_apigateway`, now `apigateway_enabled`.
        # https://github.com/Miserlou/Zappa/issues/490
        # https://github.com/Miserlou/Zappa/issues/493
        self.use_apigateway = self.stage_config.get('use_apigateway', True)
        if self.use_apigateway:
            self.use_apigateway = self.stage_config.get('apigateway_enabled', True)
        self.apigateway_description = self.stage_config.get('apigateway_description', None)

        self.lambda_handler = self.stage_config.get('lambda_handler', 'handler.lambda_handler')
        # DEPRECATED. https://github.com/Miserlou/Zappa/issues/456
        self.remote_env_bucket = self.stage_config.get('remote_env_bucket', None)
        self.remote_env_file = self.stage_config.get('remote_env_file', None)
        self.remote_env = self.stage_config.get('remote_env', None)
        self.settings_file = self.stage_config.get('settings_file', None)
        self.django_settings = self.stage_config.get('django_settings', None)
        self.manage_roles = self.stage_config.get('manage_roles', True)
        self.binary_support = self.stage_config.get('binary_support', True)
        self.api_key_required = self.stage_config.get('api_key_required', False)
        self.api_key = self.stage_config.get('api_key')
        self.iam_authorization = self.stage_config.get('iam_authorization', False)
        self.cors = self.stage_config.get("cors", False)
        self.lambda_description = self.stage_config.get('lambda_description', "Zappa Deployment")
        self.environment_variables = self.stage_config.get('environment_variables', {})
        self.aws_environment_variables = self.stage_config.get('aws_environment_variables', {})
        self.check_environment(self.environment_variables)
        self.authorizer = self.stage_config.get('authorizer', {})
        self.runtime = self.stage_config.get('runtime', get_runtime_from_python_version())
        self.aws_kms_key_arn = self.stage_config.get('aws_kms_key_arn', '')
        self.context_header_mappings = self.stage_config.get('context_header_mappings', {})

        desired_role_name = self.lambda_name + "-ZappaLambdaExecutionRole"
        self.zappa = Zappa( boto_session=session,
                            profile_name=self.profile_name,
                            aws_region=self.aws_region,
                            load_credentials=self.load_credentials,
                            desired_role_name=desired_role_name,
                            runtime=self.runtime
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
                click.echo(click.style("Warning!", fg="red", bold=True) +
                           " Your app_function is pointing to a " + click.style("file and not a function", bold=True) +
                           "! It should probably be something like 'my_file.app', not 'my_file.py'!")

        return self.zappa

    def get_json_or_yaml_settings(self, settings_name="zappa_settings"):
        """
        Return zappa_settings path as JSON or YAML (or TOML), as appropriate.
        """
        zs_json = settings_name + ".json"
        zs_yaml = settings_name + ".yml"
        zs_toml = settings_name + ".toml"

        # Must have at least one
        if not os.path.isfile(zs_json) \
            and not os.path.isfile(zs_yaml) \
            and not os.path.isfile(zs_toml):
            raise ClickException("Please configure a zappa_settings file or call `zappa init`.")

        # Prefer JSON
        if os.path.isfile(zs_json):
            settings_file = zs_json
        elif os.path.isfile(zs_toml):
            settings_file = zs_toml
        else:
            settings_file = zs_yaml

        return settings_file

    def load_settings_file(self, settings_file=None):
        """
        Load our settings file.
        """

        if not settings_file:
            settings_file = self.get_json_or_yaml_settings()
        if not os.path.isfile(settings_file):
            raise ClickException("Please configure your zappa_settings file or call `zappa init`.")

        if '.yml' in settings_file:
            with open(settings_file) as yaml_file:
                try:
                    self.zappa_settings = yaml.load(yaml_file)
                except ValueError: # pragma: no cover
                    raise ValueError("Unable to load the Zappa settings YAML. It may be malformed.")
        elif '.toml' in settings_file:
            with open(settings_file) as toml_file:
                try:
                    self.zappa_settings = toml.load(toml_file)
                except ValueError: # pragma: no cover
                    raise ValueError("Unable to load the Zappa settings TOML. It may be malformed.")
        else:
            with open(settings_file) as json_file:
                try:
                    self.zappa_settings = json.load(json_file)
                except ValueError: # pragma: no cover
                    raise ValueError("Unable to load the Zappa settings JSON. It may be malformed.")

    def create_package(self, output=None):
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

        # Create the zip file(s)
        if self.stage_config.get('slim_handler', False):
            # Create two zips. One with the application and the other with just the handler.
            # https://github.com/Miserlou/Zappa/issues/510
            self.zip_path = self.zappa.create_lambda_zip(
                prefix=self.lambda_name,
                use_precompiled_packages=self.stage_config.get('use_precompiled_packages', True),
                exclude=self.stage_config.get('exclude', []),
                disable_progress=self.disable_progress
            )

            # Make sure the normal venv is not included in the handler's zip
            exclude = self.stage_config.get('exclude', [])
            cur_venv = self.zappa.get_current_venv()
            exclude.append(cur_venv.split('/')[-1])
            self.handler_path = self.zappa.create_lambda_zip(
                prefix='handler_{0!s}'.format(self.lambda_name),
                venv=self.zappa.create_handler_venv(),
                handler_file=handler_file,
                slim_handler=True,
                exclude=exclude,
                output=output,
                disable_progress=self.disable_progress
            )
        else:

            # Custom excludes for different versions.
            # Related: https://github.com/kennethreitz/requests/issues/3985
            if sys.version_info[0] < 3:
                # Exclude packages already builtin to the python lambda environment
                # Related: https://github.com/Miserlou/Zappa/issues/556
                exclude = self.stage_config.get(
                        'exclude', [
                                        "boto3",
                                        "dateutil",
                                        "botocore",
                                        "s3transfer",
                                        "six.py",
                                        "jmespath",
                                        "concurrent"
                                    ])
            else:
                # This could be python3.6 optimized.
                exclude = self.stage_config.get(
                        'exclude', [
                                        "boto3",
                                        "dateutil",
                                        "botocore",
                                        "s3transfer",
                                        "concurrent"
                                    ])

            # Create a single zip that has the handler and application
            self.zip_path = self.zappa.create_lambda_zip(
                prefix=self.lambda_name,
                handler_file=handler_file,
                use_precompiled_packages=self.stage_config.get('use_precompiled_packages', True),
                exclude=exclude,
                output=output,
                disable_progress=self.disable_progress
            )

            # Warn if this is too large for Lambda.
            file_stats = os.stat(self.zip_path)
            if file_stats.st_size > 52428800:  # pragma: no cover
                print('\n\nWarning: Application zip package is likely to be too large for AWS Lambda. '
                      'Try setting "slim_handler" to true in your Zappa settings file.\n\n')

        # Throw custom setings into the zip that handles requests
        if self.stage_config.get('slim_handler', False):
            handler_zip = self.handler_path
        else:
            handler_zip = self.zip_path

        with zipfile.ZipFile(handler_zip, 'a') as lambda_zip:

            settings_s = "# Generated by Zappa\n"

            if self.app_function:
                if '.' not in self.app_function: # pragma: no cover
                    raise ClickException("Your " + click.style("app_function", fg='red', bold=True) + " value is not a modular path." +
                        " It needs to be in the format `" + click.style("your_module.your_app_object", bold=True) + "`.")
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

            if self.binary_support:
                settings_s = settings_s + "BINARY_SUPPORT=True\n"
            else:
                settings_s = settings_s + "BINARY_SUPPORT=False\n"

            head_map_dict = {}
            head_map_dict.update(dict(self.context_header_mappings))
            settings_s = settings_s + "CONTEXT_HEADER_MAPPINGS={0}\n".format(
                head_map_dict
            )

            # If we're on a domain, we don't need to define the /<<env>> in
            # the WSGI PATH
            if self.domain:
                settings_s = settings_s + "DOMAIN='{0!s}'\n".format((self.domain))
            else:
                settings_s = settings_s + "DOMAIN=None\n"

            # Pass through remote config bucket and path
            if self.remote_env:
                settings_s = settings_s + "REMOTE_ENV='{0!s}'\n".format(
                    self.remote_env
                )
            # DEPRECATED. use remove_env instead
            elif self.remote_env_bucket and self.remote_env_file:
                settings_s = settings_s + "REMOTE_ENV='s3://{0!s}/{1!s}'\n".format(
                    self.remote_env_bucket, self.remote_env_file
                )

            # Local envs
            env_dict = {}
            if self.aws_region:
                env_dict['AWS_REGION'] = self.aws_region
            env_dict.update(dict(self.environment_variables))

            # Environment variable keys must be ascii
            # https://github.com/Miserlou/Zappa/issues/604
            # https://github.com/Miserlou/Zappa/issues/998
            try:
                env_dict = dict((k.encode('ascii').decode('ascii'), v) for (k, v) in env_dict.items())
            except Exception:
                raise ValueError("Environment variable keys must be ascii.")

            settings_s = settings_s + "ENVIRONMENT_VARIABLES={0}\n".format(
                    env_dict
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

            # If slim handler, path to project zip
            if self.stage_config.get('slim_handler', False):
                settings_s += "ZIP_PATH='s3://{0!s}/{1!s}_current_project.zip'\n".format(self.s3_bucket_name, self.project_name)

                # since includes are for slim handler add the setting here by joining arbitrary list from zappa_settings file
                # and tell the handler we are the slim_handler
                # https://github.com/Miserlou/Zappa/issues/776
                settings_s += "SLIM_HANDLER=True\n"

                include = self.stage_config.get('include', [])
                if len(include) >= 1:
                    settings_s += "INCLUDE=" + str(include) + '\n'

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
                django_py = ''.join(os.path.join(base, 'ext', 'django_zappa.py'))
                lambda_zip.write(django_py, 'django_zappa_app.py')

            # Lambda requires a specific chmod
            temp_settings = tempfile.NamedTemporaryFile(delete=False)
            os.chmod(temp_settings.name, 0o644)
            temp_settings.write(bytes(settings_s, "utf-8"))
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
                if self.handler_path and os.path.isfile(self.handler_path):
                    os.remove(self.handler_path)
            except Exception as e: # pragma: no cover
                sys.exit(-1)

    def remove_uploaded_zip(self):
        """
        Remove the local and S3 zip file after uploading and updating.
        """

        # Remove the uploaded zip from S3, because it is now registered..
        if self.stage_config.get('delete_s3_zip', True):
            self.zappa.remove_from_s3(self.zip_path, self.s3_bucket_name)
            if self.stage_config.get('slim_handler', False):
                # Need to keep the project zip as the slim handler uses it.
                self.zappa.remove_from_s3(self.handler_path, self.s3_bucket_name)

    def on_exit(self):
        """
        Cleanup after the command finishes.
        Always called: SystemExit, KeyboardInterrupt and any other Exception that occurs.
        """
        if self.zip_path:
            # Only try to remove uploaded zip if we're running a command that has loaded credentials
            if self.load_credentials:
                self.remove_uploaded_zip()

            self.remove_local_zip()

    def print_logs(self, logs, colorize=True, http=False, non_http=False):
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

            if not colorize:
                if http:
                    if self.is_http_log_entry(message.strip()):
                        print("[" + str(timestamp) + "] " + message.strip())
                elif non_http:
                    if not self.is_http_log_entry(message.strip()):
                        print("[" + str(timestamp) + "] " + message.strip())
                else:
                    print("[" + str(timestamp) + "] " + message.strip())
            else:
                if http:
                    if self.is_http_log_entry(message.strip()):
                        click.echo(click.style("[", fg='cyan') + click.style(str(timestamp), bold=True) + click.style("]", fg='cyan') + self.colorize_log_entry(message.strip()))
                elif non_http:
                    if not self.is_http_log_entry(message.strip()):
                        click.echo(click.style("[", fg='cyan') + click.style(str(timestamp), bold=True) + click.style("]", fg='cyan') + self.colorize_log_entry(message.strip()))
                else:
                    click.echo(click.style("[", fg='cyan') + click.style(str(timestamp), bold=True) + click.style("]", fg='cyan') + self.colorize_log_entry(message.strip()))

    def is_http_log_entry(self, string):
        """
        Determines if a log entry is an HTTP-formatted log string or not.
        """
        # Debug event filter
        if 'Zappa Event' in string:
            return False

        # IP address filter
        for token in string.replace('\t', ' ').split(' '):
            try:
                if (token.count('.') is 3 and token.replace('.', '').isnumeric()):
                    return True
            except Exception: # pragma: no cover
                pass

        return False

    def colorize_log_entry(self, string):
        """
        Apply various heuristics to return a colorized version of a string.
        If these fail, simply return the string in plaintext.
        """

        final_string = string
        try:

            # First, do stuff in square brackets
            inside_squares = re.findall(r'\[([^]]*)\]', string)
            for token in inside_squares:
                if token in ['CRITICAL', 'ERROR', 'WARNING', 'DEBUG', 'INFO', 'NOTSET']:
                    final_string = final_string.replace('[' + token + ']', click.style("[", fg='cyan') + click.style(token, fg='cyan', bold=True) + click.style("]", fg='cyan'))
                else:
                    final_string = final_string.replace('[' + token + ']', click.style("[", fg='cyan') + click.style(token, bold=True) + click.style("]", fg='cyan'))

            # Then do quoted strings
            quotes = re.findall(r'"[^"]*"', string)
            for token in quotes:
                final_string = final_string.replace(token, click.style(token, fg="yellow"))

            # And UUIDs
            for token in final_string.replace('\t', ' ').split(' '):
                try:
                    if token.count('-') is 4 and token.replace('-', '').isalnum():
                        final_string = final_string.replace(token, click.style(token, fg="magenta"))
                except Exception: # pragma: no cover
                    pass

                # And IP addresses
                try:
                    if token.count('.') is 3 and token.replace('.', '').isnumeric():
                        final_string = final_string.replace(token, click.style(token, fg="red"))
                except Exception: # pragma: no cover
                    pass

                # And status codes
                try:
                    if token in ['200']:
                        final_string = final_string.replace(token, click.style(token, fg="green"))
                    if token in ['400', '401', '403', '404', '405', '500']:
                        final_string = final_string.replace(token, click.style(token, fg="red"))
                except Exception: # pragma: no cover
                    pass

            # And Zappa Events
            try:
                if "Zappa Event:" in final_string:
                    final_string = final_string.replace("Zappa Event:", click.style("Zappa Event:", bold=True, fg="green"))
            except Exception: # pragma: no cover
                pass

            # And dates
            for token in final_string.split('\t'):
                try:
                    is_date = parser.parse(token)
                    final_string = final_string.replace(token, click.style(token, fg="green"))
                except Exception: # pragma: no cover
                    pass

            final_string = final_string.replace('\t', ' ').replace('   ', ' ')
            if final_string[0] != ' ':
                final_string = ' ' + final_string
            return final_string
        except Exception as e: # pragma: no cover
            return string

    def execute_prebuild_script(self):
        """
        Parse and execute the prebuild_script from the zappa_settings.

        """

        (pb_mod_path, pb_func) = self.prebuild_script.rsplit('.', 1)

        try:  # Prefer prebuild script in working directory
            if pb_mod_path.count('.') >= 1:  # Prebuild script func is nested in a folder
                (mod_folder_path, mod_name) = pb_mod_path.rsplit('.', 1)
                mod_folder_path_fragments = mod_folder_path.split('.')
                working_dir = os.path.join(os.getcwd(), *mod_folder_path_fragments)
            else:
                mod_name = pb_mod_path
                working_dir = os.getcwd()

            working_dir_importer = pkgutil.get_importer(working_dir)
            module_ = working_dir_importer.find_module(mod_name).load_module(mod_name)

        except (ImportError, AttributeError):

            try:  # Prebuild func might be in virtualenv
                module_ = importlib.import_module(pb_mod_path)
            except ImportError:  # pragma: no cover
                raise ClickException(click.style("Failed ", fg="red") + 'to ' + click.style(
                    "import prebuild script ", bold=True) + 'module: "{pb_mod_path}"'.format(
                    pb_mod_path=click.style(pb_mod_path, bold=True)))

        if not hasattr(module_, pb_func):  # pragma: no cover
            raise ClickException(click.style("Failed ", fg="red") + 'to ' + click.style(
                "find prebuild script ", bold=True) + 'function: "{pb_func}" '.format(
                pb_func=click.style(pb_func, bold=True)) + 'in module "{pb_mod_path}"'.format(
                pb_mod_path=pb_mod_path))

        prebuild_function = getattr(module_, pb_func)
        prebuild_function()  # Call the function

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
                click.echo(click.style("Warning!", fg="red", bold=True) +
                           " You may have a namespace collision with " + click.style(item, bold=True) +
                           "! You may want to rename that file.")

    def deploy_api_gateway(self, api_id):
        cache_cluster_enabled = self.stage_config.get('cache_cluster_enabled', False)
        cache_cluster_size = str(self.stage_config.get('cache_cluster_size', .5))
        endpoint_url = self.zappa.deploy_api_gateway(
            api_id=api_id,
            stage_name=self.api_stage,
            cache_cluster_enabled=cache_cluster_enabled,
            cache_cluster_size=cache_cluster_size,
            cloudwatch_log_level=self.stage_config.get('cloudwatch_log_level', 'OFF'),
            cloudwatch_data_trace=self.stage_config.get('cloudwatch_data_trace', False),
            cloudwatch_metrics_enabled=self.stage_config.get('cloudwatch_metrics_enabled', False),
            cache_cluster_ttl=self.stage_config.get('cache_cluster_ttl', 300),
            cache_cluster_encrypted=self.stage_config.get('cache_cluster_encrypted', False)
        )
        return endpoint_url

    def check_venv(self):
        """ Ensure we're inside a virtualenv. """
        if self.zappa:
            venv = self.zappa.get_current_venv()
        else:
            # Just for `init`, when we don't have settings yet.
            venv = Zappa.get_current_venv()
        if not venv:
            raise ClickException(
                click.style("Zappa", bold=True) + " requires an " + click.style("active virtual environment", bold=True, fg="red") + "!\n" +
                "Learn more about virtual environments here: " + click.style("http://docs.python-guide.org/en/latest/dev/virtualenvs/", bold=False, fg="cyan"))

    def silence(self):
        """
        Route all stdout to null.
        """

        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')

####################################################################
# Main
####################################################################

def shamelessly_promote():
    """
    Shamelessly promote our little community.
    """

    click.echo("Need " + click.style("help", fg='green', bold=True) +
               "? Found a " + click.style("bug", fg='green', bold=True) +
               "? Let us " + click.style("know", fg='green', bold=True) + "! :D")
    click.echo("File bug reports on " + click.style("GitHub", bold=True) + " here: "
               + click.style("https://github.com/Miserlou/Zappa", fg='cyan', bold=True))
    click.echo("And join our " + click.style("Slack", bold=True) + " channel here: "
               + click.style("https://slack.zappa.io", fg='cyan', bold=True))
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
        cli.on_exit()
        sys.exit(e.code)

    except KeyboardInterrupt: # pragma: no cover
        cli.on_exit()
        sys.exit(130)
    except Exception as e:
        cli.on_exit()

        click.echo("Oh no! An " + click.style("error occurred", fg='red', bold=True) + "! :(")
        click.echo("\n==============\n")
        import traceback
        traceback.print_exc()
        click.echo("\n==============\n")
        shamelessly_promote()

        sys.exit(-1)

if __name__ == '__main__': # pragma: no cover
    handle()
