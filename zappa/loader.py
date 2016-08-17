#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Zappa CLI

Deploy arbitrary Python programs as serverless Zappa applications.

"""

from __future__ import division
from __future__ import unicode_literals

import imp
import importlib
import inspect
import os
import tempfile
import zipfile

import requests
import slugify
from click import UsageError

from zappa import Zappa
from .settings import Settings, SETTINGS_DEFAULT

DEFAULT_SETTINGS_FILE = 'zappa_settings.json'

CUSTOM_SETTINGS = [
    'assume_policy',
    'attach_policy',
    'aws_region',
    'delete_zip',
    'exclude',
    'http_methods',
    'integration_response_codes',
    'method_header_types',
    'method_response_codes',
    'parameter_depth',
    'role_name',
    'touch',
]


class ZappaLoader(object):
    """
    ZappaLoader object is responsible for executing the calls to the core library.

    """

    zappa = None
    settings = None
    settings_filename = None

    def __init__(self, settings, api_stage=None, app_function=None):
        # save off the settings filename before getting api_stage specific settings
        self.settings_filename = settings._settings_filename

        self.get_stage_settings(api_stage, settings)

        if app_function:
            self.settings.app_function = app_function

        # We need a working title for this project. Use one if supplied, else cwd dirname.
        if not self.settings.project_name:
            self.settings.project_name = slugify.slugify(self.project_dir().split(os.sep)[-1])

        # The name of the actual AWS Lambda function, ex, 'helloworld-dev'
        # Django's slugify doesn't replace _, but this does.
        self.settings.lambda_name = slugify.slugify(self.settings.project_name + '-' + self.settings.api_stage)

        # # TODO: pass along the settings object to zappa
        self.zappa = Zappa(
            boto_session=None,
            profile_name=self.settings.profile_name,
            aws_region=self.settings.aws_region)

        for setting in CUSTOM_SETTINGS:
            if setting in self.settings and self.settings[setting]:
                setting_val = self.settings[setting]
                # Read the policy file contents.
                if setting.endswith('policy'):
                    with open(setting_val, 'r') as f:
                        setting_val = f.read()
                setattr(self.zappa, setting, setting_val)

    def get_stage_settings(self, api_stage, all_settings):
        """
        Return the settings for a specific api stage.  If this was already created, it will just return it.
        This also sets self.settings on this instance.

        :param api_stage: The string representing the stage (i.e. 'dev')
        :param all_settings: The settings from the loaded settings file.
        :return: Settings for the specific stage.
        """
        if self.settings is not None:
            return self.settings

        self.settings = Settings(SETTINGS_DEFAULT)

        if api_stage is not None:
            if api_stage in all_settings:
                self.settings.deep_update(all_settings[api_stage])
                self.settings.api_stage = api_stage
            else:
                raise UsageError(
                    "API stage is not in settings file: {}.".format(api_stage))
        else:
            keys = all_settings.keys()
            for key in keys:
                if key.startswith("_"):
                    keys.remove(key)
            if len(keys) is 1:
                # if there's only one environment defined in the settings,
                # use that as the default.
                api_stage = keys[0]
                self.settings.deep_update(all_settings[api_stage])
                self.settings.api_stage = api_stage
            else:
                raise UsageError(
                    "Please supply an environment to interact with.")
        return self.settings

    def project_dir(self):
        settings_dir = os.path.dirname(self.settings_filename)
        return os.path.join(os.getcwd(), settings_dir).rstrip(os.sep)

    def callback(self, position):
        """
        Allows the execution of custom code between creation of the zip file and deployment to AWS.

        :return: None
        """
        callbacks = self.settings.get('callbacks', {})
        callback = callbacks.get(position)

        if callback:
            (mod_name, cb_func) = callback.rsplit('.', 1)

            module_ = importlib.import_module(mod_name)
            getattr(module_, cb_func)(self)  # Call the function passing self

    def pre_deploy(self):
        # Execute the prebuilt script
        if self.settings.prebuild_script:
            self.execute_prebuild_script()

    def post_deploy(self):
        # Finally, delete the local copy our zip package
        self.remove_uploaded_zip()

    def create_package(self, app_function=None):
        """
        Ensure that the package can be properly configured,
        and then create it.

        """
        # Make sure the necessary IAM execution roles are available
        if self.settings.manage_roles:
            self.zappa.create_iam_roles()

        # allow an override of the app function
        if app_function:
            self.settings.app_function = app_function

        # Create the Lambda zip package (includes project and virtual environment)
        # Also define the path the handler file so it can be copied to the zip
        # root for Lambda.
        current_file = os.path.dirname(os.path.abspath(
            inspect.getfile(inspect.currentframe())))
        handler_file = os.sep.join(current_file.split(os.sep)[0:]) + os.sep + 'handler.py'

        # Create the zip file
        self.settings.zip_path = self.zappa.create_lambda_zip(
            self.settings.lambda_name,
            handler_file=handler_file,
            use_precompiled_packages=self.settings.get('use_precompiled_packages', True),
            exclude=self.settings.get('exclude', [])
        )

        if self.settings.app_function or self.settings.django_settings:
            # Throw custom setings into the zip file
            with zipfile.ZipFile(self.settings.zip_path, 'a') as lambda_zip:

                settings_s = "# Generated by Zappa\n"

                if self.settings.app_function:
                    app_module, app_function = self.settings.app_function.rsplit('.', 1)
                    settings_s += "APP_MODULE='{0!s}'\nAPP_FUNCTION='{1!s}'\n".format(app_module,
                                                                                      app_function)

                if self.settings.debug:
                    # Cast to Bool in handler
                    settings_s += "DEBUG='{0!s}'\n".format(self.settings.debug)
                settings_s += "LOG_LEVEL='{0!s}'\n".format(self.settings.log_level)

                # If we're on a domain, we don't need to define the /<<env>> in
                # the WSGI PATH
                if self.settings.domain:
                    settings_s += "DOMAIN='{0!s}'\n".format(self.settings.domain)
                else:
                    settings_s += "DOMAIN=None\n"

                # Pass through remote config bucket and path
                if self.settings.remote_env_bucket and self.settings.remote_env_file:
                    settings_s += "REMOTE_ENV_BUCKET='{0!s}'\n".format(
                        self.settings.remote_env_bucket
                    )
                    settings_s += "REMOTE_ENV_FILE='{0!s}'\n".format(
                        self.settings.remote_env_file
                    )

                # We can be environment-aware
                settings_s += "API_STAGE='{0!s}'\n".format(self.settings.api_stage)

                if self.settings_filename:
                    settings_s += "SETTINGS_FILE='{0!s}'\n".format(self.settings_filename)
                else:
                    settings_s += "SETTINGS_FILE=None\n"

                if self.settings.django_settings:
                    settings_s += "DJANGO_SETTINGS='{0!s}'\n".format(self.settings.django_settings)
                else:
                    settings_s += "DJANGO_SETTINGS=None\n"

                # Copy our Django app into root of our package.
                # It doesn't work otherwise.
                base = __file__.rsplit(os.sep, 1)[0]
                django_py = ''.join(os.path.join(
                    [base, os.sep, 'ext', os.sep, 'django.py']))
                lambda_zip.write(django_py, 'django_zappa_app.py')

                # Lambda requires a specific chmod
                temp_settings = tempfile.NamedTemporaryFile(delete=False)
                os.chmod(temp_settings.name, 0o644)
                temp_settings.write(settings_s)
                temp_settings.close()
                lambda_zip.write(temp_settings.name, 'zappa_settings.py')
                os.remove(temp_settings.name)

        self.callback('zip')

    def remove_local_zip(self):
        """
        Remove our local zip file.
        """

        if self.settings.get('delete_zip', True):
            try:
                os.remove(self.settings.zip_path)
            except Exception:  # pragma: no cover
                pass

    def remove_uploaded_zip(self):
        """
        Remove the local and S3 zip file after uploading and updating.
        """

        # Remove the uploaded zip from S3, because it is now registered..
        self.zappa.remove_from_s3(self.settings.zip_path, self.settings.s3_bucket)

        # Finally, delete the local copy our zip package
        self.remove_local_zip()

    def is_already_deployed(self):
        # Make sure this isn't already deployed.
        deployed_versions = self.zappa.get_lambda_function_versions(self.settings.lambda_name)
        if len(deployed_versions) > 0:
            return True
        return False

    def create_and_configure_apigateway(self):
        # Create and configure the API Gateway
        api_id = self.zappa.create_api_gateway_routes(
            self.settings.lambda_arn,
            self.settings.lambda_name,
            self.settings.api_key_required,
            self.settings.integration_content_type_aliases)

        # Deploy the API!
        cache_cluster_enabled = self.settings.get('cache_cluster_enabled', False)
        cache_cluster_size = str(self.settings.get('cache_cluster_size', .5))

        endpoint_url = self.zappa.deploy_api_gateway(
            api_id=api_id,
            stage_name=self.settings.api_stage,
            cache_cluster_enabled=cache_cluster_enabled,
            cache_cluster_size=cache_cluster_size,
            api_key_required=self.settings.api_key_required,
            cloudwatch_log_level=self.settings.cloudwatch_log_level,
            cloudwatch_data_trace=self.settings.cloudwatch_data_trace,
            cloudwatch_metrics_enabled=self.settings.cloudwatch_metrics_enabled
        )

        if self.settings.touch:
            requests.get(endpoint_url)

    def execute_prebuild_script(self):
        """
        Parse and execute the prebuild_script from the zappa_settings.

        """
        mod_name, cb_func = self.settings.prebuild_script.rsplit('.', 1)

        mod = importlib.import_module(mod_name)
        getattr(mod, cb_func)()  # Call the function passing self
