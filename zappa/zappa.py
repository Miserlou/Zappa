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
# Configurables
##

HTTP_METHODS = [
    'DELETE', 
    'GET',
    'HEAD',
    'OPTIONS',
    'PATCH',
    'POST'
]
PARAMETER_DEPTH = 1
INTEGRATION_RESPONSE_METHODS = [200, 404, 500]
ROLE_NAME = "ZappaLambdaExecution"
AWS_REGION = "us-east-1"

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

RESPONSE_TEMPLATE = """#set($inputRoot = $input.path('$'))\n$inputRoot.Body"""

##
# Classes
##

class Zappa(object):
    """
    Zappa!

    Makes it easy to run Python web applications on AWS Lambda/API Gateway.

    """

    access_key = None
    secret_key = None
    credentials_arn = None

    ##
    # Packaging
    ##

    def create_lambda_zip(self, prefix='lambda_package'):
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

                # And don't package boto, because AWS gives us that for free:
                if 'boto' in to_write:
                    continue
                if ".exe" in to_write:
                    continue
                if '.DS_Store' in to_write:
                    continue

                arc_write = to_write.split(site_packages)[1]
                zipf.write(to_write, arc_write)

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

            # Use a chunk size of 50 MiB
            chunk_size = 5242880
            chunk_count = int(math.ceil(source_size / float(chunk_size)))

            print("Uploading Zip..")

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
        for i in range(1,PARAMETER_DEPTH):

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

        for method in HTTP_METHODS:

                response = client.put_method(
                    restApiId=api_id,
                    resourceId=resource_id,
                    httpMethod=method,
                    authorizationType='none',
                    apiKeyRequired=False
                )

                # Gotta do this one dirty.. thanks Boto..
                template_mapping = TEMPLATE_MAPPING
                content_mapping_templates = {'application/json': template_mapping}
                credentials = self.credentials_arn # This must be a Role ARN
                uri='arn:aws:apigateway:' + AWS_REGION + ':lambda:path/2015-03-31/functions/' + lambda_arn + '/invocations'
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
                    }
                )

                ##
                # Integration Response
                ##

                response_template = RESPONSE_TEMPLATE
                for response in INTEGRATION_RESPONSE_METHODS:
                    status_code = str(response)
                    response = client.put_integration_response(
                        restApiId=api_id,
                        resourceId=resource_id,
                        httpMethod=method,
                        statusCode=status_code,
                        selectionPattern='',
                        responseParameters={
                        },
                        responseTemplates={
                            'text/html': response_template
                        }
                    )

                ## 
                # Method Response
                ##

                for response in [200, 404, 500]:
                    status_code = str(response)
                    response = client.put_method_response(
                        restApiId=api_id,
                        resourceId=resource_id,
                        httpMethod=method,
                        statusCode=status_code,
                        responseParameters={
                        },
                        responseModels={
                            'text/html': 'Empty'
                        }
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

        endpoint_url = "https://" + api_id + ".execute-api." + AWS_REGION + ".amazonaws.com/" + stage_name
        return endpoint_url

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
                RoleName=ROLE_NAME)
            self.credentials_arn = role['Role']['Arn']
            return self.credentials_arn

        except botocore.client.ClientError:
            print("Creating " + ROLE_NAME + " IAM..")

            role = iam.create_role(
                RoleName=ROLE_NAME,
                AssumeRolePolicyDocument=assume_policy_s)
            iam.RolePolicy(ROLE_NAME, 'zappa-permissions').put(
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

