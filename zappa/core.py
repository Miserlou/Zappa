from __future__ import print_function

import boto3
import botocore
import glob
import json
import logging
import os
import random
import requests
import shutil
import string
import subprocess
import tarfile
import tempfile
import time
import troposphere
import troposphere.apigateway
import zipfile

from builtins import int, bytes
from botocore.exceptions import ClientError
from distutils.dir_util import copy_tree
from io import BytesIO, open
from lambda_packages import lambda_packages as lambda_packages_orig
from setuptools import find_packages
from tqdm import tqdm

# Zappa imports
from .utilities import (copytree,
                    add_event_source,
                    remove_event_source,
                    human_size,
                    get_topic_name,
                    contains_python_files_or_subdirs,
                    conflicts_with_a_neighbouring_module,
                    get_venv_from_python_version)

##
# Logging Config
##

logging.basicConfig(format='%(levelname)s:%(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# We lower-case lambda package keys to match lower-cased keys in get_installed_packages()
lambda_packages = {package_name.lower():val
                   for package_name,val in lambda_packages_orig.items()}

##
# Policies And Template Mappings
##

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
                "ec2:AttachNetworkInterface",
                "ec2:CreateNetworkInterface",
                "ec2:DeleteNetworkInterface",
                "ec2:DescribeInstances",
                "ec2:DescribeNetworkInterfaces",
                "ec2:DetachNetworkInterface",
                "ec2:ModifyNetworkInterfaceAttribute",
                "ec2:ResetNetworkInterfaceAttribute"
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
                "kinesis:*"
            ],
            "Resource": "arn:aws:kinesis:*:*:*"
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
        },
        {
            "Effect": "Allow",
            "Action": [
                "route53:*"
            ],
            "Resource": "*"
        }
    ]
}"""

# Latest list: https://docs.aws.amazon.com/general/latest/gr/rande.html#apigateway_region
API_GATEWAY_REGIONS = ['us-east-1', 'us-east-2',
                       'us-west-1', 'us-west-2',
                       'eu-central-1',
                       'eu-west-1', 'eu-west-2',
                       'ap-northeast-1', 'ap-northeast-2',
                       'ap-southeast-1', 'ap-southeast-2',
                       'ap-south-1']

# Latest list: https://docs.aws.amazon.com/general/latest/gr/rande.html#lambda_region
LAMBDA_REGIONS = ['us-east-1', 'us-east-2',
                  'us-west-1', 'us-west-2',
                  'eu-central-1',
                  'eu-west-1', 'eu-west-2',
                  'ap-northeast-1', 'ap-northeast-2',
                  'ap-southeast-1', 'ap-southeast-2',
                  'ap-south-1']

# We never need to include these.
# Related: https://github.com/Miserlou/Zappa/pull/56
# Related: https://github.com/Miserlou/Zappa/pull/581
ZIP_EXCLUDES = [
    '*.exe', '*.DS_Store', '*.Python', '*.git', '.git/*', '*.zip', '*.tar.gz',
    '*.hg', '*.egg-info', 'pip', 'docutils*', 'setuputils*'
]

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
        'ANY'
    ]
    role_name = "ZappaLambdaExecution"
    extra_permissions = None
    assume_policy = ASSUME_POLICY
    attach_policy = ATTACH_POLICY
    cloudwatch_log_levels = ['OFF', 'ERROR', 'INFO']

    ##
    # Credentials
    ##

    boto_session = None
    credentials_arn = None

    def __init__(self,
            boto_session=None,
            profile_name=None,
            aws_region=None,
            load_credentials=True,
            desired_role_name=None,
            runtime='python2.7'
        ):
        # Set aws_region to None to use the system's region instead
        if aws_region is None:
            # https://github.com/Miserlou/Zappa/issues/413
            self.aws_region = boto3.Session().region_name
            logger.debug("Set region from boto: %s", self.aws_region)
        else:
            self.aws_region = aws_region

        if desired_role_name:
            self.role_name = desired_role_name

        self.runtime = runtime

        if self.runtime == 'python2.7':
            self.manylinux_wheel_file_suffix = 'cp27mu-manylinux1_x86_64.whl'
        else:
            self.manylinux_wheel_file_suffix = 'cp36m-manylinux1_x86_64.whl'


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

        if load_credentials:
            self.load_credentials(boto_session, profile_name)

        self.s3_client = self.boto_session.client('s3')
        self.lambda_client = self.boto_session.client('lambda', config=long_config)
        self.events_client = self.boto_session.client('events')
        self.apigateway_client = self.boto_session.client('apigateway')
        # acm certificates need to be created from us-east-1 to be used by API gateway
        east_config = botocore.client.Config(region_name='us-east-1')
        self.acm_client = self.boto_session.client('acm', config=east_config)
        self.logs_client = self.boto_session.client('logs')
        self.iam_client = self.boto_session.client('iam')
        self.iam = self.boto_session.resource('iam')
        self.cloudwatch = self.boto_session.client('cloudwatch')
        self.route53 = self.boto_session.client('route53')
        self.sns_client = self.boto_session.client('sns')
        self.cf_client = self.boto_session.client('cloudformation')
        self.cf_template = troposphere.Template()
        self.cf_api_resources = []
        self.cf_parameters = {}

    def cache_param(self, value):
        '''Returns a troposphere Ref to a value cached as a parameter.'''

        if value not in self.cf_parameters:
            keyname = chr(ord('A') + len(self.cf_parameters))
            param = self.cf_template.add_parameter(troposphere.Parameter(
                keyname, Type="String", Default=value
            ))

            self.cf_parameters[value] = param

        return troposphere.Ref(self.cf_parameters[value])

    ##
    # Packaging
    ##
    def copy_editable_packages(self, egg_links, temp_package_path):
        """ """
        for egg_link in egg_links:
            with open(egg_link, 'rb') as df:
                egg_path = df.read().decode('utf-8').splitlines()[0].strip()
                pkgs = set([x.split(".")[0] for x in find_packages(egg_path, exclude=['test', 'tests'])])
                for pkg in pkgs:
                    copytree(os.path.join(egg_path, pkg), os.path.join(temp_package_path, pkg), symlinks=False)

        if temp_package_path:
            # now remove any egg-links as they will cause issues if they still exist
            for link in glob.glob(os.path.join(temp_package_path, "*.egg-link")):
                os.remove(link)

    def get_deps_list(self, pkg_name, installed_distros=None):
        """
        For a given package, returns a list of required packages. Recursive.
        """
        import pip
        deps = []
        if not installed_distros:
            installed_distros = pip.get_installed_distributions()
        for package in installed_distros:
            if package.project_name.lower() == pkg_name.lower():
                deps = [(package.project_name, package.version)]
                for req in package.requires():
                    deps += self.get_deps_list(pkg_name=req.project_name, installed_distros=installed_distros)
        return list(set(deps))  # de-dupe before returning

    def create_handler_venv(self):
        """
        Takes the installed zappa and brings it into a fresh virtualenv-like folder. All dependencies are then downloaded.
        """
        import pip

        # We will need the currenv venv to pull Zappa from
        current_venv = self.get_current_venv()

        # Make a new folder for the handler packages
        ve_path = os.path.join(os.getcwd(), 'handler_venv')

        if os.sys.platform == 'win32':
            current_site_packages_dir = os.path.join(current_venv, 'Lib', 'site-packages')
            venv_site_packages_dir = os.path.join(ve_path, 'Lib', 'site-packages')
        else:
            current_site_packages_dir = os.path.join(current_venv, 'lib', get_venv_from_python_version(), 'site-packages')
            venv_site_packages_dir = os.path.join(ve_path, 'lib', get_venv_from_python_version(), 'site-packages')

        if not os.path.isdir(venv_site_packages_dir):
            os.makedirs(venv_site_packages_dir)

        # Copy zappa* to the new virtualenv
        zappa_things = [z for z in os.listdir(current_site_packages_dir) if z.lower()[:5] == 'zappa']
        for z in zappa_things:
            copytree(os.path.join(current_site_packages_dir, z), os.path.join(venv_site_packages_dir, z))

        # Use pip to download zappa's dependencies. Copying from current venv causes issues with things like PyYAML that installs as yaml
        zappa_deps = self.get_deps_list('zappa')
        pkg_list = ['{0!s}=={1!s}'.format(dep, version) for dep, version in zappa_deps]

        # Need to manually add setuptools
        pkg_list.append('setuptools')
        pip.main(["install", "--quiet", "--target", venv_site_packages_dir] + pkg_list)

        return ve_path

    # staticmethod as per https://github.com/Miserlou/Zappa/issues/780
    @staticmethod
    def get_current_venv():
        """
        Returns the path to the current virtualenv
        """
        if 'VIRTUAL_ENV' in os.environ:
            venv = os.environ['VIRTUAL_ENV']
        elif os.path.exists('.python-version'):  # pragma: no cover
            try:
                subprocess.check_output('pyenv help', stderr=subprocess.STDOUT)
            except OSError:
                print("This directory seems to have pyenv's local venv, "
                      "but pyenv executable was not found.")
            with open('.python-version', 'r') as f:
                # minor fix in how .python-version is read
                # Related: https://github.com/Miserlou/Zappa/issues/921
                env_name = f.readline().strip()
            bin_path = subprocess.check_output(['pyenv', 'which', 'python']).decode('utf-8')
            venv = bin_path[:bin_path.rfind(env_name)] + env_name
        else:  # pragma: no cover
            return None
        return venv

    def create_lambda_zip(  self,
                            prefix='lambda_package',
                            handler_file=None,
                            slim_handler=False,
                            minify=True,
                            exclude=None,
                            use_precompiled_packages=True,
                            include=None,
                            venv=None,
                            output=None
                        ):
        """
        Create a Lambda-ready zip file of the current virtualenvironment and working directory.

        Returns path to that file.

        """
        # Pip is a weird package.
        # Calling this function in some environments without this can cause.. funkiness.
        import pip

        if not venv:
            venv = self.get_current_venv()

        cwd = os.getcwd()
        if not output:
            zip_fname = prefix + '-' + str(int(time.time())) + '.zip'
        else:
            zip_fname = output
        zip_path = os.path.join(cwd, zip_fname)

        # Files that should be excluded from the zip
        if exclude is None:
            exclude = list()

        # Exclude the zip itself
        exclude.append(zip_path)

        # Make sure that 'concurrent' is always forbidden.
        # https://github.com/Miserlou/Zappa/issues/827
        if not 'concurrent' in exclude:
            exclude.append('concurrent')

        def splitpath(path):
            parts = []
            (path, tail) = os.path.split(path)
            while path and tail:
                parts.append(tail)
                (path, tail) = os.path.split(path)
            parts.append(os.path.join(path, tail))
            return list(map(os.path.normpath, parts))[::-1]
        split_venv = splitpath(venv)
        split_cwd = splitpath(cwd)

        # Ideally this should be avoided automatically,
        # but this serves as an okay stop-gap measure.
        if split_venv[-1] == split_cwd[-1]:  # pragma: no cover
            print(
                "Warning! Your project and virtualenv have the same name! You may want "
                "to re-create your venv with a new name, or explicitly define a "
                "'project_name', as this may cause errors."
            )

        # First, do the project..
        temp_project_path = os.path.join(tempfile.gettempdir(), str(int(time.time())))

        os.makedirs(temp_project_path)
        if not slim_handler:
            # Slim handler does not take the project files.
            if minify:
                # Related: https://github.com/Miserlou/Zappa/issues/744
                excludes = ZIP_EXCLUDES + exclude + [split_venv[-1]]
                copytree(cwd, temp_project_path, symlinks=False, ignore=shutil.ignore_patterns(*excludes))
            else:
                copytree(cwd, temp_project_path, symlinks=False)

        # If a handler_file is supplied, copy that to the root of the package,
        # because that's where AWS Lambda looks for it. It can't be inside a package.
        if handler_file:
            filename = handler_file.split(os.sep)[-1]
            shutil.copy(handler_file, os.path.join(temp_project_path, filename))

        # Then, do site site-packages..
        egg_links = []
        temp_package_path = os.path.join(tempfile.gettempdir(), str(int(time.time() + 1)))
        if os.sys.platform == 'win32':
            site_packages = os.path.join(venv, 'Lib', 'site-packages')
        else:
            site_packages = os.path.join(venv, 'lib', get_venv_from_python_version(), 'site-packages')
        egg_links.extend(glob.glob(os.path.join(site_packages, '*.egg-link')))

        if minify:
            excludes = ZIP_EXCLUDES + exclude
            copytree(site_packages, temp_package_path, symlinks=False, ignore=shutil.ignore_patterns(*excludes))

        else:
            copytree(site_packages, temp_package_path, symlinks=False)

        # We may have 64-bin specific packages too.
        site_packages_64 = os.path.join(venv, 'lib64', get_venv_from_python_version(), 'site-packages')
        if os.path.exists(site_packages_64):
            egg_links.extend(glob.glob(os.path.join(site_packages_64, '*.egg-link')))
            if minify:
                excludes = ZIP_EXCLUDES + exclude
                copytree(site_packages_64, temp_package_path, symlinks=False, ignore=shutil.ignore_patterns(*excludes))
            else:
                copytree(site_packages_64, temp_package_path, symlinks=False)

        if egg_links:
            self.copy_editable_packages(egg_links, temp_package_path)

        copy_tree(temp_package_path, temp_project_path, update=True)

        # Then the pre-compiled packages..
        if use_precompiled_packages:
            print("Downloading and installing dependencies..")
            installed_packages = self.get_installed_packages(site_packages, site_packages_64)

            try:
                for installed_package_name, installed_package_version in installed_packages.items():
                    if self.have_correct_lambda_package_version(installed_package_name, installed_package_version):
                        print(" - %s==%s: Using precompiled lambda package " % (installed_package_name, installed_package_version,))
                        self.extract_lambda_package(installed_package_name, temp_project_path)
                    else:
                        cached_wheel_path = self.get_cached_manylinux_wheel(installed_package_name, installed_package_version)
                        if cached_wheel_path:
                            # Otherwise try to use manylinux packages from PyPi..
                            # Related: https://github.com/Miserlou/Zappa/issues/398
                            shutil.rmtree(os.path.join(temp_project_path, installed_package_name), ignore_errors=True)
                            with zipfile.ZipFile(cached_wheel_path) as zfile:
                                zfile.extractall(temp_project_path)

                        elif self.have_any_lambda_package_version(installed_package_name):
                            # Finally see if we may have at least one version of the package in lambda packages
                            # Related: https://github.com/Miserlou/Zappa/issues/855
                            lambda_version = lambda_packages[installed_package_name][self.runtime]['version']
                            print(" - %s==%s: Warning! Using precompiled lambda package version %s instead!" % (installed_package_name, installed_package_version, lambda_version, ))
                            self.extract_lambda_package(installed_package_name, temp_project_path)

            except Exception as e:
                print(e)
                # XXX - What should we do here?

        # Then zip it all up..
        print("Packaging project as zip..")
        try:
            # import zlib
            compression_method = zipfile.ZIP_DEFLATED
        except ImportError:  # pragma: no cover
            compression_method = zipfile.ZIP_STORED

        zipf = zipfile.ZipFile(zip_path, 'w', compression_method)
        for root, dirs, files in os.walk(temp_project_path):

            for filename in files:

                # Skip .pyc files for Django migrations
                # https://github.com/Miserlou/Zappa/issues/436
                # https://github.com/Miserlou/Zappa/issues/464
                if filename[-4:] == '.pyc' and root[-10:] == 'migrations':
                    continue

                # If there is a .pyc file in this package,
                # we can skip the python source code as we'll just
                # use the compiled bytecode anyway..
                if filename[-3:] == '.py' and root[-10:] != 'migrations':
                    abs_filname = os.path.join(root, filename)
                    abs_pyc_filename = abs_filname + 'c'
                    if os.path.isfile(abs_pyc_filename):

                        # but only if the pyc is older than the py,
                        # otherwise we'll deploy outdated code!
                        py_time = os.stat(abs_filname).st_mtime
                        pyc_time = os.stat(abs_pyc_filename).st_mtime

                        if pyc_time > py_time:
                            continue

                # Make sure that the files are all correctly chmodded
                # Related: https://github.com/Miserlou/Zappa/issues/484
                # Related: https://github.com/Miserlou/Zappa/issues/682
                os.chmod(os.path.join(root, filename),  0o755)

                # Actually put the file into the proper place in the zip
                # Related: https://github.com/Miserlou/Zappa/pull/716
                zipi = zipfile.ZipInfo(os.path.join(root.replace(temp_project_path, '').lstrip(os.sep), filename))
                zipi.create_system = 3
                zipi.external_attr = 0o755 << int(16) # Is this P2/P3 functional?
                with open(os.path.join(root, filename), 'rb') as f:
                    zipf.writestr(zipi, f.read(), compression_method)

            # Create python init file if it does not exist
            # Only do that if there are sub folders or python files and does not conflict with a neighbouring module
            # Related: https://github.com/Miserlou/Zappa/issues/766
            if not contains_python_files_or_subdirs(root):
                # if the directory does not contain any .py file at any level, we can skip the rest
                dirs[:] = [d for d in dirs if d != root]
            else:
                if '__init__.py' not in files and not conflicts_with_a_neighbouring_module(root):
                    tmp_init = os.path.join(temp_project_path, '__init__.py')
                    open(tmp_init, 'a').close()
                    os.chmod(tmp_init,  0o755)
                    zipf.write(tmp_init,
                               os.path.join(root.replace(temp_project_path, ''),
                                            os.path.join(root.replace(temp_project_path, ''), '__init__.py')))

        # And, we're done!
        zipf.close()

        # Trash the temp directory
        shutil.rmtree(temp_project_path)
        shutil.rmtree(temp_package_path)
        if os.path.isdir(venv) and slim_handler:
            # Remove the temporary handler venv folder
            shutil.rmtree(venv)

        return zip_fname

    def extract_lambda_package(self, package_name, path):
        """
        Extracts the lambda package into a given path. Assumes the package exists in lambda packages.
        """
        lambda_package = lambda_packages[package_name][self.runtime]

        # Trash the local version to help with package space saving
        shutil.rmtree(os.path.join(path, package_name), ignore_errors=True)

        tar = tarfile.open(lambda_package['path'], mode="r:gz")
        for member in tar.getmembers():
            tar.extract(member, path)

    @staticmethod
    def get_installed_packages(site_packages, site_packages_64):
        """
        Returns a dict of installed packages that Zappa cares about.
        """
        import pip  # this is to avoid 'funkiness' with global import
        package_to_keep = []
        if os.path.isdir(site_packages):
            package_to_keep += os.listdir(site_packages)
        if os.path.isdir(site_packages_64):
            package_to_keep += os.listdir(site_packages_64)

        installed_packages = {package.project_name.lower(): package.version for package in
                              pip.get_installed_distributions() if package.project_name in package_to_keep or
                              package.location in [site_packages, site_packages_64]}

        return installed_packages

    def have_correct_lambda_package_version(self, package_name, package_version):
        """
        Checks if a given package version binary should be copied over from lambda packages.
        package_name should be lower-cased version of package name.
        """
        lambda_package_details = lambda_packages.get(package_name, {}).get(self.runtime)

        if lambda_package_details is None:
            return False

        # Binaries can be compiled for different package versions
        # Related: https://github.com/Miserlou/Zappa/issues/800
        if package_version != lambda_package_details['version']:
            return False

        return True

    def have_any_lambda_package_version(self, package_name):
        """
        Checks if a given package has any lambda package version. We can try and use it with a warning.
        package_name should be lower-cased version of package name.
        """
        return lambda_packages.get(package_name, {}).get(self.runtime) is not None

    @staticmethod
    def download_url_with_progress(url, stream):
        """
        Downloads a given url in chunks and writes to the provided stream (can be any io stream).
        Displays the progress bar for the download.
        """
        resp = requests.get(url, timeout=2, stream=True)
        resp.raw.decode_content = True

        progress = tqdm(unit="B", unit_scale=True, total=int(resp.headers.get('Content-Length', 0)))
        for chunk in resp.iter_content(chunk_size=1024):
            if chunk:
                progress.update(len(chunk))
                stream.write(chunk)

        progress.close()

    def get_cached_manylinux_wheel(self, package_name, package_version):
        """
        Gets the locally stored version of a manylinux wheel. If one does not exist, the function downloads it.
        """
        cached_wheels_dir = os.path.join(tempfile.gettempdir(), 'cached_wheels')
        if not os.path.isdir(cached_wheels_dir):
            os.makedirs(cached_wheels_dir)

        wheel_file = '{0!s}-{1!s}-{2!s}'.format(package_name, package_version, self.manylinux_wheel_file_suffix)
        wheel_path = os.path.join(cached_wheels_dir, wheel_file)

        if not os.path.exists(wheel_path):
            # The file is not cached, download it.
            wheel_url = self.get_manylinux_wheel_url(package_name, package_version)
            if not wheel_url:
                return None

            print(" - {}=={}: Downloading".format(package_name, package_version))
            with open(wheel_path, 'wb') as f:
                self.download_url_with_progress(wheel_url, f)
        else:
            print(" - {}=={}: Using locally cached manylinux wheel".format(package_name, package_version))

        return wheel_path

    def get_manylinux_wheel_url(self, package_name, package_version):
        """
        For a given package name, returns a link to the download URL,
        else returns None.

        Related: https://github.com/Miserlou/Zappa/issues/398
        Examples here: https://gist.github.com/perrygeo/9545f94eaddec18a65fd7b56880adbae
        """
        url = 'https://pypi.python.org/pypi/{}/json'.format(package_name)
        try:
            res = requests.get(url, timeout=1.5)
            data = res.json()
            for f in data['releases'][package_version]:
                if f['filename'].endswith(self.manylinux_wheel_file_suffix):
                    return f['url']
        except Exception as e: # pragma: no cover
            return None
        return None

    ##
    # S3
    ##

    def upload_to_s3(self, source_path, bucket_name):
        r"""
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
            print("Uploading {0} ({1})..".format(dest_path, human_size(source_size)))
            progress = tqdm(total=float(os.path.getsize(source_path)), unit_scale=True, unit='B')

            # Attempt to upload to S3 using the S3 meta client with the progress bar.
            # If we're unable to do that, try one more time using a session client,
            # which cannot use the progress bar.
            # Related: https://github.com/boto/boto3/issues/611
            try:
                self.s3_client.upload_file(
                    source_path, bucket_name, dest_path,
                    Callback=progress.update
                )
            except Exception as e:  # pragma: no cover
                self.s3_client.upload_file(source_path, bucket_name, dest_path)

            progress.close()
        except (KeyboardInterrupt, SystemExit):  # pragma: no cover
            raise
        except Exception as e:  # pragma: no cover
            print(e)
            return False
        return True

    def copy_on_s3(self, src_file_name, dst_file_name, bucket_name):
        """
        Copies src file to destination within a bucket.
        """
        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
        except botocore.exceptions.ClientError as e:  # pragma: no cover
            # If a client error is thrown, then check that it was a 404 error.
            # If it was a 404 error, then the bucket does not exist.
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                return False

        copy_src = {
            "Bucket": bucket_name,
            "Key": src_file_name
        }
        try:
            self.s3_client.copy(
                CopySource=copy_src,
                Bucket=bucket_name,
                Key=dst_file_name
            )
            return True
        except botocore.exceptions.ClientError:  # pragma: no cover
            return False

    def remove_from_s3(self, file_name, bucket_name):
        """
        Given a file name and a bucket, remove it from S3.

        There's no reason to keep the file hosted on S3 once its been made into a Lambda function, so we can delete it from S3.

        Returns True on success, False on failure.

        """
        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
        except botocore.exceptions.ClientError as e:  # pragma: no cover
            # If a client error is thrown, then check that it was a 404 error.
            # If it was a 404 error, then the bucket does not exist.
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                return False

        try:
            self.s3_client.delete_object(Bucket=bucket_name, Key=file_name)
            return True
        except botocore.exceptions.ClientError:  # pragma: no cover
            return False

    ##
    # Lambda
    ##

    def create_lambda_function( self,
                                bucket,
                                s3_key,
                                function_name,
                                handler,
                                description='Zappa Deployment',
                                timeout=30,
                                memory_size=512,
                                publish=True,
                                vpc_config=None,
                                dead_letter_config=None,
                                runtime='python2.7',
                                environment_variables=None,
                                aws_kms_key_arn=None
                            ):
        """
        Given a bucket and key of a valid Lambda-zip, a function name and a handler, register that Lambda function.
        """
        if not vpc_config:
            vpc_config = {}
        if not dead_letter_config:
            dead_letter_config = {}
        if not self.credentials_arn:
            self.get_credentials_arn()
        if not environment_variables:
            environment_variables = {}
        if not aws_kms_key_arn:
            aws_kms_key_arn = ''

        response = self.lambda_client.create_function(
            FunctionName=function_name,
            Runtime=runtime,
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
            VpcConfig=vpc_config,
            DeadLetterConfig=dead_letter_config,
            Environment={'Variables': environment_variables},
            KMSKeyArn=aws_kms_key_arn
        )

        return response['FunctionArn']

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

    def update_lambda_configuration(    self,
                                        lambda_arn,
                                        function_name,
                                        handler,
                                        description='Zappa Deployment',
                                        timeout=30,
                                        memory_size=512,
                                        publish=True,
                                        vpc_config=None,
                                        runtime='python2.7',
                                        environment_variables=None,
                                        aws_kms_key_arn=None
                                    ):
        """
        Given an existing function ARN, update the configuration variables.
        """
        print("Updating Lambda function configuration..")

        if not vpc_config:
            vpc_config = {}
        if not self.credentials_arn:
            self.get_credentials_arn()
        if not environment_variables:
            environment_variables = {}
        if not aws_kms_key_arn:
            aws_kms_key_arn = ''

        response = self.lambda_client.update_function_configuration(
            FunctionName=function_name,
            Runtime=runtime,
            Role=self.credentials_arn,
            Handler=handler,
            Description=description,
            Timeout=timeout,
            MemorySize=memory_size,
            VpcConfig=vpc_config,
            Environment={'Variables': environment_variables},
            KMSKeyArn=aws_kms_key_arn
        )

        return response['FunctionArn']

    def invoke_lambda_function( self,
                                function_name,
                                payload,
                                invocation_type='Event',
                                log_type='Tail',
                                client_context=None,
                                qualifier=None
                            ):
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

        # Take into account $LATEST
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

        response = self.lambda_client.update_function_code(FunctionName=function_name, ZipFile=response.content, Publish=publish)  # pragma: no cover

        return response['FunctionArn']

    def get_lambda_function(self, function_name):
        """
        Returns the lambda function ARN, given a name

        This requires the "lambda:GetFunction" role.
        """
        response = self.lambda_client.get_function(
                FunctionName=function_name)
        return response['Configuration']['FunctionArn']

    def get_lambda_function_versions(self, function_name):
        """
        Simply returns the versions available for a Lambda function, given a function name.

        """
        try:
            response = self.lambda_client.list_versions_by_function(
                FunctionName=function_name
            )
            return response.get('Versions', [])
        except Exception:
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

    def create_api_gateway_routes(  self,
                                    lambda_arn,
                                    api_name=None,
                                    api_key_required=False,
                                    authorization_type='NONE',
                                    authorizer=None,
                                    cors_options=None,
                                    description=None
                                ):
        """
        Create the API Gateway for this Zappa deployment.

        Returns the new RestAPI CF resource.
        """

        restapi = troposphere.apigateway.RestApi('Api')
        restapi.Name = api_name or lambda_arn.split(':')[-1]
        if not description:
            description = 'Created automatically by Zappa.'
        restapi.Description = description
        self.cf_template.add_resource(restapi)

        root_id = troposphere.GetAtt(restapi, 'RootResourceId')
        invocations_uri = 'arn:aws:apigateway:' + self.boto_session.region_name + ':lambda:path/2015-03-31/functions/' + lambda_arn + '/invocations'

        ##
        # The Resources
        ##
        authorizer_resource = None
        if authorizer:
            authorizer_lambda_arn = authorizer.get('arn', lambda_arn)
            lambda_uri = 'arn:aws:apigateway:{region_name}:lambda:path/2015-03-31/functions/{lambda_arn}/invocations'.format(
                region_name=self.boto_session.region_name,
                lambda_arn=authorizer_lambda_arn
            )
            authorizer_resource = self.create_authorizer(
                restapi, lambda_uri, authorizer
            )

        self.create_and_setup_methods(  restapi,
                                        root_id,
                                        api_key_required,
                                        invocations_uri,
                                        authorization_type,
                                        authorizer_resource,
                                        0
                                        )

        if cors_options is not None:
            self.create_and_setup_cors( restapi,
                                        root_id,
                                        invocations_uri,
                                        0,
                                        cors_options
                                    )

        resource = troposphere.apigateway.Resource('ResourceAnyPathSlashed')
        self.cf_api_resources.append(resource.title)
        resource.RestApiId = troposphere.Ref(restapi)
        resource.ParentId = root_id
        resource.PathPart = "{proxy+}"
        self.cf_template.add_resource(resource)

        self.create_and_setup_methods(  restapi,
                                        resource,
                                        api_key_required,
                                        invocations_uri,
                                        authorization_type,
                                        authorizer_resource,
                                        1
                                    )  # pragma: no cover

        if cors_options is not None:
            self.create_and_setup_cors( restapi,
                                        resource,
                                        invocations_uri,
                                        1,
                                        cors_options
                                    )  # pragma: no cover
        return restapi

    def create_authorizer(self, restapi, uri, authorizer):
        """
        Create Authorizer for API gateway
        """
        authorizer_type = authorizer.get("type", "TOKEN").upper()
        identity_validation_expression = authorizer.get('validation_expression', None)

        authorizer_resource = troposphere.apigateway.Authorizer("Authorizer")
        authorizer_resource.RestApiId = troposphere.Ref(restapi)
        authorizer_resource.Name = authorizer.get("name", "ZappaAuthorizer")
        authorizer_resource.Type = authorizer_type
        authorizer_resource.AuthorizerUri = uri
        authorizer_resource.IdentitySource = "method.request.header.%s" % authorizer.get('token_header', 'Authorization')
        if identity_validation_expression:
            authorizer_resource.IdentityValidationExpression = identity_validation_expression

        if authorizer_type == 'TOKEN':
            if not self.credentials_arn:
                self.get_credentials_arn()
            authorizer_resource.AuthorizerResultTtlInSeconds = authorizer.get('result_ttl', 300)
            authorizer_resource.AuthorizerCredentials = self.credentials_arn
        if authorizer_type == 'COGNITO_USER_POOLS':
            authorizer_resource.ProviderARNs = authorizer.get('provider_arns')

        self.cf_api_resources.append(authorizer_resource.title)
        self.cf_template.add_resource(authorizer_resource)

        return authorizer_resource

    def create_and_setup_methods(
                                    self,
                                    restapi,
                                    resource,
                                    api_key_required,
                                    uri,
                                    authorization_type,
                                    authorizer_resource,
                                    depth
                                ):
        """
        Set up the methods, integration responses and method responses for a given API Gateway resource.
        """
        for method_name in self.http_methods:
            method = troposphere.apigateway.Method(method_name + str(depth))
            method.RestApiId = troposphere.Ref(restapi)
            if type(resource) is troposphere.apigateway.Resource:
                method.ResourceId = troposphere.Ref(resource)
            else:
                method.ResourceId = resource
            method.HttpMethod = method_name.upper()
            method.AuthorizationType = authorization_type
            if authorizer_resource:
                method.AuthorizerId = troposphere.Ref(authorizer_resource)
            method.ApiKeyRequired = api_key_required
            method.MethodResponses = []
            self.cf_template.add_resource(method)
            self.cf_api_resources.append(method.title)

            if not self.credentials_arn:
                self.get_credentials_arn()
            credentials = self.credentials_arn  # This must be a Role ARN

            integration = troposphere.apigateway.Integration()
            integration.CacheKeyParameters = []
            integration.CacheNamespace = 'none'
            integration.Credentials = credentials
            integration.IntegrationHttpMethod = 'POST'
            integration.IntegrationResponses = []
            integration.PassthroughBehavior = 'NEVER'
            integration.Type = 'AWS_PROXY'
            integration.Uri = uri
            method.Integration = integration

    def create_and_setup_cors(self, restapi, resource, uri, depth, config):
        """
        Set up the methods, integration responses and method responses for a given API Gateway resource.
        """
        if config is True:
            config = {}
        method_name = "OPTIONS"
        method = troposphere.apigateway.Method(method_name + str(depth))
        method.RestApiId = troposphere.Ref(restapi)
        if type(resource) is troposphere.apigateway.Resource:
            method.ResourceId = troposphere.Ref(resource)
        else:
            method.ResourceId = resource
        method.HttpMethod = method_name.upper()
        method.AuthorizationType = "NONE"
        method_response = troposphere.apigateway.MethodResponse()
        method_response.ResponseModels = {
            "application/json": "Empty"
        }
        response_headers = {
            "Access-Control-Allow-Headers": "'%s'" % ",".join(config.get(
                "allowed_headers", ["Content-Type", "X-Amz-Date",
                                    "Authorization", "X-Api-Key",
                                    "X-Amz-Security-Token"])),
            "Access-Control-Allow-Methods": "'%s'" % ",".join(config.get(
                "allowed_methods", ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"])),
            "Access-Control-Allow-Origin": "'%s'" % config.get(
                "allowed_origin", "*")
        }
        method_response.ResponseParameters = {
            "method.response.header.%s" % key: True for key in response_headers
        }
        method_response.StatusCode = "200"
        method.MethodResponses = [
            method_response
        ]
        self.cf_template.add_resource(method)
        self.cf_api_resources.append(method.title)

        integration = troposphere.apigateway.Integration()
        integration.Type = 'MOCK'
        integration.PassthroughBehavior = 'NEVER'
        integration.RequestTemplates = {
            "application/json": "{\"statusCode\": 200}"
        }
        integration_response = troposphere.apigateway.IntegrationResponse()
        integration_response.ResponseParameters = {
            "method.response.header.%s" % key: value for key, value in response_headers.items()
        }
        integration_response.ResponseTemplates = {
            "application/json": ""
        }
        integration_response.StatusCode = "200"
        integration.IntegrationResponses = [
            integration_response
        ]

        integration.Uri = uri
        method.Integration = integration

    def deploy_api_gateway( self,
                            api_id,
                            stage_name,
                            stage_description="",
                            description="",
                            cache_cluster_enabled=False,
                            cache_cluster_size='0.5',
                            variables=None,
                            cloudwatch_log_level='OFF',
                            cloudwatch_data_trace=False,
                            cloudwatch_metrics_enabled=False
                        ):
        """
        Deploy the API Gateway!

        Return the deployed API URL.
        """
        print("Deploying API Gateway..")

        self.apigateway_client.create_deployment(
            restApiId=api_id,
            stageName=stage_name,
            stageDescription=stage_description,
            description=description,
            cacheClusterEnabled=cache_cluster_enabled,
            cacheClusterSize=cache_cluster_size,
            variables=variables or {}
        )

        if cloudwatch_log_level not in self.cloudwatch_log_levels:
            cloudwatch_log_level = 'OFF'

        self.apigateway_client.update_stage(
            restApiId=api_id,
            stageName=stage_name,
            patchOperations=[
                self.get_patch_op('logging/loglevel', cloudwatch_log_level),
                self.get_patch_op('logging/dataTrace', cloudwatch_data_trace),
                self.get_patch_op('metrics/enabled', cloudwatch_metrics_enabled),
            ]
        )

        return "https://{}.execute-api.{}.amazonaws.com/{}".format(api_id, self.boto_session.region_name, stage_name)

    def add_binary_support(self, api_id):
            """
            Add binary support
            """
            response = self.apigateway_client.get_rest_api(
                restApiId=api_id
            )
            if "binaryMediaTypes" not in response or "*/*" not in response["binaryMediaTypes"]:
                self.apigateway_client.update_rest_api(
                    restApiId=api_id,
                    patchOperations=[
                        {
                            'op': "add",
                            'path': '/binaryMediaTypes/*~1*'
                        }
                    ]
                )

    def remove_binary_support(self, api_id):
        """
        Remove binary support
        """
        response = self.apigateway_client.get_rest_api(
            restApiId=api_id
        )
        if "binaryMediaTypes" in response and "*/*" in response["binaryMediaTypes"]:
            self.apigateway_client.update_rest_api(
                restApiId=api_id,
                patchOperations=[
                    {
                        'op': 'remove',
                        'path': '/binaryMediaTypes/*~1*'
                    }
                ]
            )

    def get_api_keys(self, api_id, stage_name):
        """
        Generator that allows to iterate per API keys associated to an api_id and a stage_name.
        """
        response = self.apigateway_client.get_api_keys(limit=500)
        stage_key = '{}/{}'.format(api_id, stage_name)
        for api_key in response.get('items'):
            if stage_key in api_key.get('stageKeys'):
                yield api_key.get('id')

    def create_api_key(self, api_id, stage_name):
        """
        Create new API key and link it with an api_id and a stage_name
        """
        response = self.apigateway_client.create_api_key(
            name='{}_{}'.format(stage_name, api_id),
            description='Api Key for {}'.format(api_id),
            enabled=True,
            stageKeys=[
                {
                    'restApiId': '{}'.format(api_id),
                    'stageName': '{}'.format(stage_name)
                },
            ]
        )
        print('Created a new x-api-key: {}'.format(response['id']))

    def remove_api_key(self, api_id, stage_name):
        """
        Remove a generated API key for api_id and stage_name
        """
        response = self.apigateway_client.get_api_keys(
            limit=1,
            nameQuery='{}_{}'.format(stage_name, api_id)
        )
        for api_key in response.get('items'):
            self.apigateway_client.delete_api_key(
                apiKey="{}".format(api_key['id'])
            )

    def add_api_stage_to_api_key(self, api_key, api_id, stage_name):
        """
        Add api stage to Api key
        """
        self.apigateway_client.update_api_key(
            apiKey=api_key,
            patchOperations=[
                {
                    'op': 'add',
                    'path': '/stages',
                    'value': '{}/{}'.format(api_id, stage_name)
                }
            ]
        )

    def get_patch_op(self, keypath, value, op='replace'):
        """
        Return an object that describes a change of configuration on the given staging.
        Setting will be applied on all available HTTP methods.
        """
        if isinstance(value, bool):
            value = str(value).lower()
        return {'op': op, 'path': '/*/*/{}'.format(keypath), 'value': value}

    def get_rest_apis(self, project_name):
        """
        Generator that allows to iterate per every available apis.
        """
        all_apis = self.apigateway_client.get_rest_apis(
            limit=500
        )

        for api in all_apis['items']:
            if api['name'] != project_name:
                continue
            yield api

    def undeploy_api_gateway(self, lambda_name, domain_name=None):
        """
        Delete a deployed REST API Gateway.
        """
        print("Deleting API Gateway..")

        api_id = self.get_api_id(lambda_name)

        if domain_name:

            # XXX - Remove Route53 smartly here?
            # XXX - This doesn't raise, but doesn't work either.

            try:
                self.apigateway_client.delete_base_path_mapping(
                    domainName=domain_name,
                    basePath='(none)'
                )
            except Exception as e:
                # We may not have actually set up the domain.
                pass

        was_deleted = self.delete_stack(lambda_name, wait=True)

        if not was_deleted:
            # try erasing it with the older method
            for api in self.get_rest_apis(lambda_name):
                self.apigateway_client.delete_rest_api(
                    restApiId=api['id']
                )

    def update_stage_config(    self,
                                project_name,
                                stage_name,
                                cloudwatch_log_level,
                                cloudwatch_data_trace,
                                cloudwatch_metrics_enabled
                            ):
        """
        Update CloudWatch metrics configuration.
        """
        if cloudwatch_log_level not in self.cloudwatch_log_levels:
            cloudwatch_log_level = 'OFF'

        for api in self.get_rest_apis(project_name):
            self.apigateway_client.update_stage(
                restApiId=api['id'],
                stageName=stage_name,
                patchOperations=[
                    self.get_patch_op('logging/loglevel', cloudwatch_log_level),
                    self.get_patch_op('logging/dataTrace', cloudwatch_data_trace),
                    self.get_patch_op('metrics/enabled', cloudwatch_metrics_enabled),
                ]
            )

    def delete_stack(self, name, wait=False):
        """
        Delete the CF stack managed by Zappa.
        """
        try:
            stack = self.cf_client.describe_stacks(StackName=name)['Stacks'][0]
        except: # pragma: no cover
            print('No Zappa stack named {0}'.format(name))
            return False

        tags = {x['Key']:x['Value'] for x in stack['Tags']}
        if tags.get('ZappaProject') == name:
            self.cf_client.delete_stack(StackName=name)
            if wait:
                waiter = self.cf_client.get_waiter('stack_delete_complete')
                print('Waiting for stack {0} to be deleted..'.format(name))
                waiter.wait(StackName=name)
            return True
        else:
            print('ZappaProject tag not found on {0}, doing nothing'.format(name))
            return False

    def create_stack_template(  self,
                                lambda_arn,
                                lambda_name,
                                api_key_required,
                                iam_authorization,
                                authorizer,
                                cors_options=None,
                                description=None
                            ):
        """
        Build the entire CF stack.
        Just used for the API Gateway, but could be expanded in the future.
        """

        auth_type = "NONE"
        if iam_authorization and authorizer:
            logger.warn("Both IAM Authorization and Authorizer are specified, this is not possible. "
                        "Setting Auth method to IAM Authorization")
            authorizer = None
            auth_type = "AWS_IAM"
        elif iam_authorization:
            auth_type = "AWS_IAM"
        elif authorizer:
            auth_type = authorizer.get("type", "CUSTOM")

        # build a fresh template
        self.cf_template = troposphere.Template()
        self.cf_template.add_description('Automatically generated with Zappa')
        self.cf_api_resources = []
        self.cf_parameters = {}

        restapi = self.create_api_gateway_routes(
                                            lambda_arn,
                                            api_name=lambda_name,
                                            api_key_required=api_key_required,
                                            authorization_type=auth_type,
                                            authorizer=authorizer,
                                            cors_options=cors_options,
                                            description=description
                                        )
        return self.cf_template

    def update_stack(self, name, working_bucket, wait=False, update_only=False):
        """
        Update or create the CF stack managed by Zappa.
        """
        capabilities = []

        template = name + '-template-' + str(int(time.time())) + '.json'
        with open(template, 'wb') as out:
            out.write(bytes(self.cf_template.to_json(indent=None, separators=(',',':')), "utf-8"))

        self.upload_to_s3(template, working_bucket)

        url = 'https://s3.amazonaws.com/{0}/{1}'.format(working_bucket, template)
        tags = [{'Key':'ZappaProject','Value':name}]
        update = True

        try:
            self.cf_client.describe_stacks(StackName=name)
        except botocore.client.ClientError:
            update = False

        if update_only and not update:
            print('CloudFormation stack missing, re-deploy to enable updates')
            return

        if not update:
            self.cf_client.create_stack(StackName=name,
                                        Capabilities=capabilities,
                                        TemplateURL=url,
                                        Tags=tags)
            print('Waiting for stack {0} to create (this can take a bit)..'.format(name))
        else:
            try:
                self.cf_client.update_stack(StackName=name,
                                            Capabilities=capabilities,
                                            TemplateURL=url,
                                            Tags=tags)
                print('Waiting for stack {0} to update..'.format(name))
            except botocore.client.ClientError as e:
                if e.response['Error']['Message'] == 'No updates are to be performed.':
                    wait = False
                else:
                    raise

        if wait:
            total_resources = len(self.cf_template.resources)
            current_resources = 0
            sr = self.cf_client.get_paginator('list_stack_resources')
            progress = tqdm(total=total_resources, unit='res')
            while True:
                time.sleep(3)
                result = self.cf_client.describe_stacks(StackName=name)
                if not result['Stacks']:
                    continue  # might need to wait a bit

                if result['Stacks'][0]['StackStatus'] in ['CREATE_COMPLETE', 'UPDATE_COMPLETE']:
                    break

                # Something has gone wrong.
                # Is raising enough? Should we also remove the Lambda function?
                if result['Stacks'][0]['StackStatus'] in [
                                                            'DELETE_COMPLETE',
                                                            'DELETE_IN_PROGRESS',
                                                            'ROLLBACK_IN_PROGRESS',
                                                            'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS',
                                                            'UPDATE_ROLLBACK_COMPLETE'
                                                        ]:
                    raise EnvironmentError("Stack creation failed. "
                                           "Please check your CloudFormation console. "
                                           "You may also need to `undeploy`.")

                count = 0
                for result in sr.paginate(StackName=name):
                    done = (1 for x in result['StackResourceSummaries']
                            if 'COMPLETE' in x['ResourceStatus'])
                    count += sum(done)
                if count:
                    # We can end up in a situation where we have more resources being created
                    # than anticipated.
                    if (count - current_resources) > 0:
                        progress.update(count - current_resources)
                current_resources = count
            progress.close()

        try:
            os.remove(template)
        except OSError:
            pass

        self.remove_from_s3(template, working_bucket)

    def stack_outputs(self, name):
        """
        Given a name, describes CloudFront stacks and returns dict of the stack Outputs
        , else returns an empty dict.
        """
        try:
            stack = self.cf_client.describe_stacks(StackName=name)['Stacks'][0]
            return {x['OutputKey']: x['OutputValue'] for x in stack['Outputs']}
        except botocore.client.ClientError:
            return {}


    def get_api_url(self, lambda_name, stage_name):
        """
        Given a lambda_name and stage_name, return a valid API URL.
        """
        api_id = self.get_api_id(lambda_name)
        if api_id:
            return "https://{}.execute-api.{}.amazonaws.com/{}".format(api_id, self.boto_session.region_name, stage_name)
        else:
            return None

    def get_api_id(self, lambda_name):
        """
        Given a lambda_name, return the API id.
        """
        try:
            response = self.cf_client.describe_stack_resource(StackName=lambda_name,
                                                              LogicalResourceId='Api')
            return response['StackResourceDetail'].get('PhysicalResourceId', None)
        except: # pragma: no cover
            try:
                # Try the old method (project was probably made on an older, non CF version)
                response = self.apigateway_client.get_rest_apis(limit=500)

                for item in response['items']:
                    if item['name'] == lambda_name:
                        return item['id']

                logger.exception('Could not get API ID.')
                return None
            except: # pragma: no cover
                # We don't even have an API deployed. That's okay!
                return None

    def create_domain_name(self,
                           domain_name,
                           certificate_name,
                           certificate_body=None,
                           certificate_private_key=None,
                           certificate_chain=None,
                           certificate_arn=None,
                           lambda_name=None,
                           stage=None):
        """
        Creates the API GW domain and returns the resulting DNS name.
        """

        # This is a Let's Encrypt or custom certificate
        if not certificate_arn:
            agw_response = self.apigateway_client.create_domain_name(
                domainName=domain_name,
                certificateName=certificate_name,
                certificateBody=certificate_body,
                certificatePrivateKey=certificate_private_key,
                certificateChain=certificate_chain
            )
        # This is an AWS ACM-hosted Certificate
        else:
            agw_response = self.apigateway_client.create_domain_name(
                domainName=domain_name,
                certificateName=certificate_name,
                certificateArn=certificate_arn
            )

        api_id = self.get_api_id(lambda_name)
        if not api_id:
            raise LookupError("No API URL to certify found - did you deploy?")

        self.apigateway_client.create_base_path_mapping(
            domainName=domain_name,
            basePath='',
            restApiId=api_id,
            stage=stage
        )

        return agw_response['distributionDomainName']

    def update_route53_records(self, domain_name, dns_name):
        """
        Updates Route53 Records following GW domain creation
        """
        zone_id = self.get_hosted_zone_id_for_domain(domain_name)

        is_apex = self.route53.get_hosted_zone(Id=zone_id)['HostedZone']['Name'][:-1] == domain_name
        if is_apex:
            record_set = {
                'Name': domain_name,
                'Type': 'A',
                'AliasTarget': {
                    'HostedZoneId': 'Z2FDTNDATAQYW2', # This is a magic value that means "CloudFront"
                    'DNSName': dns_name,
                    'EvaluateTargetHealth': False
                }
            }
        else:
            record_set = {
                'Name': domain_name,
                'Type': 'CNAME',
                'ResourceRecords': [
                    {
                        'Value': dns_name
                    }
                ],
                'TTL': 60
            }

        # Related: https://github.com/boto/boto3/issues/157
        # and: http://docs.aws.amazon.com/Route53/latest/APIReference/CreateAliasRRSAPI.html
        # and policy: https://spin.atomicobject.com/2016/04/28/route-53-hosted-zone-managment/
        # pure_zone_id = zone_id.split('/hostedzone/')[1]

        # XXX: ClientError: An error occurred (InvalidChangeBatch) when calling the ChangeResourceRecordSets operation:
        # Tried to create an alias that targets d1awfeji80d0k2.cloudfront.net., type A in zone Z1XWOQP59BYF6Z,
        # but the alias target name does not lie within the target zone
        response = self.route53.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                'Changes': [
                    {
                        'Action': 'UPSERT',
                        'ResourceRecordSet': record_set
                    }
                ]
            }
        )

        return response

    def update_domain_name(self,
                           domain_name,
                           certificate_name=None,
                           certificate_body=None,
                           certificate_private_key=None,
                           certificate_chain=None,
                           certificate_arn=None,
                           lambda_name=None,
                           stage=None,
                           route53=True):
        """
        This updates your certificate information for an existing domain,
        with similar arguments to boto's update_domain_name API Gateway api.

        It returns the resulting new domain information including the new certificate's ARN
        if created during this process.

        Previously, this method involved downtime that could take up to 40 minutes
        because the API Gateway api only allowed this by deleting, and then creating it.

        Related issues:     https://github.com/Miserlou/Zappa/issues/590
                            https://github.com/Miserlou/Zappa/issues/588
                            https://github.com/Miserlou/Zappa/pull/458
                            https://github.com/Miserlou/Zappa/issues/882
                            https://github.com/Miserlou/Zappa/pull/883
        """

        print("Updating domain name!")

        certificate_name = certificate_name + str(time.time())

        api_gateway_domain = self.apigateway_client.get_domain_name(domainName=domain_name)
        if not certificate_arn\
           and certificate_body and certificate_private_key and certificate_chain:
            acm_certificate = self.acm_client.import_certificate(Certificate=certificate_body,
                                                                 PrivateKey=certificate_private_key,
                                                                 CertificateChain=certificate_chain)
            certificate_arn = acm_certificate['CertificateArn']

        return self.apigateway_client.update_domain_name(domainName=domain_name,
                                                         patchOperations=[
                                                             {"op" : "replace",
                                                              "path" : "/certificateName",
                                                              "value" : certificate_name},
                                                             {"op" : "replace",
                                                              "path" : "/certificateArn",
                                                              "value" : certificate_arn}
                                                         ])

    def get_domain_name(self, domain_name):
        """
        Scan our hosted zones for the record of a given name.

        Returns the record entry, else None.

        """
        # Make sure api gateway domain is present
        try:
            self.apigateway_client.get_domain_name(domainName=domain_name)
        except Exception:
            return None

        try:
            zones = self.route53.list_hosted_zones()
            for zone in zones['HostedZones']:
                records = self.route53.list_resource_record_sets(HostedZoneId=zone['Id'])
                for record in records['ResourceRecordSets']:
                    if record['Type'] in ('CNAME', 'A') and record['Name'][:-1] == domain_name:
                        return record

        except Exception as e:
            return None

        ##
        # Old, automatic logic.
        # If re-introduced, should be moved to a new function.
        # Related ticket: https://github.com/Miserlou/Zappa/pull/458
        ##

        # We may be in a position where Route53 doesn't have a domain, but the API Gateway does.
        # We need to delete this before we can create the new Route53.
        # try:
        #     api_gateway_domain = self.apigateway_client.get_domain_name(domainName=domain_name)
        #     self.apigateway_client.delete_domain_name(domainName=domain_name)
        # except Exception:
        #     pass

        return None

    ##
    # IAM
    ##

    def get_credentials_arn(self):
        """
        Given our role name, get and set the credentials_arn.

        """
        role = self.iam.Role(self.role_name)
        self.credentials_arn = role.arn
        return role, self.credentials_arn

    def create_iam_roles(self):
        """
        Create and defines the IAM roles and policies necessary for Zappa.

        If the IAM role already exists, it will be updated if necessary.
        """
        attach_policy_obj = json.loads(self.attach_policy)
        assume_policy_obj = json.loads(self.assume_policy)

        if self.extra_permissions:
            for permission in self.extra_permissions:
                attach_policy_obj['Statement'].append(dict(permission))
            self.attach_policy = json.dumps(attach_policy_obj)

        updated = False

        # Create the role if needed
        try:
            role, credentials_arn = self.get_credentials_arn()

        except botocore.client.ClientError:
            print("Creating " + self.role_name + " IAM Role..")

            role = self.iam.create_role(
                RoleName=self.role_name,
                AssumeRolePolicyDocument=self.assume_policy
            )
            self.credentials_arn = role.arn
            updated = True

        # create or update the role's policies if needed
        policy = self.iam.RolePolicy(self.role_name, 'zappa-permissions')
        try:
            if policy.policy_document != attach_policy_obj:
                print("Updating zappa-permissions policy on " + self.role_name + " IAM Role.")

                policy.put(PolicyDocument=self.attach_policy)
                updated = True

        except botocore.client.ClientError:
            print("Creating zappa-permissions policy on " + self.role_name + " IAM Role.")
            policy.put(PolicyDocument=self.attach_policy)
            updated = True

        if role.assume_role_policy_document != assume_policy_obj and \
                set(role.assume_role_policy_document['Statement'][0]['Principal']['Service']) != set(assume_policy_obj['Statement'][0]['Principal']['Service']):
            print("Updating assume role policy on " + self.role_name + " IAM Role.")
            self.iam_client.update_assume_role_policy(
                RoleName=self.role_name,
                PolicyDocument=self.assume_policy
            )
            updated = True

        return self.credentials_arn, updated

    def _clear_policy(self, lambda_name):
        """
        Remove obsolete policy statements to prevent policy from bloating over the limit after repeated updates.
        """
        try:
            policy_response = self.lambda_client.get_policy(
                FunctionName=lambda_name
            )
            if policy_response['ResponseMetadata']['HTTPStatusCode'] == 200:
                statement = json.loads(policy_response['Policy'])['Statement']
                for s in statement:
                    delete_response = self.lambda_client.remove_permission(
                        FunctionName=lambda_name,
                        StatementId=s['Sid']
                    )
                    if delete_response['ResponseMetadata']['HTTPStatusCode'] != 204:
                        logger.error('Failed to delete an obsolete policy statement: {}'.format())
            else:
                logger.debug('Failed to load Lambda function policy: {}'.format(policy_response))
        except ClientError as e:
            if e.args[0].find('ResourceNotFoundException') > -1:
                logger.debug('No policy found, must be first run.')
            else:
                logger.error('Unexpected client error {}'.format(e.args[0]))

    ##
    # CloudWatch Events
    ##

    def create_event_permission(self, lambda_name, principal, source_arn):
        """
        Create permissions to link to an event.

        Related: http://docs.aws.amazon.com/lambda/latest/dg/with-s3-example-configure-event-source.html
        """
        logger.debug('Adding new permission to invoke Lambda function: {}'.format(lambda_name))
        permission_response = self.lambda_client.add_permission(
            FunctionName=lambda_name,
            StatementId=''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8)),
            Action='lambda:InvokeFunction',
            Principal=principal,
            SourceArn=source_arn,
        )

        if permission_response['ResponseMetadata']['HTTPStatusCode'] != 201:
            print('Problem creating permission to invoke Lambda function')
            return None  # XXX: Raise?

        return permission_response

    def schedule_events(self, lambda_arn, lambda_name, events, default=True):
        """
        Given a Lambda ARN, name and a list of events, schedule this as CloudWatch Events.

        'events' is a list of dictionaries, where the dict must contains the string
        of a 'function' and the string of the event 'expression', and an optional 'name' and 'description'.

        Expressions can be in rate or cron format:
            http://docs.aws.amazon.com/lambda/latest/dg/tutorial-scheduled-events-schedule-expressions.html
        """

        # The two stream sources - DynamoDB and Kinesis - are working differently than the other services (pull vs push)
        # and do not require event permissions. They do require additional permissions on the Lambda roles though.
        # http://docs.aws.amazon.com/lambda/latest/dg/lambda-api-permissions-ref.html
        pull_services = ['dynamodb', 'kinesis']

        # XXX: Not available in Lambda yet.
        # We probably want to execute the latest code.
        # if default:
        #     lambda_arn = lambda_arn + ":$LATEST"

        self.unschedule_events(lambda_name=lambda_name, lambda_arn=lambda_arn, events=events,
                               excluded_source_services=pull_services)
        for event in events:
            function = event['function']
            expression = event.get('expression', None) # single expression
            expressions = event.get('expressions', None) # multiple expression
            event_source = event.get('event_source', None)
            name = self.get_scheduled_event_name(event, function, lambda_name)
            description = event.get('description', function)

            #   - If 'cron' or 'rate' in expression, use ScheduleExpression
            #   - Else, use EventPattern
            #       - ex https://github.com/awslabs/aws-lambda-ddns-function

            if not self.credentials_arn:
                self.get_credentials_arn()

            if expression:
                expressions = [expression] # same code for single and multiple expression

            if expressions:
                for expression in expressions:
                    rule_response = self.events_client.put_rule(
                        Name=name,
                        ScheduleExpression=expression,
                        State='ENABLED',
                        Description=description,
                        RoleArn=self.credentials_arn
                    )

                    if 'RuleArn' in rule_response:
                        logger.debug('Rule created. ARN {}'.format(rule_response['RuleArn']))

                    # Specific permissions are necessary for any trigger to work.
                    self.create_event_permission(lambda_name, 'events.amazonaws.com', rule_response['RuleArn'])

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
                        print("Scheduled {} with expression {}!".format(name, expression))
                    else:
                        print("Problem scheduling {} with expression {}.".format(name, expression))

            elif event_source:
                service = self.service_from_arn(event_source['arn'])

                if service not in pull_services:
                    svc = ','.join(event['event_source']['events'])
                    self.create_event_permission(
                        lambda_name,
                        service + '.amazonaws.com',
                        event['event_source']['arn']
                    )
                else:
                    svc = service

                rule_response = add_event_source(
                    event_source,
                    lambda_arn,
                    function,
                    self.boto_session
                )

                if rule_response == 'successful':
                    print("Created {} event schedule for {}!".format(svc, function))
                elif rule_response == 'failed':
                    print("Problem creating {} event schedule for {}!".format(svc, function))
                elif rule_response == 'exists':
                    print("{} event schedule for {} already exists - Nothing to do here.".format(svc, function))
                elif rule_response == 'dryrun':
                    print("Dryrun for creating {} event schedule for {}!!".format(svc, function))
            else:
                print("Could not create event {} - Please define either an expression or an event source".format(name))


    @staticmethod
    def get_scheduled_event_name(event, function, lambda_name):
        name = event.get('name', function)
        if name != function:
            # a custom event name has been provided, make sure function name is included as postfix,
            # otherwise zappa's handler won't be able to locate the function.
            name = '{}-{}'.format(name, function)
        # prefix scheduled event names with lambda name. So we can look them up later via the prefix.
        return Zappa.get_event_name(lambda_name, name)

    @staticmethod
    def get_event_name(lambda_name, name):
        """
        Returns an AWS-valid Lambda event name.

        """
        return '{prefix:.{width}}-{postfix}'.format(prefix=lambda_name, width=max(0, 63 - len(name)), postfix=name)[:64]

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
            # This avoids misbehavior if low permissions, related: https://github.com/Miserlou/Zappa/issues/286
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDeniedException':
                raise
            else:
                logger.debug('No target found for this rule: {} {}'.format(rule_name, e.args[0]))
                return

        if 'Targets' in targets and targets['Targets']:
            self.events_client.remove_targets(Rule=rule_name, Ids=[x['Id'] for x in targets['Targets']])
        else:  # pragma: no cover
            logger.debug('No target to delete')

        # Delete our rule.
        self.events_client.delete_rule(Name=rule_name)

    def get_event_rule_names_for_lambda(self, lambda_arn):
        """
        Get all of the rule names associated with a lambda function.
        """
        response = self.events_client.list_rule_names_by_target(TargetArn=lambda_arn)
        rule_names = response['RuleNames']
        # Iterate when the results are paginated
        while 'NextToken' in response:
            response = self.events_client.list_rule_names_by_target(TargetArn=lambda_arn,
                                                                    NextToken=response['NextToken'])
            rule_names.extend(response['RuleNames'])
        return rule_names

    def get_event_rules_for_lambda(self, lambda_arn):
        """
        Get all of the rule details associated with this function.
        """
        rule_names = self.get_event_rule_names_for_lambda(lambda_arn=lambda_arn)
        return [self.events_client.describe_rule(Name=r) for r in rule_names]

    def unschedule_events(self, events, lambda_arn=None, lambda_name=None, excluded_source_services=None):
        excluded_source_services = excluded_source_services or []
        """
        Given a list of events, unschedule these CloudWatch Events.

        'events' is a list of dictionaries, where the dict must contains the string
        of a 'function' and the string of the event 'expression', and an optional 'name' and 'description'.
        """
        self._clear_policy(lambda_name)

        rule_names = self.get_event_rule_names_for_lambda(lambda_arn=lambda_arn)
        for rule_name in rule_names:
            self.delete_rule(rule_name)
            print('Unscheduled ' + rule_name + '.')

        non_cwe = [e for e in events if 'event_source' in e]
        for event in non_cwe:
            # TODO: This WILL miss non CW events that have been deployed but changed names. Figure out a way to remove
            # them no matter what.
            # These are non CWE event sources.
            function = event['function']
            name = event.get('name', function)
            event_source = event.get('event_source', function)
            service = self.service_from_arn(event_source['arn'])
            # DynamoDB and Kinesis streams take quite a while to setup after they are created and do not need to be
            # re-scheduled when a new Lambda function is deployed. Therefore, they should not be removed during zappa
            # update or zappa schedule.
            if service not in excluded_source_services:
                remove_event_source(
                    event_source,
                    lambda_arn,
                    function,
                    self.boto_session
                )
                print("Removed event " + name + " (" + str(event_source['events']) + ").")

    ###
    # Async / SNS
    ##

    def create_async_sns_topic(self, lambda_name, lambda_arn):
        """
        Create the SNS-based async topic.
        """
        topic_name = get_topic_name(lambda_name)
        # Create SNS topic
        topic_arn = self.sns_client.create_topic(
            Name=topic_name)['TopicArn']
        # Create subscription
        self.sns_client.subscribe(
            TopicArn=topic_arn,
            Protocol='lambda',
            Endpoint=lambda_arn
        )
        # Add Lambda permission for SNS to invoke function
        self.create_event_permission(
            lambda_name=lambda_name,
            principal='sns.amazonaws.com',
            source_arn=topic_arn
        )
        # Add rule for SNS topic as a event source
        add_event_source(
            event_source={
                "arn": topic_arn,
                "events": ["sns:Publish"]
            },
            lambda_arn=lambda_arn,
            target_function="zappa.async.route_task",
            boto_session=self.boto_session
        )
        return topic_arn

    def remove_async_sns_topic(self, lambda_name):
        """
        Remove the async SNS topic.
        """
        topic_name = get_topic_name(lambda_name)
        removed_arns = []
        for sub in self.sns_client.list_subscriptions()['Subscriptions']:
            if topic_name in sub['TopicArn']:
                self.sns_client.delete_topic(TopicArn=sub['TopicArn'])
                removed_arns.append(sub['TopicArn'])
        return removed_arns

    ##
    # CloudWatch Logging
    ##

    def fetch_logs(self, lambda_name, filter_pattern='', limit=10000, start_time=0):
        """
        Fetch the CloudWatch logs for a given Lambda name.
        """
        log_name = '/aws/lambda/' + lambda_name
        streams = self.logs_client.describe_log_streams(
            logGroupName=log_name,
            descending=True,
            orderBy='LastEventTime'
        )

        all_streams = streams['logStreams']
        all_names = [stream['logStreamName'] for stream in all_streams]

        events = []
        response = {}
        while not response or 'nextToken' in response:
            extra_args = {}
            if 'nextToken' in response:
                extra_args['nextToken'] = response['nextToken']

            # Amazon uses millisecond epoch for some reason.
            # Thanks, Jeff.
            start_time = start_time * 1000
            end_time = int(time.time()) * 1000

            response = self.logs_client.filter_log_events(
                logGroupName=log_name,
                logStreamNames=all_names,
                startTime=start_time,
                endTime=end_time,
                filterPattern=filter_pattern,
                limit=limit,
                interleaved=True, # Does this actually improve performance?
                **extra_args
            )
            if response and 'events' in response:
                events += response['events']

        return sorted(events, key=lambda k: k['timestamp'])

    def remove_log_group(self, group_name):
        """
        Filter all log groups that match the name given in log_filter.
        """
        print("Removing log group: {}".format(group_name))
        try:
            self.logs_client.delete_log_group(logGroupName=group_name)
        except botocore.exceptions.ClientError as e:
            print("Couldn't remove '{}' because of: {}".format(group_name, e))

    def remove_lambda_function_logs(self, lambda_function_name):
        """
        Remove all logs that are assigned to a given lambda function id.
        """
        self.remove_log_group('/aws/lambda/{}'.format(lambda_function_name))

    def remove_api_gateway_logs(self, project_name):
        """
        Removed all logs that are assigned to a given rest api id.
        """
        for rest_api in self.get_rest_apis(project_name):
            for stage in self.apigateway_client.get_stages(restApiId=rest_api['id'])['item']:
                self.remove_log_group('API-Gateway-Execution-Logs_{}/{}'.format(rest_api['id'], stage['stageName']))

    ##
    # Route53 Domain Name Entries
    ##

    def get_hosted_zone_id_for_domain(self, domain):
        """
        Get the Hosted Zone ID for a given domain.

        """
        all_zones = self.route53.list_hosted_zones()
        return self.get_best_match_zone(all_zones, domain)

    @staticmethod
    def get_best_match_zone(all_zones, domain):
        """Return zone id which name is closer matched with domain name."""

        # Related: https://github.com/Miserlou/Zappa/issues/459
        public_zones = [zone for zone in all_zones['HostedZones'] if not zone['Config']['PrivateZone']]

        zones = {zone['Name'][:-1]: zone['Id'] for zone in public_zones if zone['Name'][:-1] in domain}
        if zones:
            keys = max(zones.keys(), key=lambda a: len(a))  # get longest key -- best match.
            return zones[keys]
        else:
            return None

    def set_dns_challenge_txt(self, zone_id, domain, txt_challenge):
        """
        Set DNS challenge TXT.
        """
        print("Setting DNS challenge..")
        resp = self.route53.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch=self.get_dns_challenge_change_batch('UPSERT', domain, txt_challenge)
        )

        return resp

    def remove_dns_challenge_txt(self, zone_id, domain, txt_challenge):
        """
        Remove DNS challenge TXT.
        """
        print("Deleting DNS challenge..")
        resp = self.route53.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch=self.get_dns_challenge_change_batch('DELETE', domain, txt_challenge)
        )

        return resp

    @staticmethod
    def get_dns_challenge_change_batch(action, domain, txt_challenge):
        """
        Given action, domain and challege, return a change batch to use with
        route53 call.

        :param action: DELETE | UPSERT
        :param domain: domain name
        :param txt_challenge: challenge
        :return: change set for a given action, domain and TXT challenge.
        """
        return {
            'Changes': [{
                'Action': action,
                'ResourceRecordSet': {
                    'Name': '_acme-challenge.{0}'.format(domain),
                    'Type': 'TXT',
                    'TTL': 60,
                    'ResourceRecords': [{
                        'Value': '"{0}"'.format(txt_challenge)
                    }]
                }
            }]
        }

    ##
    # Utility
    ##

    def shell(self):
        """
        Spawn a PDB shell.
        """
        import pdb
        pdb.set_trace()

    def load_credentials(self, boto_session=None, profile_name=None):
        """
        Load AWS credentials.

        An optional boto_session can be provided, but that's usually for testing.

        An optional profile_name can be provided for config files that have multiple sets
        of credentials.
        """
        # Automatically load credentials from config or environment
        if not boto_session:

            # If provided, use the supplied profile name.
            if profile_name:
                self.boto_session = boto3.Session(profile_name=profile_name, region_name=self.aws_region)
            elif os.environ.get('AWS_ACCESS_KEY_ID') and os.environ.get('AWS_SECRET_ACCESS_KEY'):
                region_name = os.environ.get('AWS_DEFAULT_REGION') or self.aws_region
                session_kw = {
                    "aws_access_key_id": os.environ.get('AWS_ACCESS_KEY_ID'),
                    "aws_secret_access_key": os.environ.get('AWS_SECRET_ACCESS_KEY'),
                    "region_name": region_name,
                }

                # If we're executing in a role, AWS_SESSION_TOKEN will be present, too.
                if os.environ.get("AWS_SESSION_TOKEN"):
                    session_kw["aws_session_token"] = os.environ.get("AWS_SESSION_TOKEN")

                self.boto_session = boto3.Session(**session_kw)
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
    def service_from_arn(arn):
        return arn.split(':')[2]
