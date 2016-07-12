#! /usr/bin/env python
"""

Zappa CLI

Deploy arbitrary Python programs as serverless Zappa applications.

"""

from __future__ import unicode_literals

import argparse
import inspect
import imp
import hjson as json
import os
import requests
import slugify
import sys
import tempfile
import zipfile
import pkg_resources
import logging
import botocore

from zappa import Zappa, logger

CUSTOM_SETTINGS = [
    'aws_region',
    'delete_zip',
    'exclude',
    'http_methods',
    'integration_response_codes',
    'method_response_codes',
    'parameter_depth',
    'role_name',
    'touch',
]

CLI_COMMANDS = [
    'deploy',
    'invoke',
    'rollback',
    'schedule',
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

    api_stage = None
    app_function = None
    aws_region = None
    debug = None
    prebuild_script = None
    project_name = None
    profile_name = None
    lambda_arn = None
    lambda_name = None
    s3_bucket_name = None
    settings_file = None
    zip_path = None
    vpc_config = None
    memory_size = None
    use_apigateway = None
    lambda_handler = None

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

        if len(command_env) < 2: # pragma: no cover
            self.load_settings_file(vargs['settings_file'])

            # If there's only one environment defined in the settings,
            # use that as the default.
            if len(self.zappa_settings.keys()) is 1:
                self.api_stage = self.zappa_settings.keys()[0]
            else:
                parser.error("Please supply an environment to interact with.")
                return
        else:
            self.api_stage = command_env[1]

        # Load our settings
        self.load_settings(vargs['settings_file'])
        if vargs['app_function'] is not None:
            self.app_function = vargs['app_function']

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
            self.invoke()
        elif command == 'tail': # pragma: no cover
            self.tail()
        elif command == 'undeploy': # pragma: no cover
            self.undeploy(noconfirm=vargs['yes'])
        elif command == 'schedule': # pragma: no cover
            self.schedule()
        elif command == 'unschedule': # pragma: no cover
            self.unschedule()

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

        # Make sure the necessary IAM execution roles are available
        self.zappa.create_iam_roles()

        # Create the Lambda Zip
        self.create_package()

        # Upload it to S3
        success = self.zappa.upload_to_s3(
                self.zip_path, self.s3_bucket_name)
        if not success: # pragma: no cover
            print("Unable to upload to S3. Quitting.")
            return

        # Register the Lambda function with that zip as the source
        # You'll also need to define the path to your lambda_handler code.
        self.lambda_arn = self.zappa.create_lambda_function(bucket=self.s3_bucket_name,
                                                       s3_key=self.zip_path,
                                                       function_name=self.lambda_name,
                                                       handler=self.lambda_handler,
                                                       vpc_config=self.vpc_config,
                                                       timeout=self.timeout_seconds,
                                                       memory_size=self.memory_size)

        # Create a Keep Warm for this deployment
        if self.zappa_settings[self.api_stage].get('keep_warm', True):
            self.zappa.create_keep_warm(self.lambda_arn, self.lambda_name)

        endpoint_url = ''
        if self.use_apigateway:
            # Create and configure the API Gateway
            api_id = self.zappa.create_api_gateway_routes(
                self.lambda_arn, self.lambda_name)

            # Deploy the API!
            cache_cluster_enabled = self.zappa_settings[self.api_stage].get('cache_cluster_enabled', False)
            cache_cluster_size = str(self.zappa_settings[self.api_stage].get('cache_cluster_size', .5))
            endpoint_url = self.zappa.deploy_api_gateway(
                                        api_id=api_id,
                                        stage_name=self.api_stage,
                                        cache_cluster_enabled=cache_cluster_enabled,
                                        cache_cluster_size=cache_cluster_size
                                    )

            if self.zappa_settings[self.api_stage].get('touch', True):
                requests.get(endpoint_url)

        # Finally, delete the local copy our zip package
        if self.zappa_settings[self.api_stage].get('delete_zip', True):
            os.remove(self.zip_path)

        # Remove the uploaded zip from S3, because it is now registered..
        self.zappa.remove_from_s3(self.zip_path, self.s3_bucket_name)

        print("Deployed! {}".format(endpoint_url))


    def update(self):
        """
        Repackage and update the function code.
        """

        # Execute the prebuild script
        if self.prebuild_script:
            self.execute_prebuild_script()

        # Make sure the necessary IAM execution roles are available
        self.zappa.create_iam_roles()

        # Create the Lambda Zip,
        self.create_package()

        # Upload it to S3
        success = self.zappa.upload_to_s3(self.zip_path, self.s3_bucket_name)
        if not success: # pragma: no cover
            print("Unable to upload to S3. Quitting.")
            return

        # Register the Lambda function with that zip as the source
        # You'll also need to define the path to your lambda_handler code.
        self.lambda_arn = self.zappa.update_lambda_function(
            self.s3_bucket_name, self.zip_path, self.lambda_name)

        # Create a Keep Warm for this deployment
        if self.zappa_settings[self.api_stage].get('keep_warm', True):
            self.zappa.create_keep_warm(self.lambda_arn, self.lambda_name)

        # Remove the uploaded zip from S3, because it is now registered..
        self.zappa.remove_from_s3(self.zip_path, self.s3_bucket_name)

        # Finally, delete the local copy our zip package
        if self.zappa_settings[self.api_stage].get('delete_zip', True):
            os.remove(self.zip_path)

        print("Your updated Zappa deployment is live!")

        return

    def rollback(self, revision):
        """
        Rollsback the currently deploy lambda code to a previous revision.
        """

        print("Rolling back..")

        self.zappa.rollback_lambda_function_version(
            self.lambda_name, versions_back=revision)
        print("Done!")

        return

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
                sys.exit(130)
            except SystemExit:
                os._exit(130)

    def undeploy(self, noconfirm=False):
        """
        Tear down an exiting deployment.
        """

        if not noconfirm: # pragma: no cover
            confirm = raw_input("Are you sure you want to undeploy? [y/n] ")
            if confirm != 'y':
                return

        self.zappa.undeploy_api_gateway(self.lambda_name)
        if self.zappa_settings[self.api_stage].get('keep_warm', True):
            self.zappa.remove_keep_warm(self.lambda_name)
        self.zappa.delete_lambda_function(self.lambda_name)

        print("Done!")

        return

    def schedule(self):
        """
        Given a a list of functions and a schedule to execute them,
        setup up regular execution.

        """

        if self.zappa_settings[self.api_stage].get('events'):
            events = self.zappa_settings[self.api_stage]['events']

            if type(events) != list:
                print("Events must be supplied as a list.")
                return

            try:
                function_response = self.zappa.lambda_client.get_function(FunctionName=self.lambda_name)
            except botocore.exceptions.ClientError as e:
                print("Function does not exist, please deploy first. Ex: zappa deploy {}".format(self.api_stage))
                return

            print("Scheduling..")
            self.zappa.schedule_events(
                lambda_arn=function_response['Configuration']['FunctionArn'],
                lambda_name=function_response['Configuration']['FunctionName'],
                events=events)


    def unschedule(self):
        """
        Given a a list of scheduled functions,
        tear down their regular execution.

        """

        if self.zappa_settings[self.api_stage].get('events', None):
            events = self.zappa_settings[self.api_stage]['events']

            if type(events) != type([]):
                print("Events must be supplied as a list.")
                return

            print("Unscheduling..")
            self.zappa.unschedule_events(events)

        return

    def print_version(self):
        """
        Print the current zappa version.
        """
        version = pkg_resources.require("zappa")[0].version
        print(version)

    ##
    # Utility
    ##

    def load_settings(self, settings_file="zappa_settings.json", session=None):
        """
        Load the local zappa_settings.json file.

        An existing boto session can be supplied, though this is likely for testing purposes.

        Returns the loaded Zappa object.
        """

        # Ensure we're passed a valid settings file.
        if not os.path.isfile(settings_file):
            print("Please configure your zappa_settings file.")
            sys.exit(1) # pragma: no cover

        # Load up file
        self.load_settings_file(settings_file)

        # Make sure that this environment is our settings
        if self.api_stage not in self.zappa_settings.keys():
            print("Please define '{0!s}' in your Zappa settings.".format(self.api_stage))
            sys.exit(1) # pragma: no cover

        # We need a working title for this project. Use one if supplied, else cwd dirname.
        if 'project_name' in self.zappa_settings[self.api_stage]: # pragma: no cover
            self.project_name = self.zappa_settings[self.api_stage]['project_name']
        else:
            self.project_name = slugify.slugify(os.getcwd().split(os.sep)[-1])

        # The name of the actual AWS Lambda function, ex, 'helloworld-dev'
        # Django's slugify doesn't replace _, but this does.
        self.lambda_name = slugify.slugify(self.project_name + '-' + self.api_stage)

        # Load environment-specific settings
        self.s3_bucket_name = self.zappa_settings[self.api_stage]['s3_bucket']
        self.vpc_config = self.zappa_settings[
            self.api_stage].get('vpc_config', {})
        self.memory_size = self.zappa_settings[
            self.api_stage].get('memory_size', 512)
        self.app_function = self.zappa_settings[
            self.api_stage].get('app_function', None)
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
        self.lambda_handler = self.zappa_settings[
            self.api_stage].get('lambda_handler', 'handler.lambda_handler')
        self.remote_env_bucket = self.zappa_settings[
            self.api_stage].get('remote_env_bucket', None)
        self.remote_env_file = self.zappa_settings[
            self.api_stage].get('remote_env_file', None)

        self.zappa = Zappa(boto_session=session, profile_name=self.profile_name, aws_region=self.aws_region)

        for setting in CUSTOM_SETTINGS:
            if setting in self.zappa_settings[self.api_stage]:
                setattr(self.zappa, setting, self.zappa_settings[
                        self.api_stage][setting])

        return self.zappa

    def load_settings_file(self, settings_file="zappa_settings.json"):
        try:
            with open(settings_file) as json_file:
                self.zappa_settings = json.load(json_file)
        except Exception as e: # pragma: no cover
            print("Problem parsing settings file.")
            print(e)
            sys.exit(1) # pragma: no cover

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
                use_precompiled_packages=self.zappa_settings[self.api_stage].get('use_precompiled_packages', True),
                exclude=self.zappa_settings[self.api_stage].get('exclude', [])
            )

        if self.app_function:
            # Throw custom setings into the zip file
            with zipfile.ZipFile(self.zip_path, 'a') as lambda_zip:
                app_module, app_function = self.app_function.rsplit('.', 1)
                settings_s = "# Generated by Zappa\nAPP_MODULE='{0!s}'\nAPP_FUNCTION='{1!s}'\n".format(app_module, app_function)

                if self.debug:
                    settings_s = settings_s + "DEBUG='{0!s}'\n".format((self.debug)) # Cast to Bool in handler
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

                # We can be environment-aware
                settings_s = settings_s + "API_STAGE='{0!s}'\n".format((self.api_stage))

                # Lambda requires a specific chmod
                temp_settings = tempfile.NamedTemporaryFile(delete=False)
                os.chmod(temp_settings.name, 0644)
                temp_settings.write(settings_s)
                temp_settings.close()
                lambda_zip.write(temp_settings.name, 'zappa_settings.py')
                os.remove(temp_settings.name)
                # lambda_zip.close()


    def remove_local_zip(self):
        """
        Remove our local zip file.
        """

        if self.zappa_settings[self.api_stage].get('delete_zip', True):
            try:
                os.remove(self.zip_path)
            except Exception as e: # pragma: no cover
                pass

    def remove_uploaded_zip(self):
        """
        Remove the local and S3 zip file after uploading and updating.
        """

        # Remove the uploaded zip from S3, because it is now registered..
        self.zappa.remove_from_s3(self.zip_path, self.s3_bucket_name)

        # Finally, delete the local copy our zip package
        self.remove_local_zip()

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

####################################################################
# Main
####################################################################

def handle(): # pragma: no cover
    """
    Main program execution handler.
    """

    try:
        cli = ZappaCLI()
        sys.exit(cli.handle())
    except (KeyboardInterrupt, SystemExit): # pragma: no cover
        if cli.zip_path: # Remove the Zip from S3 upon failure.
            cli.remove_uploaded_zip()
        sys.exit(130)
    except Exception as e:
        if cli.zip_path: # Remove the Zip from S3 upon failure.
            cli.remove_uploaded_zip()
        print(e)
        sys.exit(1)

if __name__ == '__main__': # pragma: no cover
    handle()
