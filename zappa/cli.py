#! /usr/bin/env python
"""

Zappa CLI

Deploy arbitrary Python programs as serverless Zappa applications.

"""

from __future__ import unicode_literals

import argparse
import datetime
import inspect
import json
import os
import re
import requests
import sys
import tempfile
import unicodedata
import zipfile

from zappa import Zappa

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

##
# Main Input Processing
##

class ZappaCLI(object):

    # Zappa settings
    zappa = None
    zappa_settings = None

    api_stage = None
    app_function = None
    aws_region = None
    debug = None
    project_name = None
    lambda_name = None
    s3_bucket_name = None
    settings_file = None
    zip_path = None
    vpc_config = None
    memory_size = None

    def handle(self, argv=None):
        """
        Main function.

        Parses command, load settings and dispatches accordingly.

        """

        parser = argparse.ArgumentParser(description='Zappa - Deploy Python applications to AWS Lambda and API Gateway.\n')
        parser.add_argument('command_env', metavar='U', type=str, nargs='*',
                       help="Command to execute. Can be one of 'deploy', 'update', 'tail' and 'rollback'.")
        parser.add_argument('-n', '--num-rollback', type=int, default=0,
                            help='The number of versions to rollback.')
        parser.add_argument('-s', '--settings_file', type=str, default='zappa_settings.json',
                            help='The path to a zappa settings file.')
        parser.add_argument('-a', '--app_function', type=str, default=None,
                            help='The WSGI application function.')

        args = parser.parse_args(argv)
        vargs = vars(args)
        if not any(vargs.values()): # pragma: no cover
            parser.error("Please supply a command to execute. Can be one of 'deploy', 'update', 'tail', rollback', 'invoke'.'")
            return

        # Parse the input
        command_env = vargs['command_env']
        if len(command_env) < 2: # pragma: no cover
            parser.error("Please supply an environment to interact with.")
            return
        command = command_env[0]
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
        else:
            print("The command '%s' is not recognized." % command)
            return

    ##
    # The Commands
    ##

    def deploy(self):
        """
        Package your project, upload it to S3, register the Lambda function
        and create the API Gateway routes.

        """

        # Make sure the necessary IAM execution roles are available
        self.zappa.create_iam_roles()

        # Create the Lambda Zip
        self.create_package()

        # Upload it to S3
        try:
            zip_arn = self.zappa.upload_to_s3(
                self.zip_path, self.s3_bucket_name)
        except (KeyboardInterrupt, SystemExit): # pragma: no cover
            raise

        # Register the Lambda function with that zip as the source
        # You'll also need to define the path to your lambda_handler code.
        lambda_arn = self.zappa.create_lambda_function(bucket=self.s3_bucket_name,
                                                       s3_key=self.zip_path,
                                                       function_name=self.lambda_name,
                                                       handler='handler.lambda_handler',
                                                       vpc_config=self.vpc_config,
                                                       memory_size=self.memory_size)

        # Create and configure the API Gateway
        api_id = self.zappa.create_api_gateway_routes(
            lambda_arn, self.lambda_name)

        # Deploy the API!
        endpoint_url = self.zappa.deploy_api_gateway(api_id, self.api_stage)

        # Finally, delete the local copy our zip package
        if self.zappa_settings[self.api_stage].get('delete_zip', True):
            os.remove(self.zip_path)

        # Remove the uploaded zip from S3, because it is now registered..
        self.zappa.remove_from_s3(self.zip_path, self.s3_bucket_name)

        if self.zappa_settings[self.api_stage].get('touch', True):
            requests.get(endpoint_url)

        print("Your Zappa deployment is live!: " + endpoint_url)

        return

    def update(self):
        """
        Repackage and update the function code.
        """

        # Create the Lambda Zip,
        self.create_package()

        # Upload it to S3
        self.zappa.upload_to_s3(self.zip_path, self.s3_bucket_name)

        # Register the Lambda function with that zip as the source
        # You'll also need to define the path to your lambda_handler code.
        lambda_arn = self.zappa.update_lambda_function(
            self.s3_bucket_name, self.zip_path, self.lambda_name)

        # Remove the uploaded zip from S3, because it is now registered..
        self.zappa.remove_from_s3(self.zip_path, self.s3_bucket_name)

        # Finally, delete the local copy our zip package
        if self.zappa_settings[self.api_stage].get('delete_zip', True):
            os.remove(self.zip_path)

        print("Your updated Zappa deployment is live!")

        return

    def rollback(self, revision):

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
                sys.exit(0)
            except SystemExit:
                os._exit(0)


    ##
    # Utility
    ##

    def load_settings(self, settings_file="zappa_settings.json", session=None):
        """
        Load the local zappa_settings.json file. 

        Returns the loaded Zappa object.
        """

        # Ensure we're passesd a valid settings file.
        if not os.path.isfile(settings_file):
            print("Please configure your zappa_settings file.")
            quit() # pragma: no cover

        # Load up file
        try:
            with open(settings_file) as json_file:
                self.zappa_settings = json.load(json_file)
        except Exception as e: # pragma: no cover
            print("Problem parsing settings file.")
            print(e)
            quit() # pragma: no cover

        # Make sure that this environment is our settings
        if self.api_stage not in self.zappa_settings.keys():
            print("Please define '%s' in your Zappa settings." % self.api_stage)
            quit() # pragma: no cover

        # We need a working title for this project. Use one if supplied, else cwd dirname.
        if 'project_name' in self.zappa_settings[self.api_stage]: # pragma: no cover
            self.project_name = self.zappa_settings[self.api_stage]['project_name']
        else:
            self.project_name = self.slugify(os.getcwd().split(os.sep)[-1])

        # The name of the actual AWS Lambda function, ex, 'helloworld-dev'
        self.lambda_name = self.project_name + '-' + self.api_stage

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

        # Create an Zappa object..
        self.zappa = Zappa(session)
        self.zappa.aws_region = self.aws_region

        # Load your AWS credentials from ~/.aws/credentials
        self.zappa.load_credentials(session)

        # ..and configure it
        for setting in CUSTOM_SETTINGS:
            if self.zappa_settings[self.api_stage].has_key(setting):
                setattr(self.zappa, setting, self.zappa_settings[
                        self.api_stage][setting])        

        return self.zappa

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
                use_precompiled_packages=self.zappa_settings.get('use_precompiled_packages', True),
                exclude=self.zappa_settings.get('exclude', [])
            )

        # Throw our setings into it
        with zipfile.ZipFile(self.zip_path, 'a') as lambda_zip:
            app_module, app_function = self.app_function.rsplit('.', 1)
            settings_s = "# Generated by Zappa\nAPP_MODULE='%s'\nAPP_FUNCTION='%s'\n" % (app_module, app_function)
            
            if self.debug is not None:
                settings_s = settings_s + "DEBUG='%s'" % (self.debug) # Cast to Bool in handler

            # Lambda requires a specific chmod
            temp_settings = tempfile.NamedTemporaryFile(delete=False)
            os.chmod(temp_settings.name, 0644)
            temp_settings.write(settings_s)
            temp_settings.close()
            lambda_zip.write(temp_settings.name, 'zappa_settings.py')
            os.remove(temp_settings.name)

            lambda_zip.close()

        return

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

    def slugify(self, value):
        """
        
        Converts to lowercase, removes non-word characters (alphanumerics and
        underscores) and converts spaces to hyphens. Also strips leading and
        trailing whitespace.

        Stolen from Django.

        """
        value = unicodedata.normalize('NFKD', u'' + value).encode('ascii', 'ignore').decode('ascii')
        value = re.sub('[^\w\s-]', '', value).strip().lower()
        return re.sub('[-\s]+', '-', value)

    def print_logs(self, logs):

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

####################################################################
# Main
####################################################################

def handle(): # pragma: no cover
    try:
        cli = ZappaCLI()
        sys.exit(cli.handle())
    except (KeyboardInterrupt, SystemExit): # pragma: no cover
        if cli.zip_path: # Remove the Zip from S3 upon failure.
            cli.remove_uploaded_zip()
        return
    except Exception as e:
        if cli.zip_path: # Remove the Zip from S3 upon failure.
            cli.remove_uploaded_zip()
        print(e)

if __name__ == '__main__': # pragma: no cover
    handle()