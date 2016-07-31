import base64
import boto3
import botocore
import json
import logging
import os
import pip
import random
import requests
import shutil
import string
import subprocess
import tarfile
import tempfile
import time
import zipfile
import troposphere
import troposphere.apigateway
import troposphere.awslambda

import kappa
from distutils.dir_util import copy_tree
from lambda_packages import lambda_packages
from tqdm import tqdm

# Zappa imports
from util import copytree, add_event_source, remove_event_source

logging.basicConfig(format='%(levelname)s:%(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


##
# Policies And Template Mappings
##

TEMPLATE_MAPPING = """{
  "body" : "$util.base64Encode($input.json("$"))",
  "headers": {
    #foreach($header in $input.params().header.keySet())
    "$header": "$util.escapeJavaScript($input.params().header.get($header))" #if($foreach.hasNext),#end

    #end
  },
  "method": "$context.httpMethod",
  "params": {
    #foreach($param in $input.params().path.keySet())
    "$param": "$util.escapeJavaScript($input.params().path.get($param))" #if($foreach.hasNext),#end

    #end
  },
  "query": {
    #foreach($queryParam in $input.params().querystring.keySet())
    "$queryParam": "$util.escapeJavaScript($input.params().querystring.get($queryParam))" #if($foreach.hasNext),#end

    #end
  }
}"""

POST_TEMPLATE_MAPPING = """#set($rawPostData = $input.path("$"))
{
  "body" : "$util.base64Encode($input.body)",
  "headers": {
    #foreach($header in $input.params().header.keySet())
    "$header": "$util.escapeJavaScript($input.params().header.get($header))" #if($foreach.hasNext),#end

    #end
  },
  "method": "$context.httpMethod",
  "params": {
    #foreach($param in $input.params().path.keySet())
    "$param": "$util.escapeJavaScript($input.params().path.get($param))" #if($foreach.hasNext),#end

    #end
  },
  "query": {
    #foreach($queryParam in $input.params().querystring.keySet())
    "$queryParam": "$util.escapeJavaScript($input.params().querystring.get($queryParam))" #if($foreach.hasNext),#end

    #end
  }
}"""

FORM_ENCODED_TEMPLATE_MAPPING = """
{
  "body" : "$util.base64Encode($input.body)",
  "headers": {
    #foreach($header in $input.params().header.keySet())
    "$header": "$util.escapeJavaScript($input.params().header.get($header))" #if($foreach.hasNext),#end

    #end
  },
  "method": "$context.httpMethod",
  "params": {
    #foreach($param in $input.params().path.keySet())
    "$param": "$util.escapeJavaScript($input.params().path.get($param))" #if($foreach.hasNext),#end

    #end
  },
  "query": {
    #foreach($queryParam in $input.params().querystring.keySet())
    "$queryParam": "$util.escapeJavaScript($input.params().querystring.get($queryParam))" #if($foreach.hasNext),#end

    #end
  }
}"""

ASSUME_POLICY = """{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "",
      "Effect": "Allow",
      "Principal": {
        "Service": [
          "apigateway.amazonaws.com",
          "lambda.amazonaws.com",
          "events.amazonaws.com"
        ]
      },
      "Action": "sts:AssumeRole"
    }
  ]
}"""

ATTACH_POLICY = """{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:*"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "lambda:InvokeFunction"
            ],
            "Resource": [
                "*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "ec2:CreateNetworkInterface"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:*"
            ],
            "Resource": "arn:aws:s3:::*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "sns:*"
            ],
            "Resource": "arn:aws:sns:*:*:*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "sqs:*"
            ],
            "Resource": "arn:aws:sqs:*:*:*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "dynamodb:*"
            ],
            "Resource": "arn:aws:dynamodb:*:*:*"
        }
    ]
}"""

RESPONSE_TEMPLATE = """#set($inputRoot = $input.path('$'))\n$inputRoot.Content"""
ERROR_RESPONSE_TEMPLATE = """#set($inputRoot = $input.path('$.errorMessage'))\n$util.base64Decode($inputRoot)"""
REDIRECT_RESPONSE_TEMPLATE = ""

API_GATEWAY_REGIONS = ['us-east-1', 'us-west-2', 'eu-west-1', 'eu-central-1', 'ap-northeast-1', 'ap-southeast-2']
LAMBDA_REGIONS = ['us-east-1', 'us-west-2', 'eu-west-1', 'eu-central-1', 'ap-northeast-1', 'ap-southeast-2']

ZIP_EXCLUDES =  ['*.exe', '*.DS_Store', '*.Python', '*.git', '.git/*', '*.zip', '*.tar.gz', '*.hg', '*.egg-info', 'botocore*', 'pip', 'docutils*', 'boto3*', 'setuputils*', '*.dist-info']

##
# Classes
##

class Zappa(object):
    """
    Zappa!

    Makes it easy to run Python web applications on AWS Lambda/API Gateway.

    """
    ##
    # Configurables
    ##

    http_methods = [
        'DELETE',
        'GET',
        'HEAD',
        'OPTIONS',
        'PATCH',
        'POST',
        'PUT'
    ]
    parameter_depth = 8
    integration_response_codes = [200, 201, 301, 400, 401, 403, 404, 500]
    integration_content_types = [
        'text/html',
    ]
    method_response_codes = [200, 201, 301, 400, 401, 403, 404, 500]
    method_content_types = [
        'text/html',
    ]
    method_header_types = [
        'Content-Type',
        'Location',
        'Status',
        'X-Frame-Options',
        'Set-Cookie'
    ]

    role_name = "ZappaLambdaExecution"
    assume_policy = ASSUME_POLICY
    attach_policy = ATTACH_POLICY
    aws_region = 'us-east-1'

    ##
    # Credentials
    ##

    boto_session = None
    credentials_arn = None

    def __init__(self, boto_session=None, profile_name=None, aws_region=aws_region):
        self.aws_region = aws_region

        # Some common invokations, such as DB migrations,
        # can take longer than the default.

        # Note that this is set to 300s, but if connected to
        # APIGW, Lambda will max out at 30s.
        # Related: https://github.com/Miserlou/Zappa/issues/205
        long_config_dict = {
            'region_name': aws_region,
            'connect_timeout': 5,
            'read_timeout': 300
        }
        long_config = botocore.client.Config(**long_config_dict)

        self.load_credentials(boto_session, profile_name)
        self.s3_client = self.boto_session.client('s3')
        self.lambda_client = self.boto_session.client('lambda', config=long_config)
        self.events_client = self.boto_session.client('events')
        #self.apigateway_client = self.boto_session.client('apigateway')
        self.logs_client = self.boto_session.client('logs')
        self.iam_client = self.boto_session.client('iam')
        self.iam = self.boto_session.resource('iam')
        self.cf_client = self.boto_session.client('cloudformation')
        self.cf_template = troposphere.Template()
        self.cf_template.add_description('Automatically generated with Zappa')
        self.cf_api_resources = []
        self.cf_role = None

    ##
    # Packaging
    ##

    def create_lambda_zip(self, prefix='lambda_package', handler_file=None,
                          minify=True, exclude=None, use_precompiled_packages=True, include=None, venv=None):
        """
        Creates a Lambda-ready zip file of the current virtualenvironment and working directory.

        Returns path to that file.

        """
        print("Packaging project as zip...")

        if not venv:
            if 'VIRTUAL_ENV' in os.environ:
                venv = os.environ['VIRTUAL_ENV']
            elif os.path.exists('.python-version'): # pragma: no cover
                logger.debug("Pyenv's local virtualenv detected.")
                try:
                    subprocess.check_output('pyenv', stderr=subprocess.STDOUT)
                except OSError as e:
                    print("This directory seems to have pyenv's local venv"
                          "but pyenv executable was not found.")
                with open('.python-version', 'r') as f:
                    env_name = f.read()[:-1]
                    logger.debug('env name = {}'.format(env_name))
                bin_path = subprocess.check_output(['pyenv', 'which', 'python']).decode('utf-8')
                venv = bin_path[:bin_path.rfind(env_name)] + env_name
                logger.debug('env path = {}'.format(venv))
            else: # pragma: no cover
                print("Zappa requires an active virtual environment.")
                quit()

        cwd = os.getcwd()
        zip_fname = prefix + '-' + str(int(time.time())) + '.zip'
        zip_path = os.path.join(cwd, zip_fname)

        # Files that should be excluded from the zip
        if exclude is None:
            exclude = list()

        # Exclude the zip itself
        exclude.append(zip_path)

        def splitpath(path):
            parts = []
            (path, tail) = os.path.split(path)
            while path and tail:
                parts.append(tail)
                (path, tail) = os.path.split(path)
            parts.append(os.path.join(path, tail))
            return map(os.path.normpath, parts)[::-1]
        split_venv = splitpath(venv)
        split_cwd = splitpath(cwd)

        # Ideally this should be avoided automatically,
        # but this serves as an okay stop-gap measure.
        if split_venv[-1] == split_cwd[-1]: # pragma: no cover
            print("Warning! Your project and virtualenv have the same name! You may want to re-create your venv with a new name, or explicitly define a 'project_name', as this may cause errors.")

        # First, do the project..
        temp_project_path = os.path.join(tempfile.gettempdir(), str(int(time.time())))

        if minify:
            excludes = ZIP_EXCLUDES + exclude + [split_venv[-1]]
            copytree(cwd, temp_project_path, symlinks=False, ignore=shutil.ignore_patterns(*excludes))
        else:
            copytree(cwd, temp_project_path, symlinks=False)

        # Then, do the site-packages..
        # TODO Windows: %VIRTUAL_ENV%\Lib\site-packages
        temp_package_path = os.path.join(tempfile.gettempdir(), str(int(time.time() + 1)))
        site_packages = os.path.join(venv, 'lib', 'python2.7', 'site-packages')
        if minify:
            excludes = ZIP_EXCLUDES + exclude
            copytree(site_packages, temp_package_path, symlinks=False, ignore=shutil.ignore_patterns(*excludes))
        else:
            copytree(site_packages, temp_package_path, symlinks=False)

        # We may have 64-bin specific packages too.
        site_packages_64 = os.path.join(venv, 'lib64', 'python2.7', 'site-packages')
        if os.path.exists(site_packages_64):
            if minify:
                excludes = ZIP_EXCLUDES + exclude
                copytree(site_packages_64, temp_package_path, symlinks=False, ignore=shutil.ignore_patterns(*excludes))
            else:
                copytree(site_packages_64, temp_package_path, symlinks=False)

        copy_tree(temp_package_path, temp_project_path, update=True)

        # Then the pre-compiled packages..
        if use_precompiled_packages:
            installed_packages_name_set = {package.project_name.lower() for package in
                                           pip.get_installed_distributions()}

            for name, details in lambda_packages.items():
                if name.lower() in installed_packages_name_set:
                    tar = tarfile.open(details['path'], mode="r:gz")
                    for member in tar.getmembers():
                        # If we can, trash the local version.
                        if member.isdir():
                            shutil.rmtree(os.path.join(temp_project_path, member.name), ignore_errors=True)
                            continue

                        tar.extract(member, temp_project_path)

        # If a handler_file is supplied, copy that to the root of the package,
        # because that's where AWS Lambda looks for it. It can't be inside a package.
        if handler_file:
            filename = handler_file.split(os.sep)[-1]
            shutil.copy(handler_file, os.path.join(temp_project_path, filename))

        # Then zip it all up..
        try:
            import zlib
            compression_method = zipfile.ZIP_DEFLATED
        except ImportError as e: # pragma: no cover
            compression_method = zipfile.ZIP_STORED

        zipf = zipfile.ZipFile(zip_path, 'w', compression_method)
        for root, dirs, files in os.walk(temp_project_path):
            for filename in files:

                # If there is a .pyc file in this package,
                # we can skip the python source code as we'll just
                # use the compiled bytecode anyway..
                if filename[-3:] == '.py':
                    abs_filname = os.path.join(root, filename)
                    abs_pyc_filename = abs_filname + 'c'
                    if os.path.isfile(abs_pyc_filename):

                        # but only if the pyc is older than the py,
                        # otherwise we'll deploy outdated code!
                        py_time = os.stat(abs_filname).st_mtime
                        pyc_time = os.stat(abs_pyc_filename).st_mtime

                        if pyc_time > py_time:
                            continue

                zipf.write(os.path.join(root, filename), os.path.join(root.replace(temp_project_path, ''), filename))

        # And, we're done!
        zipf.close()

        # Trash the temp directory
        shutil.rmtree(temp_project_path)
        shutil.rmtree(temp_package_path)

        # Warn if this is too large for Lambda.
        file_stats = os.stat(zip_path)
        if file_stats.st_size > 52428800: # pragma: no cover
            print("\n\nWarning: Application zip package is likely to be too large for AWS Lambda.\n\n")

        return zip_fname

    ##
    # S3
    ##

    def upload_to_s3(self, source_path, bucket_name):
        """
        Given a file, upload it to S3.
        Credentials should be stored in environment variables or ~/.aws/credentials (%USERPROFILE%\.aws\credentials on Windows).

        Returns True on success, false on failure.

        """

        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
        except botocore.exceptions.ClientError:
            # This is really stupid S3 quirk. Technically, us-east-1 one has no S3,
            # it's actually "US Standard", or something.
            # More here: https://github.com/boto/boto3/issues/125
            if self.aws_region == 'us-east-1':
                self.s3_client.create_bucket(
                    Bucket=bucket_name,
                )
            else:
                self.s3_client.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': self.aws_region},
                )

        if not os.path.isfile(source_path) or os.stat(source_path).st_size == 0:
            print("Problem with source file {}".format(source_path))
            return False

        dest_path = os.path.split(source_path)[1]
        try:
            source_size = os.stat(source_path).st_size
            print("Uploading {0} ({1})...".format(dest_path, self.human_size(source_size)))
            progress = tqdm(total=float(os.path.getsize(source_path)), unit_scale=True)

            # Attempt to upload to S3 using the S3 meta client with the progress bar.
            # If we're unable to do that, try one more time using a session client,
            # which cannot use the progress bar.
            # Related: https://github.com/boto/boto3/issues/611
            try:
                self.s3_client.upload_file(
                    source_path, bucket_name, dest_path,
                    Callback=progress.update
                )
            except Exception as e: # pragma: no cover
                self.s3_client.upload_file(source_path, bucket_name, dest_path)

            progress.close()
        except (KeyboardInterrupt, SystemExit): # pragma: no cover
            raise
        except Exception as e: # pragma: no cover
            print(e)
            return False
        return True

    def remove_from_s3(self, file_name, bucket_name):
        """
        Given a file name and a bucket, remove it from S3.

        There's no reason to keep the file hosted on S3 once its been made into a Lambda function, so we can delete it from S3.

        Returns True on success, False on failure.

        """
        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
        except botocore.exceptions.ClientError as e: # pragma: no cover
            # If a client error is thrown, then check that it was a 404 error.
            # If it was a 404 error, then the bucket does not exist.
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                return False

        try:
            self.s3_client.delete_object(Bucket=bucket_name, Key=file_name)
            return True
        except botocore.exceptions.ClientError:
            return False

    ##
    # Lambda
    ##

    def create_lambda_function(self, bucket, s3_key, function_name, handler, description="Zappa Deployment", timeout=30, memory_size=512, publish=True, vpc_config=None):
        """
        Given a bucket and key of a valid Lambda-zip, a function name and a handler, register that Lambda function.

        """

        if self.credentials_arn:
            credentials = self.credentials_arn  # This must be a Role ARN
        elif self.cf_role:
            credentials = troposphere.GetAtt(self.cf_role, 'Arn')
        else:
            raise Exception('Could not find pre-made Role ARN or CloudFormation Role')

        function = troposphere.awslambda.Function('Function')
        function.Description = description
        function.FunctionName = function_name
        function.Handler = handler
        function.MemorySize = memory_size
        function.Role = credentials
        function.Runtime = 'python2.7'
        function.Timeout = timeout

        if vpc_config:
            conf = troposphere.awslambda.VPCConfig()
            conf.SecurityGroupIds = vpc_config['SecurityGroupIds']
            conf.SubnetIds = vpc_config['SubnetIds']
            function.VpcConfig = conf

        code = troposphere.awslambda.Code()
        code.S3Bucket = bucket
        code.S3Key = s3_key
        function.Code = code

        self.cf_template.add_resource(function)

        return function

    def update_lambda_function(self, bucket, s3_key, function_name, publish=True):
        """
        Given a bucket and key of a valid Lambda-zip, a function name and a handler, update that Lambda function's code.

        """

        print("Updating Lambda function code..")

        response = self.lambda_client.update_function_code(
            FunctionName=function_name,
            S3Bucket=bucket,
            S3Key=s3_key,
            Publish=publish
        )

        return response['FunctionArn']

    def invoke_lambda_function(self, function_name, payload, invocation_type='Event', log_type='Tail', client_context=None, qualifier=None):
        """
        Directly invoke a named Lambda function with a payload.
        Returns the response.

        """

        return self.lambda_client.invoke(
            FunctionName=function_name,
            InvocationType=invocation_type,
            LogType=log_type,
            Payload=payload
        )


    def rollback_lambda_function_version(self, function_name, versions_back=1, publish=True):
        """
        Rollback the lambda function code 'versions_back' number of revisions.

        Returns the Function ARN.

        """
        response = self.lambda_client.list_versions_by_function(FunctionName=function_name)

        #Take into account $LATEST
        if len(response['Versions']) < versions_back + 1:
            print("We do not have {} revisions. Aborting".format(str(versions_back)))
            return False

        revisions = [int(revision['Version']) for revision in response['Versions'] if revision['Version'] != '$LATEST']
        revisions.sort(reverse=True)

        response = self.lambda_client.get_function(FunctionName='function:{}:{}'.format(function_name, revisions[versions_back]))
        response = requests.get(response['Code']['Location'])

        if response.status_code != 200:
            print("Failed to get version {} of {} code".format(versions_back, function_name))
            return False

        response = self.lambda_client.update_function_code(FunctionName=function_name, ZipFile=response.content, Publish=publish) # pragma: no cover

        return response['FunctionArn']

    def get_lambda_function_versions(self, function_name):
        """
        Simply returns the versions available for a Lambda function, given a function name.

        """
        try:
            response = self.lambda_client.list_versions_by_function(FunctionName=function_name)
            return response
        except Exception as e:
            return []

    def delete_lambda_function(self, function_name):
        """
        Given a function name, delete it from AWS Lambda.

        Returns the response.

        """
        print("Deleting Lambda function..")

        return self.lambda_client.delete_function(
            FunctionName=function_name,
        )

    ##
    # API Gateway
    ##

    def create_api_gateway_routes(self, name, lambda_func, api_key_required=False):
        """
        Creates the API Gateway for this Zappa deployment.

        Returns the new API's api_id.

        """

        ##
        # The Resources
        ##

        restapi = troposphere.apigateway.RestApi('Api')
        restapi.Name = name
        restapi.Description = 'Created automatically by Zappa.'
        self.cf_template.add_resource(restapi)

        root_id = troposphere.GetAtt(restapi, 'RootResourceId')

        self.create_and_setup_methods(restapi, root_id, lambda_func, api_key_required, 0)

            self.create_and_setup_methods(restapi, resource, lambda_func, i) # pragma: no cover
            parent_id = troposphere.Ref(resource)

        return restapi

    def create_and_setup_methods(self, restapi, resource, lambda_func, api_key_required, depth):
        """
        Sets up the methods, integration responses and method responses for a given API Gateway resource.

        Returns the given API's resource_id.

        """

        for method_name in self.http_methods:
            method = troposphere.apigateway.Method(method_name + str(depth))
            method.DependsOn = 'Function'
            method.RestApiId = troposphere.Ref(restapi)
            if type(resource) is troposphere.apigateway.Resource:
                method.ResourceId = troposphere.Ref(resource)
            else:
                method.ResourceId = resource
            method.HttpMethod = method_name.upper()
            method.AuthorizationType = 'none'
            method.ApiKeyRequired = api_key_required
            method.MethodResponses = []
            self.cf_template.add_resource(method)
            self.cf_api_resources.append(method.title)

            template_mapping = TEMPLATE_MAPPING
            post_template_mapping = POST_TEMPLATE_MAPPING
            form_encoded_template_mapping = FORM_ENCODED_TEMPLATE_MAPPING
            content_mapping_templates = {
                'application/json': post_template_mapping,
                'application/x-www-form-urlencoded': post_template_mapping,
                'multipart/form-data': form_encoded_template_mapping
            }

            if self.credentials_arn:
                credentials = self.credentials_arn  # This must be a Role ARN
            elif self.cf_role:
                credentials = troposphere.GetAtt(self.cf_role, 'Arn')
            else:
                raise Exception('Could not find pre-made Role ARN or CloudFormation Role')

            uri = troposphere.Join('', [
                'arn:aws:apigateway:',
                self.boto_session.region_name,
                ':lambda:path/2015-03-31/functions/',
                troposphere.GetAtt(lambda_func, 'Arn'),
                '/invocations'
            ])

            integration = troposphere.apigateway.Integration()
            integration.CacheKeyParameters = []
            integration.CacheNamespace = 'none'
            integration.Credentials = credentials
            integration.IntegrationHttpMethod = 'POST'
            integration.IntegrationResponses = []
            integration.RequestParameters = {}
            integration.RequestTemplates = content_mapping_templates
            integration.Type = 'AWS'
            integration.Uri = uri
            method.Integration = integration

            ##
            # Method Response
            ##

            for response_code in self.method_response_codes:
                status_code = str(response_code)

                response_parameters = {"method.response.header." + header_type: False for header_type in self.method_header_types}
                response_models = {content_type: 'Empty' for content_type in self.method_content_types}

                response = troposphere.apigateway.MethodResponse()
                response.ResponseModels = response_models
                response.ResponseParameters = response_parameters
                response.StatusCode = status_code
                method.MethodResponses.append(response)


            ##
            # Integration Response
            ##

            for response in self.integration_response_codes:
                status_code = str(response)

                response_parameters = {"method.response.header." + header_type: "integration.response.body." + header_type for header_type in self.method_header_types}

                # Error code matching RegEx
                # Thanks to @KevinHornschemeier and @jayway
                # for the discussion on this.
                if status_code == '200':
                    response_templates = {content_type: RESPONSE_TEMPLATE for content_type in self.integration_content_types}
                elif status_code in ['301', '302']:
                    response_templates = {content_type: REDIRECT_RESPONSE_TEMPLATE for content_type in self.integration_content_types}
                    response_parameters["method.response.header.Location"] = "integration.response.body.errorMessage"
                else:
                    response_templates = {content_type: ERROR_RESPONSE_TEMPLATE for content_type in self.integration_content_types}

                integration_response = troposphere.apigateway.IntegrationResponse()
                integration_response.ResponseParameters = response_parameters
                integration_response.ResponseTemplates = response_templates
                integration_response.SelectionPattern = self.selection_pattern(status_code)
                integration_response.StatusCode = status_code
                integration.IntegrationResponses.append(integration_response)


    def deploy_api_gateway(self, restapi, stage_name, stage_description="", description="", cache_cluster_enabled=False, cache_cluster_size='0.5', variables=None, api_key_required=False):
        """
        Deploy the API Gateway!

        Returns the deployed API URL.

        """

        deployment = troposphere.apigateway.Deployment('Deployment')
        deployment.RestApiId = troposphere.Ref(restapi)
        deployment.StageName = stage_name
        deployment.DependsOn = self.cf_api_resources

        description = troposphere.apigateway.StageDescription()
        description.Description = stage_description
        description.CacheClusterEnabled = cache_cluster_enabled
        description.CacheClusterSize = cache_cluster_size
        description.Variables = variables or {}
        deployment.StageDescription = description
        self.cf_template.add_resource(deployment)

        if api_key_required:
            api_key = troposphere.apigateway.ApiKey('APIKey')
            api_key.Enabled = True

            stage_key = troposphere.apigateway.StageKey()
            stage_key.RestApiId = troposphere.Ref(restapi)
            stage_key.StageName = stage_name
            api_key.StageKeys = [stage_key]

            self.cf_template.add_resource(api_key)
            print('x-api-key: {}'.format(api_key['id']))
            self.cf_template.add_output([
                troposphere.Output('APIKey',
                                   Description='APIKey Zappa deployment',
                                   Value = troposphere.Ref(api_key))
            ])

        endpoint_value = troposphere.Join('', [
            'https://',
            troposphere.Ref(restapi),
            '.execute-api.',
            self.boto_session.region_name,
            '.amazonaws.com/',
            stage_name
        ])

        self.cf_template.add_output([
            troposphere.Output('Endpoint',
                               Description='HTTP Endpoint for this Zappa deployment',
                               Value = endpoint_value)
        ])

    def update_stack(self, name, working_bucket, wait=False):
        capabilities = []
        if self.cf_role:
            capabilities.append('CAPABILITY_IAM')

        template = name + '-template-' + str(int(time.time())) + '.json'
        with open(template, 'w') as out:
            out.write(self.cf_template.to_json(indent=None, separators=(',',':')))

        self.upload_to_s3(template, working_bucket)

        url = 'https://s3.amazonaws.com/{0}/{1}'.format(working_bucket, template)

        tags = [{'Key':'ZappaProject','Value':name}]

        update = False
        waiter = 'stack_create_complete'

        try:
            stack = self.cf_client.describe_stacks(StackName=name)['Stacks'][0]
            waiter = 'stack_update_complete'
        except botocore.client.ClientError:
            update = True

        if update:
            self.cf_client.create_stack(StackName=name,
                                        Capabilities=capabilities,
                                        TemplateURL=url,
                                        Tags=tags)
            print('Waiting for stack {0} to finish creating...'.format(name))
        else:
            self.cf_client.update_stack(StackName=name,
                                        Capabilities=capabilities,
                                        TemplateURL=url,
                                        Tags=tags)
            print('Waiting for stack {0} to update...'.format(name))

        if wait:
            polling = self.cf_client.get_waiter(waiter)
            polling.wait(StackName=name)
            # TODO cleanup if it fails!

        try:
            os.remove(template)
        except:
            pass

        self.remove_from_s3(template, working_bucket)

    def stack_outputs(self, name):
        try:
            stack = self.cf_client.describe_stacks(StackName=name)['Stacks'][0]
            return {x['OutputKey']: x['OutputValue'] for x in stack['Outputs']}
        except botocore.client.ClientError:
            return {}

    def get_api_url(self, project_name, stage_name):
        """
        Given a project_name and stage_name, return a valid API URL.

        """
        self.stack_outputs(project_name).get('Endpoint')

    ##
    # IAM
    ##

    def create_iam_roles(self):
        """
        Creates and defines the IAM roles and policies necessary for Zappa.

        If the IAM role already exists, it will be updated if necessary.
        """
        attach_policy_obj = json.loads(self.attach_policy)
        assume_policy_obj = json.loads(self.assume_policy)

        # Create the role if needed
        role = self.iam.Role(self.role_name)
        try:
            self.credentials_arn = role.arn
            self.cf_role = None

        except botocore.client.ClientError:
            role = troposphere.iam.Role(self.role_name)
            role.AssumeRolePolicyDocument = self.assume_policy
            role.Policies = [self.attach_policy]
            troposphere.add_resource(role)
            self.cf_role = role

    ##
    # CloudWatch Events
    ##

    def schedule_events(self, lambda_arn, lambda_name, events):
        """
        Given a Lambda ARN, name and a list of events, schedule this as CloudWatch Events.

        'events' is a list of dictionaries, where the dict must contains the string
        of a 'function' and the string of the event 'expression', and an optional 'name' and 'description'.

        Expressions can be in rate or cron format:
            http://docs.aws.amazon.com/lambda/latest/dg/tutorial-scheduled-events-schedule-expressions.html

        """
        for event in events:
            function = event['function']
            expression = event.get('expression', None)
            event_source = event.get('event_source', None)
            name = event.get('name', function)
            description = event.get('description', function)

            self.delete_rule(name)
            #   - If 'cron' or 'rate' in expression, use ScheduleExpression
            #   - Else, use EventPattern
            #       - ex https://github.com/awslabs/aws-lambda-ddns-function

            if not self.credentials_arn:
                self.credentials_arn = self.create_iam_roles()

            if expression:
                rule_response = self.events_client.put_rule(
                    Name=name,
                    ScheduleExpression=expression,
                    State='ENABLED',
                    Description=description,
                    RoleArn=self.credentials_arn
                )

                if 'RuleArn' in rule_response:
                    logger.debug('Rule created. ARN {}'.format(rule_response['RuleArn']))

                logger.debug('Adding new permission to invoke Lambda function: {}'.format(lambda_name))
                permission_response = self.lambda_client.add_permission(
                    FunctionName=lambda_name,
                    StatementId=''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8)),
                    Action='lambda:InvokeFunction',
                    Principal='events.amazonaws.com',
                    SourceArn=rule_response['RuleArn'],
                )

                if permission_response['ResponseMetadata']['HTTPStatusCode'] != 201:
                    print('Problem creating permission to invoke Lambda function')
                    return

                # Create the CloudWatch event ARN for this function.
                target_response = self.events_client.put_targets(
                    Rule=name,
                    Targets=[
                        {
                            'Id': 'Id' + ''.join(random.choice(string.digits) for _ in range(12)),
                            'Arn': lambda_arn,
                        }
                    ]
                )

                if target_response['ResponseMetadata']['HTTPStatusCode'] == 200:
                    print("Scheduled {}!".format(name))
                else:
                    print("Problem scheduling {}.".format(name))

            else:

                rule_response = add_event_source(
                                                    event_source,
                                                    lambda_arn,
                                                    function,
                                                    self.boto_session
                                                )
                #if rule_response: # Kappa doesn't give us this yet.
                svc = ','.join(event['event_source']['events'])
                print("Created %s event schedule for %s!" % (svc, function))

    def delete_rule(self, rule_name):
        """
        Delete a CWE rule.

        This  deletes them, but they will still show up in the AWS console.
        Annoying.

        """
        logger.debug('Deleting existing rule {}'.format(rule_name))

        # All targets must be removed before
        # we can actually delete the rule.
        try:
            targets = self.events_client.list_targets_by_rule(Rule=rule_name)
        except botocore.exceptions.ClientError as e:
            logger.debug('No target found for this rule: {} {}'.format(rule_name, e.message))
            return

        if 'Targets' in targets and targets['Targets']:
            response = self.events_client.remove_targets(Rule=rule_name, Ids=[x['Id'] for x in targets['Targets']])
        else: # pragma: no cover
            logger.debug('No target to delete')

        # Delete our rules.
        rules = self.events_client.list_rules(NamePrefix=rule_name)
        if 'Rules' in rules and rules['Rules']:
            for rule in rules['Rules']:
                if rule['Name'] == rule_name:
                    logger.debug('Deleting rule: {}'.format(rule_name))
                    self.events_client.delete_rule(Name=rule_name)


    def unschedule_events(self, events, lambda_arn):
        """
        Given a list of events, unschedule these CloudWatch Events.

        'events' is a list of dictionaries, where the dict must contains the string
        of a 'function' and the string of the event 'expression', and an optional 'name' and 'description'.

        """

        for event in events:

            # These are scheduled CWEs.
            if event.has_key('expression'):
                function = event['function']
                name = event.get('name', function)
                self.delete_rule(name)
                print("Unscheduled " + name + ".")
            # These are non CWE event sources.
            elif event.has_key('event_source'):
                function = event['function']
                name = event.get('name', function)
                event_source = event.get('event_source', function)
                rule_response = remove_event_source(  
                                                    event_source,
                                                    lambda_arn,
                                                    function, 
                                                    self.boto_session
                                                )
                print("Removed event " + name + ".")


    def create_keep_warm(self, lambda_arn, lambda_name, name="zappa-keep-warm", schedule_expression="rate(5 minutes)"):
        """
        Schedule a regularly occuring execution to keep the function warm in cache.

        """
        raise NotImplementedError()

        rule_name = name + "-" + str(lambda_name)

        print("Scheduling keep-warm..")

        # Do we have an old keepwarm for this?
        self.delete_rule(rule_name)

        response = self.events_client.put_rule(
            Name=rule_name,
            ScheduleExpression=schedule_expression,
            State='ENABLED',
            Description='Zappa Keep Warm - ' + str(lambda_name),
            RoleArn=self.credentials_arn
        )

        response = self.lambda_client.add_permission(
            FunctionName=lambda_name,
            StatementId=''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8)),
            Action='lambda:InvokeFunction',
            Principal='events.amazonaws.com',
            SourceArn=response['RuleArn'],
        )

        response = self.events_client.put_targets(
            Rule=rule_name,
            Targets=[
                {
                    'Id': str(sum([ ord(c) for c in lambda_arn])), # Is this insane?
                    'Arn': lambda_arn,
                    'Input': '',
                },
            ]
        )

    def remove_keep_warm(self, lambda_name, name="zappa-keep-warm"):
        """
        Unschedule the regularly occuring execution to keep the function warm in cache.

        """

        print("Removing keep-warm..")

        self.delete_rule("{}-{}".format(name, str(lambda_name)))


    ##
    # CloudWatch Logging
    ##

    def fetch_logs(self, lambda_name, filter_pattern='', limit=10000):
        """
        Fetch the CloudWatch logs for a given Lambda name.

        """

        log_name = '/aws/lambda/' + lambda_name
        streams = self.logs_client.describe_log_streams(logGroupName=log_name,
                                            descending=True,
                                            orderBy='LastEventTime')

        all_streams = streams['logStreams']
        all_names = [stream['logStreamName'] for stream in all_streams]
        response = self.logs_client.filter_log_events(logGroupName=log_name,
                            logStreamNames=all_names,
                            filterPattern=filter_pattern,
                            limit=limit)

        return response['events']

    ##
    # Utility
    ##

    def load_credentials(self, boto_session=None, profile_name=None):
        """
        Load AWS credentials.

        An optional boto_session can be provided, but that's usually for testing.

        An optional profile_name can be provided for config files that have multiple sets
        of credentials.
        """

        # Automatically load credentials from config or environment
        if not boto_session:

            # Set aws_region to None to use the system's region instead
            if self.aws_region is None:
                self.aws_region = boto3.Session().region_name
                logger.debug("Set region from boto: %s", self.aws_region)

            # If provided, use the supplied profile name.
            if profile_name:
                self.boto_session = boto3.Session(profile_name=profile_name, region_name=self.aws_region)
            elif os.environ.get('AWS_ACCESS_KEY_ID') and os.environ.get('AWS_SECRET_ACCESS_KEY'):
                region_name = os.environ.get('AWS_DEFAULT_REGION') or self.aws_region
                self.boto_session = boto3.Session(
                    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
                    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
                    region_name=region_name)
            else:
                self.boto_session = boto3.Session(region_name=self.aws_region)

            logger.debug("Loaded boto session from config: %s", boto_session)
        else:
            logger.debug("Using provided boto session: %s", boto_session)
            self.boto_session = boto_session

        # use provided session's region in case it differs
        self.aws_region = self.boto_session.region_name

        if self.boto_session.region_name not in LAMBDA_REGIONS:
            print("Warning! AWS Lambda may not be available in this AWS Region!")

        if self.boto_session.region_name not in API_GATEWAY_REGIONS:
            print("Warning! AWS API Gateway may not be available in this AWS Region!")


    @staticmethod
    def selection_pattern(status_code):
        """
        Generate a regex to match a given status code in a response.
        """

        pattern = ''

        if status_code in ['301', '302']:
            pattern = 'https://.*|/.*'
        elif status_code != '200':
            pattern = base64.b64encode("<!DOCTYPE html>" + str(status_code)) + '.*'
            pattern = pattern.replace('+', r"\+")

        return pattern

    def human_size(self, num, suffix='B'):
        for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
            if abs(num) < 1024.0:
                return "{0:3.1f}{1!s}{2!s}".format(num, unit, suffix)
            num /= 1024.0
        return "{0:.1f}{1!s}{2!s}".format(num, 'Yi', suffix)
