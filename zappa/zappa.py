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
import tarfile
import tempfile
import time
import zipfile

from distutils.dir_util import copy_tree
from lambda_packages import lambda_packages
from tqdm import tqdm

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
                "sqs:*"
            ],
            "Resource": "arn:aws:sqs:::*"
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

API_GATEWAY_REGIONS = ['us-east-1', 'us-west-2', 'eu-west-1', 'ap-northeast-1']
LAMBDA_REGIONS = ['us-east-1', 'us-west-2', 'eu-west-1', 'ap-northeast-1']

ZIP_EXCLUDES =  ['*.exe', '*.DS_Store', '*.Python', '*.git', '.git/*', '*.zip', '*.tar.gz', '*.hg', '*.egg-info']

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
    aws_region = 'us-east-1'

    ##
    # Credentials
    ##

    boto_session = None
    credentials_arn = None

    def __init__(self, boto_session=None, profile_name=None, aws_region=aws_region):
        self.aws_region = aws_region
        self.load_credentials(boto_session, profile_name)
        self.s3_client = self.boto_session.client('s3')
        self.lambda_client = self.boto_session.client('lambda')
        self.events_client = self.boto_session.client('events')
        self.apigateway_client = self.boto_session.client('apigateway')
        self.logs_client = self.boto_session.client('logs')
        self.iam_client = self.boto_session.client('iam')
        self.iam = self.boto_session.resource('iam')
        self.s3 = self.boto_session.resource('s3')

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
            try:
                venv = os.environ['VIRTUAL_ENV']
            except KeyError as e: # pragma: no cover
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
            shutil.copytree(cwd, temp_project_path, symlinks=False, ignore=shutil.ignore_patterns(*excludes))
        else:
            shutil.copytree(cwd, temp_project_path, symlinks=False)

        # Then, do the site-packages..
        # TODO Windows: %VIRTUAL_ENV%\Lib\site-packages
        temp_package_path = os.path.join(tempfile.gettempdir(), str(int(time.time() + 1)))
        site_packages = os.path.join(venv, 'lib', 'python2.7', 'site-packages')
        if minify:
            excludes = ZIP_EXCLUDES + exclude
            shutil.copytree(site_packages, temp_package_path, symlinks=False, ignore=shutil.ignore_patterns(*excludes))
        else:
            shutil.copytree(site_packages, temp_package_path, symlinks=False)

        # We may have 64-bin specific packages too.
        site_packages_64 = os.path.join(venv, 'lib64', 'python2.7', 'site-packages')
        if os.path.exists(site_packages_64):
            if minify:
                excludes = ZIP_EXCLUDES + exclude
                shutil.copytree(site_packages_64, temp_package_path, symlinks=False, ignore=shutil.ignore_patterns(*excludes))
            else:
                shutil.copytree(site_packages_64, temp_package_path, symlinks=False)

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

        # If this bucket doesn't exist, make it.
        # Will likely fail, but that's apparently the best way to check
        # it exists, since boto3 doesn't expose a better check.
        try:
            self.s3.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={"LocationConstraint": self.aws_region})
        except botocore.exceptions.ClientError as e: # pragma: no cover
            pass

        if not os.path.isfile(source_path) or os.stat(source_path).st_size == 0:
            print("Problem with source file {}".format(source_path))
            return False

        dest_path = os.path.split(source_path)[1]
        try:
            source_size = os.stat(source_path).st_size
            print("Uploading zip (" + str(self.human_size(source_size)) + ")...")
            progress = tqdm(total=float(os.path.getsize(source_path)), unit_scale=True)

            # Attempt to upload to S3 using the S3 meta client with the progress bar.
            # If we're unable to do that, try one more time using a session client,
            # which cannot use the progress bar.
            # Related: https://github.com/boto/boto3/issues/611
            try:
                self.s3.meta.client.upload_file(
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
        bucket = self.s3.Bucket(bucket_name)

        try:
            self.s3.meta.client.head_bucket(Bucket=bucket_name)
        except botocore.exceptions.ClientError as e: # pragma: no cover
            # If a client error is thrown, then check that it was a 404 error.
            # If it was a 404 error, then the bucket does not exist.
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                return False

        delete_keys = {'Objects': [{'Key': file_name}]}
        response = bucket.delete_objects(Delete=delete_keys)
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            return True
        else: # pragma: no cover
            return False
    ##
    # Lambda
    ##

    def create_lambda_function(self, bucket, s3_key, function_name, handler, description="Zappa Deployment", timeout=30, memory_size=512, publish=True, vpc_config=None):
        """
        Given a bucket and key of a valid Lambda-zip, a function name and a handler, register that Lambda function.

        """

        if not vpc_config:
            vpc_config = {}

        response = self.lambda_client.create_function(
            FunctionName=function_name,
            Runtime='python2.7',
            Role=self.credentials_arn,
            Handler=handler,
            Code={
                'S3Bucket': bucket,
                'S3Key': s3_key,
            },
            Description=description,
            Timeout=timeout,
            MemorySize=memory_size,
            Publish=publish,
            VpcConfig=vpc_config
        )

        return response['FunctionArn']

    def update_lambda_function(self, bucket, s3_key, function_name, publish=True):
        """
        Given a bucket and key of a valid Lambda-zip, a function name and a handler, update that Lambda function's code.

        """

        print("Updating Lambda function..")

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

    def delete_lambda_function(self, function_name):
        """
        Given a function name, delete it from AWS Lambda.

        Returns the response.

        """
        print("Deleting lambda function..")

        return self.lambda_client.delete_function(
            FunctionName=function_name,
        )

    ##
    # API Gateway
    ##

    def create_api_gateway_routes(self, lambda_arn, api_name=None):
        """
        Creates the API Gateway for this Zappa deployment.

        Returns the new API's api_id.

        """

        print("Creating API Gateway routes..")

        if not api_name:
            api_name = str(int(time.time()))

        # Does an API Gateway with this name exist already?
        apis = self.apigateway_client.get_rest_apis()['items']
        if not len(filter(lambda a: a['name'] == api_name, apis)):
            response = self.apigateway_client.create_rest_api(
                name=api_name,
                description=api_name + " Zappa",
                cloneFrom=''
            )

        api_id = response['id']

        ##
        # The Resources
        ##

        response = self.apigateway_client.get_resources(restApiId=api_id)

        # count how many put requests we'll be reporting for progress bar
        progress_total = self.parameter_depth * len(self.http_methods) * (
                             2 + len(self.integration_response_codes) + len(self.method_response_codes)) - 1
        progress = tqdm(total=progress_total)

        # AWS seems to create this by default,
        # but not sure if that'll be the case forever.
        parent_id = None
        for item in response['items']:
            if item['path'] == '/':
                root_id = item['id']
        if not root_id: # pragma: no cover
            return False
        self.create_and_setup_methods(api_id, root_id, lambda_arn, progress.update)

        parent_id = root_id
        for i in range(1, self.parameter_depth):

            response = self.apigateway_client.create_resource(
                restApiId=api_id,
                parentId=parent_id,
                pathPart="{parameter_" + str(i) + "}"
            )
            resource_id = response['id']
            parent_id = resource_id

            self.create_and_setup_methods(api_id, resource_id, lambda_arn, progress.update) # pragma: no cover

        return api_id

    def create_and_setup_methods(self, api_id, resource_id, lambda_arn, report_progress):
        """
        Sets up the methods, integration responses and method responses for a given API Gateway resource.

        Returns the given API's resource_id.

        """

        for method in self.http_methods:
            response = self.apigateway_client.put_method(
                    restApiId=api_id,
                    resourceId=resource_id,
                    httpMethod=method,
                    authorizationType='none',
                    apiKeyRequired=False
            )
            report_progress()

            template_mapping = TEMPLATE_MAPPING
            post_template_mapping = POST_TEMPLATE_MAPPING
            form_encoded_template_mapping = FORM_ENCODED_TEMPLATE_MAPPING
            content_mapping_templates = {
                'application/json': post_template_mapping,
                'application/x-www-form-urlencoded': post_template_mapping,
                'multipart/form-data': form_encoded_template_mapping
            }
            credentials = self.credentials_arn  # This must be a Role ARN
            uri = 'arn:aws:apigateway:' + self.boto_session.region_name + ':lambda:path/2015-03-31/functions/' + lambda_arn + '/invocations'

            self.apigateway_client.put_integration(
                restApiId=api_id,
                resourceId=resource_id,
                httpMethod=method.upper(),
                type='AWS',
                integrationHttpMethod='POST',
                uri=uri,
                credentials=credentials,
                requestParameters={},
                requestTemplates=content_mapping_templates,
                cacheNamespace='none',
                cacheKeyParameters=[]
            )
            report_progress()

            ##
            # Method Response
            ##

            for response in self.method_response_codes:
                status_code = str(response)

                response_parameters = {"method.response.header." + header_type: False for header_type in self.method_header_types}
                response_models = {content_type: 'Empty' for content_type in self.method_content_types}

                method_response = self.apigateway_client.put_method_response(
                        restApiId=api_id,
                        resourceId=resource_id,
                        httpMethod=method,
                        statusCode=status_code,
                        responseParameters=response_parameters,
                        responseModels=response_models
                )
                report_progress()

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

                integration_response = self.apigateway_client.put_integration_response(
                        restApiId=api_id,
                        resourceId=resource_id,
                        httpMethod=method,
                        statusCode=status_code,
                        selectionPattern=self.selection_pattern(status_code),
                        responseParameters=response_parameters,
                        responseTemplates=response_templates
                )
                report_progress()

        return resource_id

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

    def deploy_api_gateway(self, api_id, stage_name, stage_description="", description="", cache_cluster_enabled=False, cache_cluster_size='0.5', variables=None):
        """
        Deploy the API Gateway!

        Returns the deployed API URL.

        """

        print("Deploying API Gateway..")

        response = self.apigateway_client.create_deployment(
            restApiId=api_id,
            stageName=stage_name,
            stageDescription=stage_description,
            description=description,
            cacheClusterEnabled=cache_cluster_enabled,
            cacheClusterSize=cache_cluster_size,
            variables=variables or {}
        )

        return "https://{}.execute-api.{}.amazonaws.com/{}".format(api_id, self.boto_session.region_name, stage_name)

    def undeploy_api_gateway(self, project_name):
        """
        Delete a deployed REST API Gateway.

        """

        print("Deleting API Gateway..")

        all_apis = self.apigateway_client.get_rest_apis(
            limit=500
        )

        for api in all_apis['items']:
            if api['name'] != project_name:
                continue
            response = self.apigateway_client.delete_rest_api(
                restApiId=api['id']
            )


    def get_api_url(self, stage_name):
        """
        Given a stage_name, return a valid API URL.

        """

        response = self.apigateway_client.get_rest_apis(limit=500)

        for item in response['items']:
            if item['description'] == stage_name:
                return "https://{}.execute-api.{}.amazonaws.com/{}".format(item['id'], self.boto_session.region_name, stage_name)

    ##
    # IAM
    ##

    def create_iam_roles(self):
        """
        Creates and defines the IAM roles and policies necessary for Zappa.

        If the IAM role already exists, it will be updated if necessary.
        """
        assume_policy_s = ASSUME_POLICY
        attach_policy_s = ATTACH_POLICY

        attach_policy_obj = json.loads(attach_policy_s)
        assume_policy_obj = json.loads(assume_policy_s)

        # Create the role if needed
        role = self.iam.Role(self.role_name)
        try:
            self.credentials_arn = role.arn

        except botocore.client.ClientError:
            print("Creating " + self.role_name + " IAM Role...")

            role = self.iam.create_role(RoleName=self.role_name,
                                   AssumeRolePolicyDocument=assume_policy_s)
            self.credentials_arn = role.arn

        # create or update the role's policies if needed
        policy = self.iam.RolePolicy(self.role_name, 'zappa-permissions')
        try:
            if policy.policy_document != attach_policy_obj:
                print("Updating zappa-permissions policy on " + self.role_name + " IAM Role.")
                policy.put(PolicyDocument=attach_policy_s)

        except botocore.client.ClientError:
            print("Creating zappa-permissions policy on " + self.role_name + " IAM Role.")
            policy.put(PolicyDocument=attach_policy_s)

        if role.assume_role_policy_document != assume_policy_obj and \
                set(role.assume_role_policy_document['Statement'][0]['Principal']['Service']) != set(assume_policy_obj['Statement'][0]['Principal']['Service']):
            print("Updating assume role policy on " + self.role_name + " IAM Role.")
            self.iam_client.update_assume_role_policy(
                RoleName=self.role_name,
                PolicyDocument=assume_policy_s
            )

        return self.credentials_arn

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
            expression = event['expression']
            name = event.get('name', function)
            description = event.get('description', function)

            self.delete_rule(name)
            #   - If 'cron' or 'rate' in expression, use ScheduleExpression
            #   - Else, use EventPattern
            #       - ex https://github.com/awslabs/aws-lambda-ddns-function

            if not self.credentials_arn:
                self.credentials_arn = self.create_iam_roles()

            if 'cron' in expression or 'rate' in expression:
                rule_response = self.events_client.put_rule(
                    Name=name,
                    ScheduleExpression=expression,
                    State='ENABLED',
                    Description=description,
                    RoleArn=self.credentials_arn
                )
            else:
                rule_response = self.events_client.put_rule(
                    Name=name,
                    EventPattern=expression,
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
                        'Input': json.dumps({'detail': function})
                    }
                ]
            )

            if target_response['ResponseMetadata']['HTTPStatusCode'] == 200:
                print("Scheduled {} at {}.".format(name, expression))
            else:
                print("Problem scheduling {} at {}.".format(name, expression))


    def delete_rule(self, rule_name):
        """
        Delete a CWE rule.

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


    def unschedule_events(self, events):
        """
        Given a list of events, unschedule these CloudWatch Events.

        'events' is a list of dictionaries, where the dict must contains the string
        of a 'function' and the string of the event 'expression', and an optional 'name' and 'description'.

        """

        for event in events:
            if event.has_key('function'):
                function = event['function']
                name = event.get('name', function)
                self.delete_rule(name)

                print("Uncheduled " + name + ".")


    def create_keep_warm(self, lambda_arn, lambda_name, name="zappa-keep-warm", schedule_expression="rate(5 minutes)"):
        """
        Schedule a regularly occuring execution to keep the function warm in cache.

        """

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

    def human_size(self, num, suffix='B'):
        for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
            if abs(num) < 1024.0:
                return "{0:3.1f}{1!s}{2!s}".format(num, unit, suffix)
            num /= 1024.0
        return "{0:.1f}{1!s}{2!s}".format(num, 'Yi', suffix)
