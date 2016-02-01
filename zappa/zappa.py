import base64
import boto3
import botocore
import ConfigParser
import httplib
import math
import os
import time
import zipfile

from boto.s3.connection import S3Connection
from boto.s3.key import Key
from filechunkio import FileChunkIO
from os.path import expanduser
from tqdm import tqdm

from sign_request import sign_request

##
# Policies And Template Mappings
##

TEMPLATE_MAPPING = """{
  "body" : $input.json('$'),
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

POST_TEMPLATE_MAPPING = """#set($rawPostData = $input.path('$'))
{
  "body" : "$rawPostData",
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
          "lambda.amazonaws.com",
          "apigateway.amazonaws.com"
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
        }
    ]
}"""

RESPONSE_TEMPLATE = """#set($inputRoot = $input.path('$'))\n$inputRoot.Content"""
ERROR_RESPONSE_TEMPLATE = """#set($inputRoot = $input.path('$.errorMessage'))\n$util.base64Decode($inputRoot)"""
REDIRECT_RESPONSE_TEMPLATE = ""

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
        'POST'
    ]
    parameter_depth = 5
    integration_response_codes = [200, 301, 400, 401, 403, 404, 500]
    integration_content_types = [
        'text/html',
        # 'application/atom+xml',
        # 'application/json',
        # 'application/jwt',
        # 'application/xml',
    ]
    method_response_codes = [200, 301, 400, 401, 403, 404, 500]
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
    aws_region = "us-east-1"

    ##
    # Credentials
    ##

    access_key = None
    secret_key = None
    credentials_arn = None

    ##
    # Packaging
    ##

    def create_lambda_zip(self, prefix='lambda_package', handler_file=None, minify=True):
        """
        Creates a Lambda-ready zip file of the current virtualenvironment and working directory.

        Returns path to that file.

        """
        print("Packaging project as zip..")

        venv = os.environ['VIRTUAL_ENV']

        output_path = prefix + '-' + str(int(time.time())) + '.zip'
        zipf = zipfile.ZipFile(output_path, 'w')
        path = os.getcwd()

        def splitpath(path):
            parts=[]
            (path, tail)=os.path.split(path)
            while path and tail:
                 parts.append( tail)
                 (path,tail)=os.path.split(path)
            parts.append( os.path.join(path,tail) )
            return map( os.path.normpath, parts)[::-1]
        split_venv = splitpath(venv)

        # First, do the project..
        for root, dirs, files in os.walk(path):
            for filen in files:
                to_write = os.path.join(root, filen)

                # Don't put our package or our entire venv in the package.
                if prefix in to_write:
                    continue

                # Don't put the venv in the package..
                split_to_write = splitpath(to_write)
                if set(split_venv).issubset(set(split_to_write)):
                    continue

                to_write = to_write.split(path + os.sep)[1]
                zipf.write(to_write)

        # Then, do the site-packages..
        # TODO Windows: %VIRTUAL_ENV%\Lib\site-packages 
        site_packages = os.path.join(venv, 'lib', 'python2.7', 'site-packages')
        for root, dirs, files in os.walk(site_packages):
            for filen in files:
                to_write = os.path.join(root, filen)

                # There are few things we can do to reduce the filesize
                if minify:

                    # And don't package boto, because AWS gives us that for free:
                    if 'boto' in to_write:
                        continue
                    if ".exe" in to_write:
                        continue
                    if '.DS_Store' in to_write:
                        continue

                    # If there is a .pyc file in this package,
                    # we can skip the python source code as we'll just
                    # use the compiled bytecode anyway.
                    if to_write[-3:] == '.py':
                        if os.path.isfile(to_write + 'c'):
                            continue

                    # Our package has already been installed,
                    # so we can skip the distribution information.
                    if '.dist-info' in to_write:
                        continue

                arc_write = to_write.split(site_packages)[1]
                zipf.write(to_write, arc_write)

        # If a handler_file is supplied, copy that to the root of the zip,
        # because that's where AWS Lambda looks for it. It can't be inside a package.
        if handler_file:
            filename = handler_file.split(os.sep)[-1]
            zipf.write(handler_file, filename)

        zipf.close()
        return output_path

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
            self.s3_connection = S3Connection()
        except Exception as e:
            print(e)
            return False

        all_buckets = self.s3_connection.get_all_buckets()
        if bucket_name not in [bucket.name for bucket in all_buckets]:
            try:
                self.s3_connection.create_bucket(bucket_name)
            except Exception as e:
                print(e)
                print("Couldn't create bucket.")
                return False

        if (not os.path.isfile(source_path) or os.stat(source_path).st_size == 0):
            print(e)
            return False

        try:
            bucket = self.s3_connection.get_bucket(bucket_name)
            source_size = os.stat(source_path).st_size
            dest_path = os.path.split(source_path)[1]

            # Create a multipart upload request
            mpu = bucket.initiate_multipart_upload(dest_path)

            # Use a chunk size of 5 MiB
            chunk_size = 5242880
            chunk_count = int(math.ceil(source_size / float(chunk_size)))

            print("Uploading zip (" + str(self.human_size(source_size)) + ")..")

            # Send the file parts, using FileChunkIO to create a file-like object
            # that points to a certain byte range within the original file. We
            # set bytes to never exceed the original file size.
            for i in tqdm(range(chunk_count)):
                offset = chunk_size * i
                bytes = min(chunk_size, source_size - offset)
                with FileChunkIO(source_path, 'r', offset=offset,
                                     bytes=bytes) as fp:
                    mpu.upload_part_from_file(fp, part_num=i + 1)

            # Finish the upload
            mpu.complete_upload()

        except Exception as e:
            print(e)
            return False

        return True

    def remove_from_s3(self, file_name, bucket_name):
        """
        Given a file name and a bucket, remove it from S3.

        There's no reason to keep the file hosted on S3 once its been made into a Lambda function, so we can delete it from S3.

        Returns True on success, False on failure.

        """

        s3 = boto3.resource('s3')
        bucket = s3.Bucket(bucket_name)

        try:
            s3.meta.client.head_bucket(Bucket=bucket_name)
        except botocore.exceptions.ClientError as e:
            # If a client error is thrown, then check that it was a 404 error.
            # If it was a 404 error, then the bucket does not exist.
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                return False

        delete_keys={'Objects': [{'Key': file_name}]}
        response = bucket.delete_objects(Delete=delete_keys)
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            return True
        else:
            return False

    ##
    # Lambda
    ##

    def create_lambda_function(self, bucket, s3_key, function_name, handler, description="Zappa Deployment", timeout=30, memory_size=512, publish=True):
        """
        Given a bucket and key of a valid Lambda-zip, a function name and a handler, register that Lambda function.

        """

        client = boto3.client('lambda')
        response = client.create_function(
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
            Publish=publish
        )

        return response['FunctionArn']

    def update_lambda_function(self, bucket, s3_key, function_name, publish=True):
        """
        Given a bucket and key of a valid Lambda-zip, a function name and a handler, update that Lambda function's code.

        """

        client = boto3.client('lambda')
        response = client.update_function_code(
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

        client = boto3.client('lambda')
        response = client.invoke(
            FunctionName=function_name,
            InvocationType=invocation_type,
            LogType=log_type,
            Payload=payload
        )

        return response

    ##
    # API Gateway
    ##

    def create_api_gateway_routes(self, lambda_arn, api_name=None):
        """
        Creates the API Gateway for this Zappa deployment.

        Returns the new API's api_id.

        """

        print("Creating API Gateway routes..")

        client = boto3.client('apigateway')

        if not api_name:
            api_name = str(int(time.time()))

        # Does an API Gateway with this name exist already?
        try:
            response = client.get_rest_api(
                restApiId=api_name
            )
        except botocore.exceptions.ClientError as e:
            response = client.create_rest_api(
                name=api_name,
                description=api_name + " Zappa",
                cloneFrom=''
            )

        api_id = response['id']

        ##
        # The Resources
        ##

        response = client.get_resources(
            restApiId=api_id,
        )

        # AWS seems to create this by default,
        # but not sure if that'll be the case forever.
        parent_id = None
        for item in response['items']:
            if item['path'] == '/':
                root_id = item['id']
        if not root_id:
            return False
        self.create_and_setup_methods(api_id, root_id, lambda_arn)

        parent_id = root_id
        for i in range(1,self.parameter_depth):

            response = client.create_resource(
                restApiId=api_id,
                parentId=parent_id,
                pathPart="{parameter_" + str(i) + "}"
            )
            resource_id = response['id']
            parent_id = resource_id

            self.create_and_setup_methods(api_id, resource_id, lambda_arn)

        return api_id

    def create_and_setup_methods(self, api_id, resource_id, lambda_arn):
        """
        Sets up the methods, integration responses and method responses for a given API Gateway resource.

        Returns the given API's resource_id.

        """

        client = boto3.client('apigateway')

        for method in self.http_methods:

                response = client.put_method(
                    restApiId=api_id,
                    resourceId=resource_id,
                    httpMethod=method,
                    authorizationType='none',
                    apiKeyRequired=False
                )

                # Gotta do this one dirty.. thanks Boto..
                template_mapping = TEMPLATE_MAPPING
                post_template_mapping = POST_TEMPLATE_MAPPING
                content_mapping_templates = {'application/json': template_mapping, 'application/x-www-form-urlencoded': post_template_mapping}
                credentials = self.credentials_arn # This must be a Role ARN
                uri='arn:aws:apigateway:' + self.aws_region + ':lambda:path/2015-03-31/functions/' + lambda_arn + '/invocations'
                url = "/restapis/{0}/resources/{1}/methods/{2}/integration".format(
                    api_id,
                    resource_id,
                    method.upper()
                )

                response = sign_request(
                    self.access_key,
                    self.secret_key,
                    canonical_uri=url,
                    method='put',
                    request_body={
                        "type": "AWS",
                        "httpMethod": "POST",
                        "uri": uri,
                        "credentials": credentials,
                        "requestParameters": {
                        },
                        "requestTemplates": content_mapping_templates,
                        "cacheNamespace": "none",
                        "cacheKeyParameters": []
                    },
                    host='apigateway.' + self.aws_region + '.amazonaws.com',
                    region=self.aws_region,
                )

                ## 
                # Method Response
                ##

                for response in self.method_response_codes:
                    status_code = str(response)

                    response_parameters = {"method.response.header." + header_type: False for header_type in self.method_header_types}
                    response_models = {content_type: 'Empty' for content_type in self.method_content_types}

                    method_response = client.put_method_response(
                        restApiId=api_id,
                        resourceId=resource_id,
                        httpMethod=method,
                        statusCode=status_code,
                        responseParameters=response_parameters,
                        responseModels=response_models
                    )

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
                        selection_pattern = ''
                        response_templates = {content_type: RESPONSE_TEMPLATE for content_type in self.integration_content_types}
                    elif status_code in ['301', '302']:
                        selection_pattern = '\/.*'
                        response_templates = {content_type: REDIRECT_RESPONSE_TEMPLATE for content_type in self.integration_content_types}
                        response_parameters["method.response.header.Location"] = "integration.response.body.errorMessage"
                    else:
                        selection_pattern =  base64.b64encode("<!DOCTYPE html>" + str(status_code)) + '.*'
                        selection_pattern = selection_pattern.replace('+', "\+")
                        response_templates = {content_type: ERROR_RESPONSE_TEMPLATE for content_type in self.integration_content_types}

                    integration_response = client.put_integration_response(
                        restApiId=api_id,
                        resourceId=resource_id,
                        httpMethod=method,
                        statusCode=status_code,
                        selectionPattern=selection_pattern,
                        responseParameters=response_parameters,
                        responseTemplates=response_templates
                    )

        return resource_id

    def deploy_api_gateway(self, api_id, stage_name, stage_description="", description="", cache_cluster_enabled=False, cache_cluster_size='0.5', variables={}):
        """
        Deploy the API Gateway!

        Returns the deployed API URL.

        """

        print("Deploying API Gateway..")

        client = boto3.client('apigateway')
        response = client.create_deployment(
            restApiId=api_id,
            stageName=stage_name,
            stageDescription=stage_description,
            description=description,
            cacheClusterEnabled=cache_cluster_enabled,
            cacheClusterSize=cache_cluster_size,
            variables=variables
        )

        endpoint_url = "https://" + api_id + ".execute-api." + self.aws_region + ".amazonaws.com/" + stage_name
        return endpoint_url

    def get_api_url(self, stage_name):
        """
        Given a stage_name, return a valid API URL.

        """

        client = boto3.client('apigateway')

        response = client.get_rest_apis(
            limit=500
        )

        for item in response['items']:
            if item['description'] == stage_name:
                endpoint_url = "https://" + item['id'] + ".execute-api." + self.aws_region + ".amazonaws.com/" + stage_name
                return endpoint_url

        return ''

    ##
    # IAM
    ##

    def create_iam_roles(self):
        """
        Creates and defines the IAM roles and policies necessary for Zappa.

        """

        assume_policy_s = ASSUME_POLICY
        attach_policy_s = ATTACH_POLICY

        iam = boto3.resource('iam')

        try:
            role = iam.meta.client.get_role(
                RoleName=self.role_name)
            self.credentials_arn = role['Role']['Arn']
            return self.credentials_arn

        except botocore.client.ClientError:
            print("Creating " + self.role_name + " IAM..")

            role = iam.create_role(
                RoleName=self.role_name,
                AssumeRolePolicyDocument=assume_policy_s)
            iam.RolePolicy(self.role_name, 'zappa-permissions').put(
                PolicyDocument=attach_policy_s)

        self.credentials_arn = role.arn
        return self.credentials_arn

    ##
    # Utility
    ##

    def nuke_old_apis(self):
        """

        Deletes old Zappa APIs.
        Useful in case of hitting the AWS APIGW upper limit.

        """

        client = boto3.client('apigateway')
        response = client.get_rest_apis()
        for item in response['items']:
            try:
                int(item['name'])
            except Exception as e:
                continue

            client.delete_rest_api(
                restApiId=item['id']
            )
        return

    def load_credentials(self):
        """

        Loads AWS Credentials from the .aws/credentials file.
        Ideally, this should use ENV as well.

        """

        user_home = expanduser("~")
        config = ConfigParser.ConfigParser()
        config.read([str(user_home + "/.aws/credentials")])
        self.access_key = config.get('default', 'aws_access_key_id')
        self.secret_key = config.get('default', 'aws_secret_access_key')
        return

    def human_size(self, num, suffix='B'):
        for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
            if abs(num) < 1024.0:
                return "%3.1f%s%s" % (num, unit, suffix)
            num /= 1024.0
        return "%.1f%s%s" % (num, 'Yi', suffix)

##
# Main
##

if __name__ == "__main__":

    zappa = Zappa()
    zappa.load_credentials()
    zappa.create_iam_roles()

    zappa.nuke_old_apis()

    zip_path = zappa.create_lambda_zip()
    timestamp = zip_path.replace('.zip', '')
    zip_arn = zappa.upload_to_s3(zip_path, 'lmbda')
    lambda_arn = zappa.create_lambda_function('lmbda', zip_path, timestamp, 'runme.lambda_handler')

    api_id = zappa.create_api_gateway_routes(lambda_arn)
    endpoint_url = zappa.deploy_api_gateway(api_id, "PRODUCTION", stage_description=timestamp, description=timestamp, cache_cluster_enabled=False, cache_cluster_size='0.5', variables={})

    print("Your Zappa deployment is live!: " + endpoint_url)

