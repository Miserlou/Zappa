# -*- coding: utf8 -*-
import collections
import json

from io import BytesIO
import botocore
import botocore.stub
import flask
import mock
import os
import random
import string
import zipfile
import unittest
import shutil
import sys
import tempfile
import uuid

from click.globals import resolve_color_default
from click.exceptions import ClickException

from zappa.cli import ZappaCLI, shamelessly_promote, disable_click_colors
from zappa.core import ALB_LAMBDA_ALIAS
from zappa.ext.django_zappa import get_django_wsgi
from zappa.letsencrypt import (
    get_cert_and_update_domain,
    create_domain_key,
    create_domain_csr,
    create_chained_certificate,
    cleanup,
    parse_account_key,
    parse_csr,
    sign_certificate,
    encode_certificate,
    register_account,
    verify_challenge,
    gettempdir,
)
from zappa.utilities import (
    conflicts_with_a_neighbouring_module,
    contains_python_files_or_subdirs,
    detect_django_settings,
    detect_flask_apps,
    get_venv_from_python_version,
    human_size,
    InvalidAwsLambdaName,
    parse_s3_url,
    string_to_timestamp,
    titlecase_keys,
    is_valid_bucket_name,
    validate_name,
)
from zappa.wsgi import create_wsgi_request, common_log
from zappa.core import Zappa, ASSUME_POLICY, ATTACH_POLICY


def random_string(length):
    return "".join(random.choice(string.printable) for _ in range(length))


class TestZappa(unittest.TestCase):
    def setUp(self):
        self.sleep_patch = mock.patch("time.sleep", return_value=None)
        # Tests expect us-east-1.
        # If the user has set a different region in env variables, we set it aside for now and use us-east-1
        self.users_current_region_name = os.environ.get("AWS_DEFAULT_REGION", None)
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
        if not os.environ.get("PLACEBO_MODE") == "record":
            self.sleep_patch.start()

    def tearDown(self):
        if not os.environ.get("PLACEBO_MODE") == "record":
            self.sleep_patch.stop()
        del os.environ["AWS_DEFAULT_REGION"]
        if self.users_current_region_name is not None:
            # Give the user their AWS region back, we're done testing with us-east-1.
            os.environ["AWS_DEFAULT_REGION"] = self.users_current_region_name

    ##
    # Sanity Tests
    ##

    def test_test(self):
        self.assertTrue(True)

    ##
    # Basic Tests
    ##

    def test_zappa(self):
        self.assertTrue(True)
        Zappa()

    def test_disable_click_colors(self):
        disable_click_colors()
        assert resolve_color_default() is False

    @mock.patch("zappa.core.find_packages")
    @mock.patch("os.remove")
    def test_copy_editable_packages(self, mock_remove, mock_find_packages):
        virtual_env = os.environ.get("VIRTUAL_ENV")
        if not virtual_env:
            return self.skipTest(
                "test_copy_editable_packages must be run in a virtualenv"
            )

        temp_package_dir = tempfile.mkdtemp()
        try:
            egg_links = [
                os.path.join(
                    virtual_env,
                    "lib",
                    get_venv_from_python_version(),
                    "site-packages",
                    "test-copy-editable-packages.egg-link",
                )
            ]
            egg_path = "/some/other/directory/package"
            mock_find_packages.return_value = [
                "package",
                "package.subpackage",
                "package.another",
            ]
            temp_egg_link = os.path.join(temp_package_dir, "package-python.egg-link")

            z = Zappa()
            mock_open = mock.mock_open(read_data=egg_path.encode("utf-8"))
            with mock.patch("zappa.core.open", mock_open), mock.patch(
                "glob.glob"
            ) as mock_glob, mock.patch("zappa.core.copytree") as mock_copytree:
                # we use glob.glob to get the egg-links in the temp packages
                # directory
                mock_glob.return_value = [temp_egg_link]

                z.copy_editable_packages(egg_links, temp_package_dir)

                # make sure we copied the right directories
                mock_copytree.assert_called_with(
                    os.path.join(egg_path, "package"),
                    os.path.join(temp_package_dir, "package"),
                    metadata=False,
                    symlinks=False,
                )
                self.assertEqual(mock_copytree.call_count, 1)

                # make sure it removes the egg-link from the temp packages
                # directory
                mock_remove.assert_called_with(temp_egg_link)
                self.assertEqual(mock_remove.call_count, 1)
        finally:
            shutil.rmtree(temp_package_dir)

        return

    def test_create_lambda_package(self):
        # mock the pkg_resources.WorkingSet() to include a known package in lambda_packages so that the code
        # for zipping pre-compiled packages gets called
        mock_installed_packages = {"psycopg2": "2.6.1"}
        with mock.patch(
            "zappa.core.Zappa.get_installed_packages",
            return_value=mock_installed_packages,
        ):
            z = Zappa(runtime="python3.6")
            path = z.create_lambda_zip(handler_file=os.path.realpath(__file__))
            self.assertTrue(os.path.isfile(path))
            os.remove(path)

    def test_get_manylinux_python36(self):
        z = Zappa(runtime="python3.6")
        self.assertIsNotNone(z.get_cached_manylinux_wheel("psycopg2", "2.7.1"))
        self.assertIsNone(z.get_cached_manylinux_wheel("derpderpderpderp", "0.0"))

        # mock with a known manylinux wheel package so that code for downloading them gets invoked
        mock_installed_packages = {"psycopg2": "2.7.1"}
        with mock.patch(
            "zappa.core.Zappa.get_installed_packages",
            return_value=mock_installed_packages,
        ):
            z = Zappa(runtime="python3.6")
            path = z.create_lambda_zip(handler_file=os.path.realpath(__file__))
            self.assertTrue(os.path.isfile(path))
            os.remove(path)

    def test_get_manylinux_python37(self):
        z = Zappa(runtime="python3.7")
        self.assertIsNotNone(z.get_cached_manylinux_wheel("psycopg2", "2.7.6"))
        self.assertIsNone(z.get_cached_manylinux_wheel("derp_no_such_thing", "0.0"))

        # mock with a known manylinux wheel package so that code for downloading them gets invoked
        mock_installed_packages = {"psycopg2": "2.7.6"}
        with mock.patch(
            "zappa.core.Zappa.get_installed_packages",
            return_value=mock_installed_packages,
        ):
            z = Zappa(runtime="python3.7")
            path = z.create_lambda_zip(handler_file=os.path.realpath(__file__))
            self.assertTrue(os.path.isfile(path))
            os.remove(path)

    def test_get_manylinux_python38(self):
        z = Zappa(runtime="python3.8")
        self.assertIsNotNone(z.get_cached_manylinux_wheel("psycopg2-binary", "2.8.4"))
        self.assertIsNone(z.get_cached_manylinux_wheel("derp_no_such_thing", "0.0"))

        # mock with a known manylinux wheel package so that code for downloading them gets invoked
        mock_installed_packages = {"psycopg2-binary": "2.8.4"}
        with mock.patch(
            "zappa.core.Zappa.get_installed_packages",
            return_value=mock_installed_packages,
        ):
            z = Zappa(runtime="python3.8")
            path = z.create_lambda_zip(handler_file=os.path.realpath(__file__))
            self.assertTrue(os.path.isfile(path))
            os.remove(path)

        # same, but with an ABI3 package
        mock_installed_packages = {"cryptography": "2.8"}
        with mock.patch(
            "zappa.core.Zappa.get_installed_packages",
            return_value=mock_installed_packages,
        ):
            z = Zappa(runtime="python3.8")
            path = z.create_lambda_zip(handler_file=os.path.realpath(__file__))
            self.assertTrue(os.path.isfile(path))
            os.remove(path)

    def test_getting_installed_packages(self, *args):
        z = Zappa(runtime="python3.6")

        # mock pkg_resources call to be same as what our mocked site packages dir has
        mock_package = collections.namedtuple(
            "mock_package", ["project_name", "version", "location"]
        )
        mock_pip_installed_packages = [
            mock_package("super_package", "0.1", "/venv/site-packages")
        ]

        with mock.patch("os.path.isdir", return_value=True):
            with mock.patch("os.listdir", return_value=["super_package"]):
                import pkg_resources  # this gets called in non-test Zappa mode

                with mock.patch(
                    "pkg_resources.WorkingSet", return_value=mock_pip_installed_packages
                ):
                    self.assertDictEqual(
                        z.get_installed_packages("", ""), {"super_package": "0.1"}
                    )

    def test_getting_installed_packages_mixed_case_location(self, *args):
        z = Zappa(runtime="python3.6")

        # mock pip packages call to be same as what our mocked site packages dir has
        mock_package = collections.namedtuple(
            "mock_package", ["project_name", "version", "location"]
        )
        mock_pip_installed_packages = [
            mock_package("SuperPackage", "0.1", "/Venv/site-packages"),
            mock_package("SuperPackage64", "0.1", "/Venv/site-packages64"),
        ]

        with mock.patch("os.path.isdir", return_value=True):
            with mock.patch("os.listdir", return_value=[]):
                import pkg_resources  # this gets called in non-test Zappa mode

                with mock.patch(
                    "pkg_resources.WorkingSet", return_value=mock_pip_installed_packages
                ):
                    self.assertDictEqual(
                        z.get_installed_packages(
                            "/venv/Site-packages", "/venv/site-packages64"
                        ),
                        {
                            "superpackage": "0.1",
                            "superpackage64": "0.1",
                        },
                    )

    def test_getting_installed_packages_mixed_case(self, *args):
        z = Zappa(runtime="python3.6")

        # mock pkg_resources call to be same as what our mocked site packages dir has
        mock_package = collections.namedtuple(
            "mock_package", ["project_name", "version", "location"]
        )
        mock_pip_installed_packages = [
            mock_package("SuperPackage", "0.1", "/venv/site-packages")
        ]

        with mock.patch("os.path.isdir", return_value=True):
            with mock.patch("os.listdir", return_value=["superpackage"]):
                import pkg_resources  # this gets called in non-test Zappa mode

                with mock.patch(
                    "pkg_resources.WorkingSet", return_value=mock_pip_installed_packages
                ):
                    self.assertDictEqual(
                        z.get_installed_packages("", ""), {"superpackage": "0.1"}
                    )

    def test_load_credentials(self):
        z = Zappa()
        z.aws_region = "us-east-1"
        z.load_credentials()
        self.assertEqual(z.boto_session.region_name, "us-east-1")
        self.assertEqual(z.aws_region, "us-east-1")

        z.aws_region = "eu-west-1"
        z.profile_name = "default"
        z.load_credentials()
        self.assertEqual(z.boto_session.region_name, "eu-west-1")
        self.assertEqual(z.aws_region, "eu-west-1")

        creds = {
            "AWS_ACCESS_KEY_ID": "AK123",
            "AWS_SECRET_ACCESS_KEY": "JKL456",
            "AWS_DEFAULT_REGION": "us-west-1",
        }
        with mock.patch.dict("os.environ", creds):
            z.aws_region = None
            z.load_credentials()
            loaded_creds = z.boto_session._session.get_credentials()

        self.assertEqual(loaded_creds.access_key, "AK123")
        self.assertEqual(loaded_creds.secret_key, "JKL456")
        self.assertEqual(z.boto_session.region_name, "us-west-1")

    def test_create_api_gateway_routes_with_different_auth_methods(self):
        z = Zappa()
        z.parameter_depth = 1
        z.integration_response_codes = [200]
        z.method_response_codes = [200]
        z.http_methods = ["GET"]
        z.credentials_arn = "arn:aws:iam::12345:role/ZappaLambdaExecution"
        lambda_arn = "arn:aws:lambda:us-east-1:12345:function:helloworld"

        # No auth at all
        z.create_stack_template(lambda_arn, "helloworld", False, False, None)
        parsable_template = json.loads(z.cf_template.to_json())
        self.assertEqual(
            "NONE",
            parsable_template["Resources"]["GET0"]["Properties"]["AuthorizationType"],
        )
        self.assertEqual(
            "NONE",
            parsable_template["Resources"]["GET1"]["Properties"]["AuthorizationType"],
        )
        self.assertEqual(
            False,
            parsable_template["Resources"]["GET0"]["Properties"]["ApiKeyRequired"],
        )
        self.assertEqual(
            False,
            parsable_template["Resources"]["GET1"]["Properties"]["ApiKeyRequired"],
        )

        # IAM auth
        z.create_stack_template(lambda_arn, "helloworld", False, True, None)
        parsable_template = json.loads(z.cf_template.to_json())
        self.assertEqual(
            "AWS_IAM",
            parsable_template["Resources"]["GET0"]["Properties"]["AuthorizationType"],
        )
        self.assertEqual(
            "AWS_IAM",
            parsable_template["Resources"]["GET1"]["Properties"]["AuthorizationType"],
        )
        self.assertEqual(
            False,
            parsable_template["Resources"]["GET0"]["Properties"]["ApiKeyRequired"],
        )
        self.assertEqual(
            False,
            parsable_template["Resources"]["GET1"]["Properties"]["ApiKeyRequired"],
        )

        # CORS with auth
        z.create_stack_template(lambda_arn, "helloworld", False, True, None, True)
        parsable_template = json.loads(z.cf_template.to_json())
        self.assertEqual(
            "AWS_IAM",
            parsable_template["Resources"]["GET0"]["Properties"]["AuthorizationType"],
        )
        self.assertEqual(
            "AWS_IAM",
            parsable_template["Resources"]["GET1"]["Properties"]["AuthorizationType"],
        )
        self.assertEqual(
            "NONE",
            parsable_template["Resources"]["OPTIONS0"]["Properties"][
                "AuthorizationType"
            ],
        )
        self.assertEqual(
            "NONE",
            parsable_template["Resources"]["OPTIONS1"]["Properties"][
                "AuthorizationType"
            ],
        )
        self.assertEqual(
            "MOCK",
            parsable_template["Resources"]["OPTIONS0"]["Properties"]["Integration"][
                "Type"
            ],
        )
        self.assertEqual(
            "MOCK",
            parsable_template["Resources"]["OPTIONS1"]["Properties"]["Integration"][
                "Type"
            ],
        )
        self.assertEqual(
            "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
            parsable_template["Resources"]["OPTIONS0"]["Properties"]["Integration"][
                "IntegrationResponses"
            ][0]["ResponseParameters"][
                "method.response.header.Access-Control-Allow-Headers"
            ],
        )
        self.assertEqual(
            "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
            parsable_template["Resources"]["OPTIONS1"]["Properties"]["Integration"][
                "IntegrationResponses"
            ][0]["ResponseParameters"][
                "method.response.header.Access-Control-Allow-Headers"
            ],
        )
        self.assertTrue(
            parsable_template["Resources"]["OPTIONS0"]["Properties"]["MethodResponses"][
                0
            ]["ResponseParameters"][
                "method.response.header.Access-Control-Allow-Headers"
            ]
        )
        self.assertTrue(
            parsable_template["Resources"]["OPTIONS1"]["Properties"]["MethodResponses"][
                0
            ]["ResponseParameters"][
                "method.response.header.Access-Control-Allow-Headers"
            ]
        )
        self.assertEqual(
            False,
            parsable_template["Resources"]["GET0"]["Properties"]["ApiKeyRequired"],
        )
        self.assertEqual(
            False,
            parsable_template["Resources"]["GET1"]["Properties"]["ApiKeyRequired"],
        )

        # API Key auth
        z.create_stack_template(lambda_arn, "helloworld", True, True, None)
        parsable_template = json.loads(z.cf_template.to_json())
        self.assertEqual(
            "AWS_IAM",
            parsable_template["Resources"]["GET0"]["Properties"]["AuthorizationType"],
        )
        self.assertEqual(
            "AWS_IAM",
            parsable_template["Resources"]["GET1"]["Properties"]["AuthorizationType"],
        )
        self.assertEqual(
            True, parsable_template["Resources"]["GET0"]["Properties"]["ApiKeyRequired"]
        )
        self.assertEqual(
            True, parsable_template["Resources"]["GET1"]["Properties"]["ApiKeyRequired"]
        )

        # Authorizer and IAM
        authorizer = {
            "function": "runapi.authorization.gateway_authorizer.evaluate_token",
            "result_ttl": 300,
            "token_header": "Authorization",
            "validation_expression": "xxx",
        }
        z.create_stack_template(lambda_arn, "helloworld", False, True, authorizer)
        parsable_template = json.loads(z.cf_template.to_json())
        self.assertEqual(
            "AWS_IAM",
            parsable_template["Resources"]["GET0"]["Properties"]["AuthorizationType"],
        )
        self.assertEqual(
            "AWS_IAM",
            parsable_template["Resources"]["GET1"]["Properties"]["AuthorizationType"],
        )
        with self.assertRaises(KeyError):
            parsable_template["Resources"]["Authorizer"]

        # Authorizer with validation expression
        invocations_uri = (
            "arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/"
            + lambda_arn
            + "/invocations"
        )
        z.create_stack_template(lambda_arn, "helloworld", False, False, authorizer)
        parsable_template = json.loads(z.cf_template.to_json())
        self.assertEqual(
            "CUSTOM",
            parsable_template["Resources"]["GET0"]["Properties"]["AuthorizationType"],
        )
        self.assertEqual(
            "CUSTOM",
            parsable_template["Resources"]["GET1"]["Properties"]["AuthorizationType"],
        )
        self.assertEqual(
            "TOKEN", parsable_template["Resources"]["Authorizer"]["Properties"]["Type"]
        )
        self.assertEqual(
            "ZappaAuthorizer",
            parsable_template["Resources"]["Authorizer"]["Properties"]["Name"],
        )
        self.assertEqual(
            300,
            parsable_template["Resources"]["Authorizer"]["Properties"][
                "AuthorizerResultTtlInSeconds"
            ],
        )
        self.assertEqual(
            invocations_uri,
            parsable_template["Resources"]["Authorizer"]["Properties"]["AuthorizerUri"],
        )
        self.assertEqual(
            z.credentials_arn,
            parsable_template["Resources"]["Authorizer"]["Properties"][
                "AuthorizerCredentials"
            ],
        )
        self.assertEqual(
            "xxx",
            parsable_template["Resources"]["Authorizer"]["Properties"][
                "IdentityValidationExpression"
            ],
        )

        # Authorizer without validation expression
        authorizer.pop("validation_expression", None)
        z.create_stack_template(lambda_arn, "helloworld", False, False, authorizer)
        parsable_template = json.loads(z.cf_template.to_json())
        self.assertEqual(
            "CUSTOM",
            parsable_template["Resources"]["GET0"]["Properties"]["AuthorizationType"],
        )
        self.assertEqual(
            "CUSTOM",
            parsable_template["Resources"]["GET1"]["Properties"]["AuthorizationType"],
        )
        self.assertEqual(
            "TOKEN", parsable_template["Resources"]["Authorizer"]["Properties"]["Type"]
        )
        with self.assertRaises(KeyError):
            parsable_template["Resources"]["Authorizer"]["Properties"][
                "IdentityValidationExpression"
            ]

        # Authorizer with arn
        authorizer = {
            "arn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
        }
        z.create_stack_template(lambda_arn, "helloworld", False, False, authorizer)
        parsable_template = json.loads(z.cf_template.to_json())
        self.assertEqual(
            "arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1:123456789012:function:my-function/invocations",
            parsable_template["Resources"]["Authorizer"]["Properties"]["AuthorizerUri"],
        )

    def test_policy_json(self):
        # ensure the policy docs are valid JSON
        json.loads(ASSUME_POLICY)
        json.loads(ATTACH_POLICY)

    def test_schedule_events(self):
        z = Zappa()
        path = os.getcwd()

    # z.schedule_events # TODO

    def test_update_aws_env_vars(self):
        z = Zappa()
        z.credentials_arn = object()

        with mock.patch.object(z, "lambda_client") as mock_client:
            # Simulate already having some AWS env vars remotely
            mock_client.get_function_configuration.return_value = {
                "Environment": {
                    "Variables": {"REMOTE_ONLY": "AAA", "CHANGED_REMOTE": "BBB"}
                }
            }
            z.update_lambda_configuration(
                "test",
                "test",
                "test",
                aws_environment_variables={"CHANGED_REMOTE": "ZZ", "LOCAL_ONLY": "YY"},
            )
            end_result_should_be = {
                "REMOTE_ONLY": "AAA",
                "CHANGED_REMOTE": "ZZ",
                "LOCAL_ONLY": "YY",
            }
            self.assertEqual(
                mock_client.update_function_configuration.call_args[1]["Environment"],
                {"Variables": end_result_should_be},
            )

        with mock.patch.object(z, "lambda_client") as mock_client:
            # Simulate already having some AWS env vars remotely but none set in aws_environment_variables
            mock_client.get_function_configuration.return_value = {
                "Environment": {
                    "Variables": {"REMOTE_ONLY_1": "AAA", "REMOTE_ONLY_2": "BBB"}
                }
            }
            z.update_lambda_configuration("test", "test", "test")
            end_result_should_be = {"REMOTE_ONLY_1": "AAA", "REMOTE_ONLY_2": "BBB"}
            self.assertEqual(
                mock_client.update_function_configuration.call_args[1]["Environment"],
                {"Variables": end_result_should_be},
            )

    def test_update_layers(self):
        z = Zappa()
        z.credentials_arn = object()

        with mock.patch.object(z, "lambda_client") as mock_client:
            mock_client.get_function_configuration.return_value = {}
            z.update_lambda_configuration(
                "test", "test", "test", layers=["Layer1", "Layer2"]
            )
            self.assertEqual(
                mock_client.update_function_configuration.call_args[1]["Layers"],
                ["Layer1", "Layer2"],
            )
        with mock.patch.object(z, "lambda_client") as mock_client:
            mock_client.get_function_configuration.return_value = {}
            z.update_lambda_configuration("test", "test", "test")
            self.assertEqual(
                mock_client.update_function_configuration.call_args[1]["Layers"], []
            )

    def test_update_empty_aws_env_hash(self):
        z = Zappa()
        z.credentials_arn = object()

        with mock.patch.object(z, "lambda_client") as mock_client:
            # Simulate having no AWS env vars remotely
            mock_client.get_function_configuration.return_value = {}
            z.update_lambda_configuration(
                "test",
                "test",
                "test",
                aws_environment_variables={"LOCAL_ONLY": "LZ", "SHOW_AND_TELL": "SHA"},
            )
            end_result_should_be = {"LOCAL_ONLY": "LZ", "SHOW_AND_TELL": "SHA"}
            self.assertEqual(
                mock_client.update_function_configuration.call_args[1]["Environment"],
                {"Variables": end_result_should_be},
            )

    ##
    # Logging
    ##

    def test_logging(self):
        """
        TODO
        """
        Zappa()

    ##
    # Mapping and pattern tests
    # Deprecated
    ##

    # def test_redirect_pattern(self):
    #     test_urls = [
    #         # a regular endpoint url
    #         'https://asdf1234.execute-api.us-east-1.amazonaws.com/env/path/to/thing',
    #         # an external url (outside AWS)
    #         'https://github.com/Miserlou/zappa/issues?q=is%3Aissue+is%3Aclosed',
    #         # a local url
    #         '/env/path/to/thing'
    #     ]

    #     for code in ['301', '302']:
    #         pattern = Zappa.selection_pattern(code)

    #         for url in test_urls:
    #             self.assertRegexpMatches(url, pattern)

    # def test_b64_pattern(self):
    #     head = '\{"http_status": '

    #     for code in ['400', '401', '402', '403', '404', '500']:
    #         pattern = Zappa.selection_pattern(code)

    #         document = head + code + random_string(50)
    #         self.assertRegexpMatches(document, pattern)

    #         for bad_code in ['200', '301', '302']:
    #             document = base64.b64encode(head + bad_code + random_string(50))
    #             self.assertNotRegexpMatches(document, pattern)

    # def test_200_pattern(self):
    #     pattern = Zappa.selection_pattern('200')
    #     self.assertEqual(pattern, '')

    ##
    # WSGI
    ##

    def test_wsgi_event(self):

        ## This is a pre-proxy+ event
        # event = {
        #     "body": "",
        #     "headers": {
        #         "Via": "1.1 e604e934e9195aaf3e36195adbcb3e18.cloudfront.net (CloudFront)",
        #         "Accept-Language": "en-US,en;q=0.5",
        #         "Accept-Encoding": "gzip",
        #         "CloudFront-Is-SmartTV-Viewer": "false",
        #         "CloudFront-Forwarded-Proto": "https",
        #         "X-Forwarded-For": "109.81.209.118, 216.137.58.43",
        #         "CloudFront-Viewer-Country": "CZ",
        #         "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        #         "X-Forwarded-Proto": "https",
        #         "X-Amz-Cf-Id": "LZeP_TZxBgkDt56slNUr_H9CHu1Us5cqhmRSswOh1_3dEGpks5uW-g==",
        #         "CloudFront-Is-Tablet-Viewer": "false",
        #         "X-Forwarded-Port": "443",
        #         "CloudFront-Is-Mobile-Viewer": "false",
        #         "CloudFront-Is-Desktop-Viewer": "true",
        #         "Content-Type": "application/json"
        #     },
        #     "params": {
        #         "parameter_1": "asdf1",
        #         "parameter_2": "asdf2",
        #     },
        #     "method": "POST",
        #     "query": {
        #         "dead": "beef"
        #     }
        # }

        event = {
            "body": None,
            "resource": "/",
            "requestContext": {
                "resourceId": "6cqjw9qu0b",
                "apiId": "9itr2lba55",
                "resourcePath": "/",
                "httpMethod": "GET",
                "requestId": "c17cb1bf-867c-11e6-b938-ed697406e3b5",
                "accountId": "724336686645",
                "identity": {
                    "apiKey": None,
                    "userArn": None,
                    "cognitoAuthenticationType": None,
                    "caller": None,
                    "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:48.0) Gecko/20100101 Firefox/48.0",
                    "user": None,
                    "cognitoIdentityPoolId": None,
                    "cognitoIdentityId": None,
                    "cognitoAuthenticationProvider": None,
                    "sourceIp": "50.191.225.98",
                    "accountId": None,
                },
                "stage": "devorr",
            },
            "queryStringParameters": None,
            "httpMethod": "GET",
            "pathParameters": None,
            "headers": {
                "Via": "1.1 6801928d54163af944bf854db8d5520e.cloudfront.net (CloudFront)",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "CloudFront-Is-SmartTV-Viewer": "false",
                "CloudFront-Forwarded-Proto": "https",
                "X-Forwarded-For": "50.191.225.98, 204.246.168.101",
                "CloudFront-Viewer-Country": "US",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1",
                "Host": "9itr2lba55.execute-api.us-east-1.amazonaws.com",
                "X-Forwarded-Proto": "https",
                "X-Amz-Cf-Id": "qgNdqKT0_3RMttu5KjUdnvHI3OKm1BWF8mGD2lX8_rVrJQhhp-MLDw==",
                "CloudFront-Is-Tablet-Viewer": "false",
                "X-Forwarded-Port": "443",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:48.0) Gecko/20100101 Firefox/48.0",
                "CloudFront-Is-Mobile-Viewer": "false",
                "CloudFront-Is-Desktop-Viewer": "true",
            },
            "stageVariables": None,
            "path": "/",
        }

        request = create_wsgi_request(event)

    def test_wsgi_path_info_unquoted(self):
        event = {
            "body": {},
            "headers": {},
            "pathParameters": {},
            "path": "/path%3A1",  # encoded /path:1
            "httpMethod": "GET",
            "queryStringParameters": {},
            "requestContext": {},
        }
        request = create_wsgi_request(event, trailing_slash=True)
        self.assertEqual("/path:1", request["PATH_INFO"])

    def test_wsgi_latin1(self):
        event = {
            "body": {},
            "headers": {},
            "pathParameters": {},
            "path": "/path/%E4%BB%8A%E6%97%A5%E3%81%AF",
            "httpMethod": "GET",
            "queryStringParameters": {"a": "%E4%BB%8A%E6%97%A5%E3%81%AF"},
            "requestContext": {},
        }
        request = create_wsgi_request(event, script_name="%E4%BB%8A%E6%97%A5%E3%81%AF")
        # verify that the path, query params and script name can be encoded in iso-8859-1
        request["PATH_INFO"].encode("iso-8859-1")
        request["QUERY_STRING"].encode("iso-8859-1")
        request["SCRIPT_NAME"].encode("iso-8859-1")

    def test_wsgi_logging(self):
        # event = {
        #     "body": {},
        #     "headers": {},
        #     "params": {
        #         "parameter_1": "asdf1",
        #         "parameter_2": "asdf2",
        #     },
        #     "httpMethod": "GET",
        #     "query": {}
        # }

        event = {
            "body": None,
            "resource": "/{proxy+}",
            "requestContext": {
                "resourceId": "dg451y",
                "apiId": "79gqbxq31c",
                "resourcePath": "/{proxy+}",
                "httpMethod": "GET",
                "requestId": "766df67f-8991-11e6-b2c4-d120fedb94e5",
                "accountId": "724336686645",
                "identity": {
                    "apiKey": None,
                    "userArn": None,
                    "cognitoAuthenticationType": None,
                    "caller": None,
                    "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:49.0) Gecko/20100101 Firefox/49.0",
                    "user": None,
                    "cognitoIdentityPoolId": None,
                    "cognitoIdentityId": None,
                    "cognitoAuthenticationProvider": None,
                    "sourceIp": "96.90.37.59",
                    "accountId": None,
                },
                "stage": "devorr",
            },
            "queryStringParameters": None,
            "httpMethod": "GET",
            "pathParameters": {"proxy": "asdf1/asdf2"},
            "headers": {
                "Via": "1.1 b2aeb492548a8a2d4036401355f928dd.cloudfront.net (CloudFront)",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "X-Forwarded-Port": "443",
                "X-Forwarded-For": "96.90.37.59, 54.240.144.50",
                "CloudFront-Viewer-Country": "US",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1",
                "Host": "79gqbxq31c.execute-api.us-east-1.amazonaws.com",
                "X-Forwarded-Proto": "https",
                "X-Amz-Cf-Id": "BBFP-RhGDrQGOzoCqjnfB2I_YzWt_dac9S5vBcSAEaoM4NfYhAQy7Q==",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:49.0) Gecko/20100101 Firefox/49.0",
                "CloudFront-Forwarded-Proto": "https",
            },
            "stageVariables": None,
            "path": "/asdf1/asdf2",
        }

        environ = create_wsgi_request(event, trailing_slash=False)
        response_tuple = collections.namedtuple("Response", ["status_code", "content"])
        response = response_tuple(200, "hello")
        le = common_log(environ, response, response_time=True)
        le = common_log(environ, response, response_time=False)

    def test_wsgi_multipart(self):
        # event = {'body': 'LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS03Njk1MjI4NDg0Njc4MTc2NTgwNjMwOTYxDQpDb250ZW50LURpc3Bvc2l0aW9uOiBmb3JtLWRhdGE7IG5hbWU9Im15c3RyaW5nIg0KDQpkZGQNCi0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tNzY5NTIyODQ4NDY3ODE3NjU4MDYzMDk2MS0tDQo=', 'headers': {'Content-Type': 'multipart/form-data; boundary=---------------------------7695228484678176580630961', 'Via': '1.1 38205a04d96d60185e88658d3185ccee.cloudfront.net (CloudFront)', 'Accept-Language': 'en-US,en;q=0.5', 'Accept-Encoding': 'gzip, deflate, br', 'CloudFront-Is-SmartTV-Viewer': 'false', 'CloudFront-Forwarded-Proto': 'https', 'X-Forwarded-For': '71.231.27.57, 104.246.180.51', 'CloudFront-Viewer-Country': 'US', 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:45.0) Gecko/20100101 Firefox/45.0', 'Host': 'xo2z7zafjh.execute-api.us-east-1.amazonaws.com', 'X-Forwarded-Proto': 'https', 'Cookie': 'zappa=AQ4', 'CloudFront-Is-Tablet-Viewer': 'false', 'X-Forwarded-Port': '443', 'Referer': 'https://xo8z7zafjh.execute-api.us-east-1.amazonaws.com/former/post', 'CloudFront-Is-Mobile-Viewer': 'false', 'X-Amz-Cf-Id': '31zxcUcVyUxBOMk320yh5NOhihn5knqrlYQYpGGyOngKKwJb0J0BAQ==', 'CloudFront-Is-Desktop-Viewer': 'true'}, 'params': {'parameter_1': 'post'}, 'method': 'POST', 'query': {}}

        event = {
            "body": "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS03Njk1MjI4NDg0Njc4MTc2NTgwNjMwOTYxDQpDb250ZW50LURpc3Bvc2l0aW9uOiBmb3JtLWRhdGE7IG5hbWU9Im15c3RyaW5nIg0KDQpkZGQNCi0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tNzY5NTIyODQ4NDY3ODE3NjU4MDYzMDk2MS0tDQo=",
            "resource": "/",
            "requestContext": {
                "resourceId": "6cqjw9qu0b",
                "apiId": "9itr2lba55",
                "resourcePath": "/",
                "httpMethod": "POST",
                "requestId": "c17cb1bf-867c-11e6-b938-ed697406e3b5",
                "accountId": "724336686645",
                "identity": {
                    "apiKey": None,
                    "userArn": None,
                    "cognitoAuthenticationType": None,
                    "caller": None,
                    "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:48.0) Gecko/20100101 Firefox/48.0",
                    "user": None,
                    "cognitoIdentityPoolId": None,
                    "cognitoIdentityId": None,
                    "cognitoAuthenticationProvider": None,
                    "sourceIp": "50.191.225.98",
                    "accountId": None,
                },
                "stage": "devorr",
            },
            "queryStringParameters": None,
            "httpMethod": "POST",
            "pathParameters": None,
            "headers": {
                "Content-Type": "multipart/form-data; boundary=---------------------------7695228484678176580630961",
                "Via": "1.1 38205a04d96d60185e88658d3185ccee.cloudfront.net (CloudFront)",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "CloudFront-Is-SmartTV-Viewer": "false",
                "CloudFront-Forwarded-Proto": "https",
                "X-Forwarded-For": "71.231.27.57, 104.246.180.51",
                "CloudFront-Viewer-Country": "US",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:45.0) Gecko/20100101 Firefox/45.0",
                "Host": "xo2z7zafjh.execute-api.us-east-1.amazonaws.com",
                "X-Forwarded-Proto": "https",
                "Cookie": "zappa=AQ4",
                "CloudFront-Is-Tablet-Viewer": "false",
                "X-Forwarded-Port": "443",
                "Referer": "https://xo8z7zafjh.execute-api.us-east-1.amazonaws.com/former/post",
                "CloudFront-Is-Mobile-Viewer": "false",
                "X-Amz-Cf-Id": "31zxcUcVyUxBOMk320yh5NOhihn5knqrlYQYpGGyOngKKwJb0J0BAQ==",
                "CloudFront-Is-Desktop-Viewer": "true",
            },
            "stageVariables": None,
            "path": "/",
        }

        environ = create_wsgi_request(event, trailing_slash=False)
        response_tuple = collections.namedtuple("Response", ["status_code", "content"])
        response = response_tuple(200, "hello")

    def test_wsgi_without_body(self):
        event = {
            "body": None,
            "resource": "/",
            "requestContext": {
                "resourceId": "6cqjw9qu0b",
                "apiId": "9itr2lba55",
                "resourcePath": "/",
                "httpMethod": "POST",
                "requestId": "c17cb1bf-867c-11e6-b938-ed697406e3b5",
                "accountId": "724336686645",
                "identity": {
                    "apiKey": None,
                    "userArn": None,
                    "cognitoAuthenticationType": None,
                    "caller": None,
                    "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:48.0) Gecko/20100101 Firefox/48.0",
                    "user": None,
                    "cognitoIdentityPoolId": None,
                    "cognitoIdentityId": None,
                    "cognitoAuthenticationProvider": None,
                    "sourceIp": "50.191.225.98",
                    "accountId": None,
                },
                "stage": "devorr",
            },
            "queryStringParameters": None,
            "httpMethod": "POST",
            "pathParameters": None,
            "headers": {
                "Via": "1.1 38205a04d96d60185e88658d3185ccee.cloudfront.net (CloudFront)",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "CloudFront-Is-SmartTV-Viewer": "false",
                "CloudFront-Forwarded-Proto": "https",
                "X-Forwarded-For": "71.231.27.57, 104.246.180.51",
                "CloudFront-Viewer-Country": "US",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:45.0) Gecko/20100101 Firefox/45.0",
                "Host": "xo2z7zafjh.execute-api.us-east-1.amazonaws.com",
                "X-Forwarded-Proto": "https",
                "Cookie": "zappa=AQ4",
                "CloudFront-Is-Tablet-Viewer": "false",
                "X-Forwarded-Port": "443",
                "Referer": "https://xo8z7zafjh.execute-api.us-east-1.amazonaws.com/former/post",
                "CloudFront-Is-Mobile-Viewer": "false",
                "X-Amz-Cf-Id": "31zxcUcVyUxBOMk320yh5NOhihn5knqrlYQYpGGyOngKKwJb0J0BAQ==",
                "CloudFront-Is-Desktop-Viewer": "true",
            },
            "stageVariables": None,
            "path": "/",
            "isBase64Encoded": True,
        }

        environ = create_wsgi_request(event, trailing_slash=False)
        response_tuple = collections.namedtuple("Response", ["status_code", "content"])
        response = response_tuple(200, "hello")

    def test_wsgi_from_apigateway_testbutton(self):
        """
        API Gateway resources have a "test bolt" button on methods.
        This button sends some empty dicts as 'null' instead of '{}'.
        """
        event = {
            "resource": "/",
            "path": "/",
            "httpMethod": "GET",
            "headers": None,
            "queryStringParameters": None,
            "pathParameters": None,
            "stageVariables": None,
            "requestContext": {
                "accountId": "0123456",
                "resourceId": "qwertyasdf",
                "stage": "test-invoke-stage",
                "requestId": "test-invoke-request",
                "identity": {
                    "cognitoIdentityPoolId": None,
                    "accountId": "0123456",
                    "cognitoIdentityId": None,
                    "caller": "MYCALLERID",
                    "apiKey": "test-invoke-api-key",
                    "sourceIp": "test-invoke-source-ip",
                    "accessKey": "MYACCESSKEY",
                    "cognitoAuthenticationType": None,
                    "cognitoAuthenticationProvider": None,
                    "userArn": "arn:aws:iam::fooo:user/my.username",
                    "userAgent": "Apache-HttpClient/4.5.x (Java/1.8.0_112)",
                    "user": "MYCALLERID",
                },
                "resourcePath": "/",
                "httpMethod": "GET",
                "apiId": "myappid",
            },
            "body": None,
            "isBase64Encoded": False,
        }

        environ = create_wsgi_request(event, trailing_slash=False)
        response_tuple = collections.namedtuple("Response", ["status_code", "content"])
        response = response_tuple(200, "hello")

    ##
    # Handler
    ##

    ##
    # CLI
    ##

    def test_cli_sanity(self):
        zappa_cli = ZappaCLI()
        return

    def test_load_settings(self):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "ttt888"
        zappa_cli.load_settings("test_settings.json")
        self.assertEqual(False, zappa_cli.stage_config["touch"])

    def test_load_extended_settings(self):

        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "extendo"
        zappa_cli.load_settings("test_settings.json")
        self.assertEqual("lmbda", zappa_cli.stage_config["s3_bucket"])
        self.assertEqual(True, zappa_cli.stage_config["touch"])

        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "extendofail"
        with self.assertRaises(ClickException):
            zappa_cli.load_settings("test_settings.json")

        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "ttt888"
        with self.assertRaises(RuntimeError):
            zappa_cli.load_settings("tests/test_bad_circular_extends_settings.json")

        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "extendo2"
        zappa_cli.load_settings("test_settings.json")
        self.assertEqual(
            "lmbda2", zappa_cli.stage_config["s3_bucket"]
        )  # Second Extension
        self.assertTrue(zappa_cli.stage_config["touch"])  # First Extension
        self.assertTrue(zappa_cli.stage_config["delete_local_zip"])  # The base

    def test_load_settings__lambda_concurrency_enabled(self):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "lambda_concurrency_enabled"
        zappa_cli.load_settings("test_settings.json")
        self.assertEqual(6, zappa_cli.stage_config["lambda_concurrency"])

    def test_load_settings_yml(self):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "ttt888"
        zappa_cli.load_settings("tests/test_settings.yml")
        self.assertEqual(False, zappa_cli.stage_config["touch"])

        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "extendo"
        zappa_cli.load_settings("tests/test_settings.yml")
        self.assertEqual("lmbda", zappa_cli.stage_config["s3_bucket"])
        self.assertEqual(True, zappa_cli.stage_config["touch"])

    def test_load_settings_yaml(self):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "ttt888"
        zappa_cli.load_settings("tests/test_settings.yaml")
        self.assertEqual(False, zappa_cli.stage_config["touch"])

        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "extendo"
        zappa_cli.load_settings("tests/test_settings.yaml")
        self.assertEqual("lmbda", zappa_cli.stage_config["s3_bucket"])
        self.assertEqual(True, zappa_cli.stage_config["touch"])

    def test_load_settings_toml(self):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "ttt888"
        zappa_cli.load_settings("tests/test_settings.toml")
        self.assertEqual(False, zappa_cli.stage_config["touch"])

    def test_settings_extension(self):
        """
        Make sure Zappa uses settings in the proper order: JSON, TOML, YAML.
        """
        tempdir = tempfile.mkdtemp(prefix="zappa-test-settings")
        shutil.copy("tests/test_one_env.json", tempdir + "/zappa_settings.json")
        shutil.copy("tests/test_settings.yml", tempdir + "/zappa_settings.yml")
        shutil.copy("tests/test_settings.yml", tempdir + "/zappa_settings.yaml")
        shutil.copy("tests/test_settings.toml", tempdir + "/zappa_settings.toml")

        orig_cwd = os.getcwd()
        os.chdir(tempdir)
        try:
            zappa_cli = ZappaCLI()

            # With all three, we should get the JSON file first.
            self.assertEqual(
                zappa_cli.get_json_or_yaml_settings(), "zappa_settings.json"
            )
            zappa_cli.load_settings_file()
            self.assertIn("lonely", zappa_cli.zappa_settings)
            os.unlink("zappa_settings.json")

            # Without the JSON file, we should get the TOML file.
            self.assertEqual(
                zappa_cli.get_json_or_yaml_settings(), "zappa_settings.toml"
            )
            zappa_cli.load_settings_file()
            self.assertIn("ttt888", zappa_cli.zappa_settings)
            self.assertNotIn("devor", zappa_cli.zappa_settings)
            os.unlink("zappa_settings.toml")

            # With just the YAML file, we should get it.
            self.assertEqual(
                zappa_cli.get_json_or_yaml_settings(), "zappa_settings.yml"
            )
            zappa_cli.load_settings_file()
            self.assertIn("ttt888", zappa_cli.zappa_settings)
            self.assertIn("devor", zappa_cli.zappa_settings)
            os.unlink("zappa_settings.yml")

            self.assertEqual(
                zappa_cli.get_json_or_yaml_settings(), "zappa_settings.yaml"
            )
            zappa_cli.load_settings_file()
            self.assertIn("ttt888", zappa_cli.zappa_settings)
            self.assertIn("devor", zappa_cli.zappa_settings)
            os.unlink("zappa_settings.yaml")

            # Without anything, we should get an exception.
            self.assertRaises(ClickException, zappa_cli.get_json_or_yaml_settings)
        finally:
            os.chdir(orig_cwd)
            shutil.rmtree(tempdir)

    def test_cli_utility(self):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "ttt888"
        zappa_cli.load_settings("test_settings.json")
        zappa_cli.create_package()
        zappa_cli.remove_local_zip()
        logs = [
            {"timestamp": "12345", "message": "[START RequestId] test"},
            {"timestamp": "12345", "message": "[REPORT RequestId] test"},
            {"timestamp": "12345", "message": "[END RequestId] test"},
            {"timestamp": "12345", "message": "test"},
            {
                "timestamp": "1480001341214",
                "message": '[INFO] 2016-11-24T15:29:13.326Z c0cb52d1-b25a-11e6-9b73-f940ce24319a 59.111.125.48 - -  [24/Nov/2016:15:29:13 +0000] "GET / HTTP/1.1" 200 2590 "" "python-requests/2.11.0" 0/4.672',
            },
            {
                "timestamp": "1480001341214",
                "message": '[INFO] 2016-11-24T15:29:13.326Z c0cb52d1-b25a-11e6-9b73-f940ce24319a 59.111.125.48 - -  [24/Nov/2016:15:29:13 +0000] "GET / HTTP/1.1" 400 2590 "" "python-requests/2.11.0" 0/4.672',
            },
            {
                "timestamp": "1480001341215",
                "message": "[1480001341258] [DEBUG] 2016-11-24T15:29:01.258Z b890d8f6-b25a-11e6-b6bc-718f7ec807df Zappa Event: {}",
            },
        ]
        zappa_cli.print_logs(logs)
        zappa_cli.print_logs(logs, colorize=False)
        zappa_cli.print_logs(logs, colorize=False, http=True)
        zappa_cli.print_logs(logs, colorize=True, http=True)
        zappa_cli.print_logs(logs, colorize=True, http=False)
        zappa_cli.print_logs(logs, colorize=True, non_http=True)
        zappa_cli.print_logs(logs, colorize=True, non_http=False)
        zappa_cli.print_logs(logs, colorize=True, non_http=True, http=True)
        zappa_cli.print_logs(logs, colorize=True, non_http=False, http=False)
        zappa_cli.print_logs(logs, colorize=False, force_colorize=False)
        zappa_cli.print_logs(logs, colorize=False, force_colorize=True)
        zappa_cli.print_logs(logs, colorize=True, force_colorize=False)
        zappa_cli.print_logs(
            logs, colorize=True, non_http=False, http=False, force_colorize=True
        )
        zappa_cli.check_for_update()

    def test_cli_format_invoke_command(self):
        zappa_cli = ZappaCLI()
        plain_string = "START RequestId: def8808e-5223-11e7-b3b7-4919f6e7dd4f Version: $LATEST\n[DEBUG]\t2017-06-15T23:39:27.638Z\tdef8808e-5223-11e7-b3b7-4919f6e7dd4f\tZappa Event: {'raw_command': 'import datetime; print(datetime.datetime.now())'}\n2017-06-15 23:39:27.638296\nEND RequestId: def8808e-5223-11e7-b3b7-4919f6e7dd4f\nREPORT RequestId: def8808e-5223-11e7-b3b7-4919f6e7dd4f\tDuration: 0.59 ms\tBilled Duration: 100 ms \tMemory Size: 512 MB\tMax Memory Used: 53 MB\t\n"
        final_string = "START RequestId: def8808e-5223-11e7-b3b7-4919f6e7dd4f Version: $LATEST\n[DEBUG] 2017-06-15T23:39:27.638Z def8808e-5223-11e7-b3b7-4919f6e7dd4f Zappa Event: {'raw_command': 'import datetime; print(datetime.datetime.now())'}\n2017-06-15 23:39:27.638296\nEND RequestId: def8808e-5223-11e7-b3b7-4919f6e7dd4f\nREPORT RequestId: def8808e-5223-11e7-b3b7-4919f6e7dd4f\nDuration: 0.59 ms\nBilled Duration: 100 ms \nMemory Size: 512 MB\nMax Memory Used: 53 MB\n"

        formated_string = zappa_cli.format_invoke_command(plain_string)
        self.assertEqual(final_string, formated_string)

    def test_cli_colorize_invoke_command(self):
        zappa_cli = ZappaCLI()
        plain_string = "START RequestId: dd81d3de-5225-11e7-a24f-59014f430ab3 Version: $LATEST\n[DEBUG] 2017-06-15T23:53:44.194Z dd81d3de-5225-11e7-a24f-59014f430ab3 Zappa Event: {'raw_command': 'import datetime; print(datetime.datetime.now())'}\n2017-06-15 23:53:44.195012\nEND RequestId: dd81d3de-5225-11e7-a24f-59014f430ab3\nREPORT RequestId: dd81d3de-5225-11e7-a24f-59014f430ab3\nDuration: 0.63 ms\nBilled Duration: 100 ms \nMemory Size: 512 MB\nMax Memory Used: 53 MB\n"
        final_string = "\x1b[36m\x1b[1m[START]\x1b[0m \x1b[32m\x1b[1mRequestId:\x1b[0m \x1b[35m\x1b[35mdd81d3de-5225-11e7-a24f-59014f430ab3\x1b[0m\x1b[0m \x1b[32m\x1b[1mVersion:\x1b[0m $LATEST\n\x1b[36m\x1b[1m[DEBUG]\x1b[0m 2017-06-15T23:53:44.194Z \x1b[35m\x1b[35mdd81d3de-5225-11e7-a24f-59014f430ab3\x1b[0m\x1b[0m \x1b[32m\x1b[1mZappa Event:\x1b[0m {'raw_command': 'import datetime; print(datetime.datetime.now())'}\n2017-06-15 23:53:44.195012\n\x1b[36m\x1b[1m[END]\x1b[0m \x1b[32m\x1b[1mRequestId:\x1b[0m \x1b[35m\x1b[35mdd81d3de-5225-11e7-a24f-59014f430ab3\x1b[0m\x1b[0m\n\x1b[36m\x1b[1m[REPORT]\x1b[0m \x1b[32m\x1b[1mRequestId:\x1b[0m \x1b[35m\x1b[35mdd81d3de-5225-11e7-a24f-59014f430ab3\x1b[0m\x1b[0m\n\x1b[32m\x1b[1mDuration:\x1b[0m 0.63 ms\n\x1b[32m\x1b[1mBilled\x1b[0m \x1b[32m\x1b[1mDuration:\x1b[0m 100 ms \n\x1b[32m\x1b[1mMemory Size:\x1b[0m 512 MB\n\x1b[32m\x1b[1mMax Memory Used:\x1b[0m 53 MB\n"

        colorized_string = zappa_cli.colorize_invoke_command(plain_string)
        self.assertEqual(final_string, colorized_string)

    def test_cli_colorize_whole_words_only(self):
        zappa_cli = ZappaCLI()
        plain_string = "START RESTART END RENDER report [DEBUG] TEXT[DEBUG]TEXT"
        final_string = "\x1b[36m\x1b[1m[START]\x1b[0m RESTART \x1b[36m\x1b[1m[END]\x1b[0m RENDER report \x1b[36m\x1b[1m[DEBUG]\x1b[0m TEXT\x1b[36m\x1b[1m[DEBUG]\x1b[0mTEXT"

        colorized_string = zappa_cli.colorize_invoke_command(plain_string)
        self.assertEqual(final_string, colorized_string)

    def test_cli_colorize_invoke_command_bad_string(self):
        zappa_cli = ZappaCLI()
        plain_string = "Hey, I'm a plain string, won't be colorized"
        final_string = "Hey, I'm a plain string, won't be colorized"

        colorized_string = zappa_cli.colorize_invoke_command(plain_string)
        self.assertEqual(final_string, colorized_string)

    # def test_cli_args(self):
    #     zappa_cli = ZappaCLI()
    #     # Sanity
    #     argv = '-s test_settings.json derp ttt888'.split()
    #     with self.assertRaises(SystemExit) as system_exit:
    #         zappa_cli.handle(argv)
    #     self.assertEqual(system_exit.exception.code, 2)

    # def test_cli_error_exit_code(self):
    #     # Discussion: https://github.com/Miserlou/Zappa/issues/407
    #     zappa_cli = ZappaCLI()
    #     # Sanity
    #     argv = '-s test_settings.json status devor'.split()
    #     with self.assertRaises(SystemExit) as system_exit:
    #         zappa_cli.handle(argv)
    #     self.assertEqual(system_exit.exception.code, 1)

    # def test_cli_default(self):
    #     # Discussion: https://github.com/Miserlou/Zappa/issues/422
    #     zappa_cli = ZappaCLI()
    #     argv = '-s tests/test_one_env.json status'.split()
    #     # It'll fail, but at least it'll cover it.
    #     with self.assertRaises(SystemExit) as system_exit:
    #         zappa_cli.handle(argv)
    #     self.assertEqual(system_exit.exception.code, 1)

    #     zappa_cli = ZappaCLI()
    #     argv = '-s tests/test_one_env.json status --all'.split()
    #     # It'll fail, but at least it'll cover it.
    #     with self.assertRaises(SystemExit) as system_exit:
    #         zappa_cli.handle(argv)
    #     self.assertEqual(system_exit.exception.code, 1)

    #     zappa_cli = ZappaCLI()
    #     argv = '-s test_settings.json status'.split()
    #     with self.assertRaises(SystemExit) as system_exit:
    #         zappa_cli.handle(argv)
    #     self.assertEqual(system_exit.exception.code, 2)

    # def test_cli_negative_rollback(self):
    #     zappa_cli = ZappaCLI()
    #     argv = '-s test_settings.json rollback -n -1 dev'.split()
    #     output = StringIO()
    #     old_stderr, sys.stderr = sys.stderr, output
    #     with self.assertRaises(SystemExit) as system_exit:

    #         print argv

    #         zappa_cli.handle(argv)
    #     self.assertEqual(system_exit.exception.code, 2)

    #     error_msg = output.getvalue().strip()
    #     expected = r".*This argument must be positive \(got -1\)$"
    #     self.assertRegexpMatches(error_msg, expected)
    #     sys.stderr = old_stderr

    # @mock.patch('zappa.cli.ZappaCLI.dispatch_command')
    # def test_cli_invoke(self, _):
    #     zappa_cli = ZappaCLI()
    #     argv = '-s test_settings.json invoke '.split()
    #     raw_tests = (
    #         ['--raw', 'devor', '"print 1+2"'],
    #         ['devor', '"print 1+2"', '--raw']
    #     )

    #     for cmd in raw_tests:
    #         zappa_cli.handle(argv + cmd)
    #         args = zappa_cli.vargs

    #         self.assertFalse(args['all'])
    #         self.assertTrue(args['raw'])
    #         self.assertEquals(args['command_rest'], '"print 1+2"')
    #         self.assertEquals(args['command_env'], 'devor')

    #     all_raw_tests = (
    #         ['--all', '--raw', '"print 1+2"'],
    #         ['"print 1+2"', '--all', '--raw'],
    #         ['--raw', '"print 1+2"', '--all'],
    #         ['--all', '"print 1+2"', '--raw']
    #     )
    #     for cmd in all_raw_tests:
    #         zappa_cli.handle(argv + cmd)
    #         args = zappa_cli.vargs

    #         self.assertTrue(args['all'])
    #         self.assertTrue(args['raw'])
    #         self.assertEquals(args['command_rest'], '"print 1+2"')
    #         self.assertEquals(args['command_env'], None)

    #     zappa_cli.handle(argv + ['devor', 'myapp.my_func'])
    #     args = zappa_cli.vargs
    #     self.assertEquals(args['command_rest'], 'myapp.my_func')

    #     all_func_tests = (
    #         ['--all', 'myapp.my_func'],
    #         ['myapp.my_func', '--all']
    #     )
    #     for cmd in all_func_tests:
    #         zappa_cli.handle(argv + cmd)
    #         args = zappa_cli.vargs

    #         self.assertTrue(args['all'])
    #         self.assertEquals(args['command_rest'], 'myapp.my_func')

    # @mock.patch('zappa.cli.ZappaCLI.dispatch_command')
    # def test_cli_manage(self, _):
    #     zappa_cli = ZappaCLI()
    #     argv = '--settings test_settings.json manage'.split()
    #     all_tests = (
    #         ['--all', 'showmigrations', 'admin'],
    #         ['showmigrations', 'admin', '--all']
    #     )

    #     for cmd in all_tests:

    #         print argv
    #         print cmd
    #         print(argv + cmd)

    #         zappa_cli.handle(argv + cmd)
    #         args = zappa_cli.vargs

    #         self.assertTrue(args['all'])
    #         self.assertTrue(
    #             args['command_rest'] == ['showmigrations', 'admin']
    #         )

    #     cmd = ['devor', 'showmigrations', 'admin']
    #     zappa_cli.handle(argv + cmd)
    #     args = zappa_cli.vargs

    #     self.assertFalse(args['all'])
    #     self.assertTrue(
    #         args['command_rest'] == ['showmigrations', 'admin']
    #     )

    #     cmd = ['devor', '"shell --version"']
    #     zappa_cli.handle(argv + cmd)
    #     args = zappa_cli.vargs

    #     self.assertFalse(args['all'])
    #     self.assertTrue(args['command_rest'] == ['"shell --version"'])

    def test_bad_json_catch(self):
        zappa_cli = ZappaCLI()
        self.assertRaises(
            ValueError, zappa_cli.load_settings_file, "tests/test_bad_settings.json"
        )

    def test_bad_stage_name_catch(self):
        zappa_cli = ZappaCLI()
        self.assertRaises(
            ValueError,
            zappa_cli.load_settings,
            "tests/test_bad_stage_name_settings.json",
        )

    def test_bad_environment_vars_catch(self):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "ttt888"
        self.assertRaises(
            ValueError, zappa_cli.load_settings, "tests/test_bad_environment_vars.json"
        )

    # @mock.patch('botocore.session.Session.full_config', new_callable=mock.PropertyMock)
    # def test_cli_init(self, mock_config):

    #     # Coverage for all profile detection paths
    #     mock_config.side_effect = [
    #         { 'profiles' : { 'default' : { 'region' : 'us-east-1'} } },
    #         { 'profiles' : { 'default' : { 'region' : 'us-east-1'} } },
    #         { 'profiles' : {
    #             'default' : {
    #                 'region' : 'us-east-1'
    #             },
    #             'another' : {
    #                 'region' : 'us-east-1'
    #             }
    #         } },
    #         { 'profiles' : {
    #             'radical' : {
    #                 'region' : 'us-east-1'
    #             },
    #             'another' : {
    #                 'region' : 'us-east-1'
    #             }
    #         } },
    #         { 'profiles': {} },
    #         { 'profiles': {} },
    #         { 'profiles' : { 'default' : { 'region' : 'us-east-1'} } },
    #     ]

    #     if os.path.isfile('zappa_settings.json'):
    #         os.remove('zappa_settings.json')

    #     # Test directly
    #     zappa_cli = ZappaCLI()
    #     # Via http://stackoverflow.com/questions/2617057/how-to-supply-stdin-files-and-environment-variable-inputs-to-python-unit-tests
    #     inputs = ['dev', 'lmbda', 'test_settings', 'y', '']

    #     def test_for(inputs):
    #         input_generator = (i for i in inputs)
    #         bi = 'builtins.input'

    #         with mock.patch(bi, lambda prompt: next(input_generator)):
    #             zappa_cli.init()

    #         if os.path.isfile('zappa_settings.json'):
    #             os.remove('zappa_settings.json')

    #     test_for(inputs)
    #     test_for(['dev', 'lmbda', 'test_settings', 'n', ''])
    #     test_for(['dev', 'default', 'lmbda', 'test_settings', '', ''])
    #     test_for(['dev', 'radical', 'lmbda', 'test_settings', 'p', ''])
    #     test_for(['dev', 'lmbda', 'test_settings', 'y', ''])
    #     test_for(['dev', 'lmbda', 'test_settings', 'p', 'n'])

    #     # Test via handle()
    #     input_generator = (i for i in inputs)
    #     bi = 'builtins.input'
    #     with mock.patch(bi, lambda prompt: next(input_generator)):
    #         zappa_cli = ZappaCLI()
    #         argv = ['init']
    #         zappa_cli.handle(argv)

    #     if os.path.isfile('zappa_settings.json'):
    #         os.remove('zappa_settings.json')

    def test_domain_name_match(self):
        # Simple sanity check
        zone = Zappa.get_best_match_zone(
            all_zones={
                "HostedZones": [
                    {
                        "Name": "example.com.au.",
                        "Id": "zone-correct",
                        "Config": {"PrivateZone": False},
                    }
                ]
            },
            domain="www.example.com.au",
        )
        assert zone == "zone-correct"

        # No match test
        zone = Zappa.get_best_match_zone(
            all_zones={
                "HostedZones": [
                    {
                        "Name": "example.com.au.",
                        "Id": "zone-incorrect",
                        "Config": {"PrivateZone": False},
                    }
                ]
            },
            domain="something-else.com.au",
        )
        assert zone is None

        # More involved, better match should win.
        zone = Zappa.get_best_match_zone(
            all_zones={
                "HostedZones": [
                    {
                        "Name": "example.com.au.",
                        "Id": "zone-incorrect",
                        "Config": {"PrivateZone": False},
                    },
                    {
                        "Name": "subdomain.example.com.au.",
                        "Id": "zone-correct",
                        "Config": {"PrivateZone": False},
                    },
                ]
            },
            domain="www.subdomain.example.com.au",
        )
        assert zone == "zone-correct"

        # Check private zone is not matched
        zone = Zappa.get_best_match_zone(
            all_zones={
                "HostedZones": [
                    {
                        "Name": "example.com.au.",
                        "Id": "zone-private",
                        "Config": {"PrivateZone": True},
                    }
                ]
            },
            domain="www.example.com.au",
        )
        assert zone is None

        # More involved, should ignore the private zone and match the public.
        zone = Zappa.get_best_match_zone(
            all_zones={
                "HostedZones": [
                    {
                        "Name": "subdomain.example.com.au.",
                        "Id": "zone-private",
                        "Config": {"PrivateZone": True},
                    },
                    {
                        "Name": "subdomain.example.com.au.",
                        "Id": "zone-public",
                        "Config": {"PrivateZone": False},
                    },
                ]
            },
            domain="www.subdomain.example.com.au",
        )
        assert zone == "zone-public"

    ##
    # Let's Encrypt / ACME
    ##

    def test_lets_encrypt_sanity(self):
        # We need a fake account key and crt
        import subprocess

        devnull = open(os.devnull, "wb")
        out = subprocess.check_output(["openssl", "genrsa", "2048"], stderr=devnull)
        with open(os.path.join(gettempdir(), "account.key"), "wb") as f:
            f.write(out)

        cmd = [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-subj",
            "/C=US/ST=Denial/L=Springfield/O=Dis/CN=www.example.com",
            "-passout",
            "pass:foo",
            "-keyout",
            os.path.join(gettempdir(), "key.key"),
            "-out",
            os.path.join(gettempdir(), "signed.crt"),
            "-days",
            "1",
        ]
        devnull = open(os.devnull, "wb")
        subprocess.check_call(cmd, stdout=devnull, stderr=devnull)

        DEFAULT_CA = "https://acme-staging.api.letsencrypt.org"
        CA = "https://acme-staging.api.letsencrypt.org"

        try:
            result = register_account()
        except ValueError as e:
            pass  # that's fine.

        create_domain_key()
        create_domain_csr("herp.derp.wtf")
        parse_account_key()
        parse_csr()
        create_chained_certificate()

        try:
            result = sign_certificate()
        except ValueError as e:
            pass  # that's fine.

        # This service fails due to remote "over-quota" errors,
        # so let's retire it until we can find a better provider.

        # result = verify_challenge('http://echo.jsontest.com/status/valid')
        # try:
        #     result = verify_challenge('http://echo.jsontest.com/status/fail')
        # except ValueError as e:
        #     pass # that's fine.
        # try:
        #     result = verify_challenge('http://bing.com')
        # except ValueError as e:
        #     pass # that's fine.

        encode_certificate(b"123")

        # without domain testing..
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "ttt888"
        zappa_cli.load_settings("test_settings.json")
        get_cert_and_update_domain(zappa_cli, "kerplah", "zzzz", domain=None)

    def test_certify_sanity_checks(self):
        """
        Make sure 'zappa certify':
        * Errors out when a deployment hasn't taken place.
        * Writes errors when certificate settings haven't been specified.
        * Calls Zappa correctly for creates vs. updates.
        """
        old_stdout = sys.stderr

        try:
            zappa_cli = ZappaCLI()
            zappa_cli.domain = "test.example.com"
            try:
                zappa_cli.certify()
            except AttributeError:
                # Since zappa_cli.zappa isn't initialized, the certify() call
                # fails when it tries to inspect what Zappa has deployed.
                pass

            # Set up a core.Zappa mock and let us save some state about
            # domains and lambdas
            zappa_mock = mock.create_autospec(Zappa)
            zappa_mock.function_versions = []
            zappa_mock.domain_names = {}

            def get_lambda_function_versions(_function_name, *_args, **_kwargs):
                return zappa_mock.function_versions

            def get_domain_name(domain, *_args, **_kwargs):
                return zappa_mock.domain_names.get(domain)

            zappa_mock.get_domain_name.side_effect = get_domain_name
            zappa_mock.get_lambda_function_versions.side_effect = (
                get_lambda_function_versions
            )

            zappa_cli.zappa = zappa_mock
            self.assertRaises(ClickException, zappa_cli.certify)

            # Make sure we get an error if we don't configure the domain.
            zappa_cli.zappa.function_versions = ["$LATEST"]
            zappa_cli.api_stage = "stage"
            zappa_cli.zappa_settings = {"stage": {}}
            zappa_cli.api_stage = "stage"
            zappa_cli.domain = "test.example.com"

            try:
                zappa_cli.certify()
            except ClickException as e:
                log_output = str(e)
                self.assertIn("Can't certify a domain without", log_output)
                self.assertIn("domain", log_output)

            # Without any LetsEncrypt settings, we should get a message about
            # not having a lets_encrypt_key setting.
            zappa_cli.zappa_settings["stage"]["domain"] = "test.example.com"
            try:
                zappa_cli.certify()
                self.fail("Expected a ClickException")
            except ClickException as e:
                log_output = str(e)
                self.assertIn("Can't certify a domain without", log_output)
                self.assertIn("lets_encrypt_key", log_output)

            # With partial settings, we should get a message about not having
            # certificate, certificate_key, and certificate_chain
            zappa_cli.zappa_settings["stage"]["certificate"] = "foo"
            try:
                zappa_cli.certify()
                self.fail("Expected a ClickException")
            except ClickException as e:
                log_output = str(e)
                self.assertIn("Can't certify a domain without", log_output)
                self.assertIn("certificate_key", log_output)
                self.assertIn("certificate_chain", log_output)

            zappa_cli.zappa_settings["stage"]["certificate_key"] = "key"
            try:
                zappa_cli.certify()
                self.fail("Expected a ClickException")
            except ClickException as e:
                log_output = str(e)
                self.assertIn("Can't certify a domain without", log_output)
                self.assertIn("certificate_key", log_output)
                self.assertIn("certificate_chain", log_output)

            zappa_cli.zappa_settings["stage"]["certificate_chain"] = "chain"
            del zappa_cli.zappa_settings["stage"]["certificate_key"]
            try:
                zappa_cli.certify()
                self.fail("Expected a ClickException")
            except ClickException as e:
                log_output = str(e)
                self.assertIn("Can't certify a domain without", log_output)
                self.assertIn("certificate_key", log_output)
                self.assertIn("certificate_chain", log_output)

            # With all certificate settings, make sure Zappa's domain calls
            # are executed.
            cert_file = tempfile.NamedTemporaryFile()
            cert_file.write(b"Hello world")
            cert_file.flush()

            zappa_cli.zappa_settings["stage"].update(
                {
                    "certificate": cert_file.name,
                    "certificate_key": cert_file.name,
                    "certificate_chain": cert_file.name,
                }
            )
            sys.stdout.truncate(0)
            zappa_cli.certify()
            zappa_cli.zappa.create_domain_name.assert_called_once()
            zappa_cli.zappa.update_route53_records.assert_called_once()
            zappa_cli.zappa.update_domain_name.assert_not_called()
            log_output = sys.stdout.getvalue()
            self.assertIn("Created a new domain name", log_output)

            zappa_cli.zappa.reset_mock()
            zappa_cli.zappa.domain_names["test.example.com"] = "*.example.com"
            sys.stdout.truncate(0)
            zappa_cli.certify()
            zappa_cli.zappa.update_domain_name.assert_called_once()
            zappa_cli.zappa.update_route53_records.assert_not_called()
            zappa_cli.zappa.create_domain_name.assert_not_called()
            log_output = sys.stdout.getvalue()
            self.assertNotIn("Created a new domain name", log_output)

            # Test creating domain without Route53
            zappa_cli.zappa_settings["stage"].update(
                {
                    "route53_enabled": False,
                }
            )
            zappa_cli.zappa.reset_mock()
            zappa_cli.zappa.domain_names["test.example.com"] = ""
            sys.stdout.truncate(0)
            zappa_cli.certify()
            zappa_cli.zappa.create_domain_name.assert_called_once()
            zappa_cli.zappa.update_route53_records.assert_not_called()
            zappa_cli.zappa.update_domain_name.assert_not_called()
            log_output = sys.stdout.getvalue()
            self.assertIn("Created a new domain name", log_output)
        finally:
            sys.stdout = old_stdout

    @mock.patch("troposphere.Template")
    @mock.patch("botocore.client")
    def test_get_domain_respects_route53_setting(self, client, template):
        zappa_core = Zappa(
            boto_session=mock.Mock(),
            profile_name="test",
            aws_region="test",
            load_credentials=False,
        )
        zappa_core.apigateway_client = mock.Mock()
        zappa_core.route53 = mock.Mock()

        # Check it returns valid and exits early
        record = zappa_core.get_domain_name("test_domain", route53=False)
        self.assertIsNotNone(record)
        zappa_core.apigateway_client.get_domain_name.assert_called_once()
        zappa_core.route53.list_hosted_zones.assert_not_called()

        zappa_core.apigateway_client.reset_mock()
        zappa_core.route53.reset_mock()

        # And that the route53 path still works
        zappa_core.route53.list_hosted_zones.return_value = {
            "IsTruncated": False,
            "HostedZones": [{"Id": "somezone"}],
        }
        zappa_core.route53.list_resource_record_sets.return_value = {
            "ResourceRecordSets": [{"Type": "CNAME", "Name": "test_domain1"}]
        }

        record = zappa_core.get_domain_name("test_domain")
        self.assertIsNotNone(record)
        zappa_core.apigateway_client.get_domain_name.assert_called_once()
        zappa_core.route53.list_hosted_zones.assert_called_once()
        zappa_core.route53.list_resource_record_sets.assert_called_once_with(
            HostedZoneId="somezone"
        )

    @mock.patch("botocore.client")
    def test_get_all_zones_normal_case(self, client):
        zappa_core = Zappa(
            boto_session=mock.Mock(),
            profile_name="test",
            aws_region="test",
            load_credentials=False,
        )
        zappa_core.route53 = mock.Mock()

        # Check that it handle the normal case
        zappa_core.route53.list_hosted_zones.return_value = {
            "IsTruncated": False,
            "HostedZones": [{"Id": "somezone"}],
        }

        zones = zappa_core.get_all_zones()
        zappa_core.route53.list_hosted_zones.assert_called_with(MaxItems="100")
        self.assertListEqual(zones["HostedZones"], [{"Id": "somezone"}])

    @mock.patch("botocore.client")
    def test_get_all_zones_two_pages(self, client):
        zappa_core = Zappa(
            boto_session=mock.Mock(),
            profile_name="test",
            aws_region="test",
            load_credentials=False,
        )
        zappa_core.route53 = mock.Mock()

        # Check that it handle the normal case
        zappa_core.route53.list_hosted_zones.side_effect = [
            {
                "IsTruncated": True,
                "HostedZones": [{"Id": "zone1"}],
                "NextMarker": "101",
            },
            {"IsTruncated": False, "HostedZones": [{"Id": "zone2"}]},
        ]

        zones = zappa_core.get_all_zones()
        zappa_core.route53.list_hosted_zones.assert_has_calls(
            [
                mock.call(MaxItems="100"),
                mock.call(MaxItems="100", Marker="101"),
            ]
        )
        self.assertListEqual(zones["HostedZones"], [{"Id": "zone1"}, {"Id": "zone2"}])

    ##
    # Django
    ##

    def test_detect_dj(self):
        # Sanity
        settings_modules = detect_django_settings()

    def test_dj_wsgi(self):
        # Sanity
        settings_modules = detect_django_settings()

        settings = """
# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os
BASE_DIR = os.path.dirname(os.path.dirname(__file__))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.7/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'alskdfjalsdkf=0*%do-ayvy*m2k=vss*$7)j8q!@u0+d^na7mi2(^!l!d'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

TEMPLATE_DEBUG = True

ALLOWED_HOSTS = []

# Application definition

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
)

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
)

ROOT_URLCONF = 'blah.urls'
WSGI_APPLICATION = 'hackathon_starter.wsgi.application'

# Database
# https://docs.djangoproject.com/en/1.7/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

# Internationalization
# https://docs.djangoproject.com/en/1.7/topics/i18n/

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True
        """

        djts = open("dj_test_settings.py", "w")
        djts.write(settings)
        djts.close()

        app = get_django_wsgi("dj_test_settings")
        try:
            os.remove("dj_test_settings.py")
            os.remove("dj_test_settings.pyc")
        except Exception as e:
            pass

    ##
    # Util / Misc
    ##

    def test_human_units(self):
        human_size(1)
        human_size(9999999999999)

    def test_string_to_timestamp(self):
        boo = string_to_timestamp("asdf")
        self.assertTrue(boo == 0)

        yay = string_to_timestamp("1h")
        self.assertTrue(type(yay) == int)
        self.assertTrue(yay > 0)

        yay = string_to_timestamp("4m")
        self.assertTrue(type(yay) == int)
        self.assertTrue(yay > 0)

        yay = string_to_timestamp("1mm")
        self.assertTrue(type(yay) == int)
        self.assertTrue(yay > 0)

        yay = string_to_timestamp("1mm1w1d1h1m1s1ms1us")
        self.assertTrue(type(yay) == int)
        self.assertTrue(yay > 0)

    def test_event_name(self):
        zappa = Zappa()
        truncated = zappa.get_event_name(
            "basldfkjalsdkfjalsdkfjaslkdfjalsdkfjadlsfkjasdlfkjasdlfkjasdflkjasdf-asdfasdfasdfasdfasdf",
            "this.is.my.dang.function.wassup.yeah.its.long",
        )
        self.assertTrue(len(truncated) <= 64)
        self.assertTrue(
            truncated.endswith("this.is.my.dang.function.wassup.yeah.its.long")
        )
        truncated = zappa.get_event_name(
            "basldfkjalsdkfjalsdkfjaslkdfjalsdkfjadlsfkjasdlfkjasdlfkjasdflkjasdf-asdfasdfasdfasdfasdf",
            "thisidoasdfaljksdfalskdjfalsdkfjasldkfjalsdkfjalsdkfjalsdfkjalasdfasdfasdfasdklfjasldkfjalsdkjfaslkdfjasldkfjasdflkjdasfskdj",
        )
        self.assertTrue(len(truncated) <= 64)
        truncated = zappa.get_event_name("a", "b")
        self.assertTrue(len(truncated) <= 64)
        self.assertEqual(truncated, "a-b")

    def test_hashed_rule_name(self):
        zappa = Zappa()
        truncated = zappa.get_event_name(
            "basldfkjalsdkfjalsdkfjaslkdfjalsdkfjadlsfkjasdlfkjasdlfkjasdflkjasdf-asdfasdfasdfasdfasdf",
            "this.is.my.dang.function.wassup.yeah.its.long",
        )
        self.assertTrue(len(truncated) == 64)

        rule_name = zappa.get_hashed_rule_name(
            event=dict(name="some-event-name"),
            function="this.is.my.dang.function.wassup.yeah.its.long",
            lambda_name="basldfkjalsdkfjalsdkfjaslkdfjalsdkfjadlsfkjasdlfkjasdlfkjasdflkjasdf-asdfasdfasdfasdfasdf",
        )
        self.assertTrue(len(rule_name) <= 64)
        self.assertTrue(
            rule_name.endswith("-this.is.my.dang.function.wassup.yeah.its.long")
        )

    def test_detect_dj(self):
        # Sanity
        settings_modules = detect_django_settings()

    def test_detect_flask(self):
        # Sanity
        settings_modules = detect_flask_apps()

    def test_shameless(self):
        shamelessly_promote()

    def test_s3_url_parser(self):
        remote_bucket, remote_file = parse_s3_url(
            "s3://my-project-config-files/filename.json"
        )
        self.assertEqual(remote_bucket, "my-project-config-files")
        self.assertEqual(remote_file, "filename.json")

        remote_bucket, remote_file = parse_s3_url("s3://your-bucket/account.key")
        self.assertEqual(remote_bucket, "your-bucket")
        self.assertEqual(remote_file, "account.key")

        remote_bucket, remote_file = parse_s3_url(
            "s3://my-config-bucket/super-secret-config.json"
        )
        self.assertEqual(remote_bucket, "my-config-bucket")
        self.assertEqual(remote_file, "super-secret-config.json")

        remote_bucket, remote_file = parse_s3_url("s3://your-secure-bucket/account.key")
        self.assertEqual(remote_bucket, "your-secure-bucket")
        self.assertEqual(remote_file, "account.key")

        remote_bucket, remote_file = parse_s3_url(
            "s3://your-bucket/subfolder/account.key"
        )
        self.assertEqual(remote_bucket, "your-bucket")
        self.assertEqual(remote_file, "subfolder/account.key")

        # Sad path
        remote_bucket, remote_file = parse_s3_url("/dev/null")
        self.assertEqual(remote_bucket, "")

    def test_remote_env_package(self):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "deprecated_remote_env"
        zappa_cli.load_settings("test_settings.json")
        self.assertEqual("lmbda-env", zappa_cli.stage_config["remote_env_bucket"])
        self.assertEqual("dev/env.json", zappa_cli.stage_config["remote_env_file"])
        zappa_cli.create_package()
        with zipfile.ZipFile(zappa_cli.zip_path, "r") as lambda_zip:
            content = lambda_zip.read("zappa_settings.py")
        zappa_cli.remove_local_zip()
        # m = re.search("REMOTE_ENV='(.*)'", content)
        # self.assertEqual(m.group(1), 's3://lmbda-env/dev/env.json')

        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "remote_env"
        zappa_cli.load_settings("test_settings.json")
        self.assertEqual(
            "s3://lmbda-env/prod/env.json", zappa_cli.stage_config["remote_env"]
        )
        zappa_cli.create_package()
        with zipfile.ZipFile(zappa_cli.zip_path, "r") as lambda_zip:
            content = lambda_zip.read("zappa_settings.py")
        zappa_cli.remove_local_zip()
        # m = re.search("REMOTE_ENV='(.*)'", content)
        # self.assertEqual(m.group(1), 's3://lmbda-env/prod/env.json')

    def test_package_only(self):

        for delete_local_zip in [True, False]:
            zappa_cli = ZappaCLI()
            if delete_local_zip:
                zappa_cli.api_stage = "build_package_only_delete_local_zip_true"
            else:
                zappa_cli.api_stage = "build_package_only_delete_local_zip_false"
            zappa_cli.load_settings("test_settings.json")
            zappa_cli.package()
            zappa_cli.on_exit()  # simulate the command exits
            # the zip should never be removed
            self.assertEqual(os.path.isfile(zappa_cli.zip_path), True)

            # cleanup
            os.remove(zappa_cli.zip_path)

    def test_package_output(self):

        for delete_local_zip in [True]:
            zappa_cli = ZappaCLI()
            if delete_local_zip:
                zappa_cli.api_stage = "build_package_only_delete_local_zip_true"
            zappa_cli.load_settings("test_settings.json")
            zappa_cli.package(output="oh-boy.zip")
            zappa_cli.on_exit()  # simulate the command exits
            # the zip should never be removed
            self.assertEqual(os.path.isfile(zappa_cli.zip_path), True)

            # cleanup
            os.remove(zappa_cli.zip_path)

    def test_package_does_not_load_credentials(self):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "ttt888"

        with mock.patch("zappa.core.Zappa.load_credentials") as LoadCredentialsMock:
            # load_credentials is set in ZappaCLI.handler; simulates 'zappa package'
            zappa_cli.load_credentials = False
            zappa_cli.load_settings("test_settings.json")
            zappa_cli.package()
            zappa_cli.on_exit()  # simulate the command exits

            # credentials should not be loaded for package command
            self.assertFalse(zappa_cli.load_credentials)
            self.assertFalse(LoadCredentialsMock.called)

        # cleanup
        os.remove(zappa_cli.zip_path)

    def test_flask_logging_bug(self):
        """
        This checks whether Flask can write errors sanely.
        https://github.com/Miserlou/Zappa/issues/283
        """
        event = {
            "body": {},
            "headers": {},
            "pathParameters": {},
            "path": "/",
            "httpMethod": "GET",
            "queryStringParameters": {},
            "requestContext": {},
        }

        old_stderr = sys.stderr
        sys.stderr = BytesIO()
        try:
            environ = create_wsgi_request(event)
            app = flask.Flask(__name__)
            with app.request_context(environ):
                app.logger.error("This is a test")
                log_output = sys.stderr.getvalue()
        finally:
            sys.stderr = old_stderr

    def test_slim_handler(self):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "slim_handler"
        zappa_cli.load_settings("test_settings.json")
        zappa_cli.create_package()

        self.assertTrue(os.path.isfile(zappa_cli.handler_path))
        self.assertTrue(os.path.isfile(zappa_cli.zip_path))

        zappa_cli.remove_local_zip()

    def test_validate_name(self):
        fname = "tests/name_scenarios.json"
        with open(fname, "r") as f:
            scenarios = json.load(f)
        for scenario in scenarios:
            value = scenario["value"]
            is_valid = scenario["is_valid"]
            if is_valid:
                assert validate_name(value)
            else:
                with self.assertRaises(InvalidAwsLambdaName) as exc:
                    validate_name(value)

    def test_contains_python_files_or_subdirs(self):
        self.assertTrue(contains_python_files_or_subdirs("tests/data"))
        self.assertTrue(contains_python_files_or_subdirs("tests/data/test2"))
        self.assertFalse(contains_python_files_or_subdirs("tests/data/test1"))

    def test_conflicts_with_a_neighbouring_module(self):
        self.assertTrue(conflicts_with_a_neighbouring_module("tests/data/test1"))
        self.assertFalse(conflicts_with_a_neighbouring_module("tests/data/test2"))

    def test_settings_py_generation(self):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "ttt888"
        zappa_cli.load_settings("test_settings.json")
        zappa_cli.create_package()
        with zipfile.ZipFile(zappa_cli.zip_path, "r") as lambda_zip:
            content = lambda_zip.read("zappa_settings.py").decode("utf-8")
            settings = {}
            exec(content, globals(), settings)

            # validate environment variables
            self.assertIn("ENVIRONMENT_VARIABLES", settings)
            self.assertEqual(
                settings["ENVIRONMENT_VARIABLES"]["TEST_ENV_VAR"], "test_value"
            )

            # validate Context header mappings
            self.assertIn("CONTEXT_HEADER_MAPPINGS", settings)
            self.assertEqual(
                settings["CONTEXT_HEADER_MAPPINGS"]["CognitoIdentityId"],
                "identity.cognitoIdentityId",
            )
            self.assertEqual(settings["CONTEXT_HEADER_MAPPINGS"]["APIStage"], "stage")

        zappa_cli.remove_local_zip()

    def test_only_ascii_env_var_allowed(self):
        zappa_cli = ZappaCLI()
        zappa_cli.api_stage = "ttt888"
        zappa_cli.load_settings("tests/test_non_ascii_environment_var_key.json")
        with self.assertRaises(ValueError) as context:
            zappa_cli.create_package()
        self.assertEqual(
            "Environment variable keys must be ascii.", str(context.exception)
        )

    def test_titlecase_keys(self):
        raw = {
            "hOSt": "github.com",
            "ConnECtiOn": "keep-alive",
            "UpGRAde-InSecuRE-ReQueSts": "1",
            "uSer-AGEnT": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36",
            "cONtENt-TYPe": "text/html; charset=utf-8",
            "aCCEpT": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "ACcePT-encoDInG": "gzip, deflate, br",
            "AcCEpT-lAnGUagE": "en-US,en;q=0.9",
        }
        transformed = titlecase_keys(raw)
        expected = {
            "Host": "github.com",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36",
            "Content-Type": "text/html; charset=utf-8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9",
        }
        self.assertEqual(expected, transformed)

    def test_is_valid_bucket_name(self):
        # Bucket names must be at least 3 and no more than 63 characters long.
        self.assertFalse(is_valid_bucket_name("ab"))
        self.assertFalse(
            is_valid_bucket_name(
                "abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefhijlmn"
            )
        )
        # Bucket names must not contain uppercase characters or underscores.
        self.assertFalse(is_valid_bucket_name("aaaBaaa"))
        self.assertFalse(is_valid_bucket_name("aaa_aaa"))
        # Bucket names must start with a lowercase letter or number.
        self.assertFalse(is_valid_bucket_name(".abbbaba"))
        self.assertFalse(is_valid_bucket_name("abbaba."))
        self.assertFalse(is_valid_bucket_name("-abbaba"))
        self.assertFalse(is_valid_bucket_name("ababab-"))
        # Bucket names must be a series of one or more labels. Adjacent labels are separated by a single period (.).
        # Each label must start and end with a lowercase letter or a number.
        self.assertFalse(is_valid_bucket_name("aaa..bbbb"))
        self.assertFalse(is_valid_bucket_name("aaa.-bbb.ccc"))
        self.assertFalse(is_valid_bucket_name("aaa-.bbb.ccc"))
        # Bucket names must not be formatted as an IP address (for example, 192.168.5.4).
        self.assertFalse(is_valid_bucket_name("192.168.5.4"))
        self.assertFalse(is_valid_bucket_name("127.0.0.1"))
        self.assertFalse(is_valid_bucket_name("255.255.255.255"))

        self.assertTrue(is_valid_bucket_name("valid-formed-s3-bucket-name"))
        self.assertTrue(is_valid_bucket_name("worst.bucket.ever"))

    # TODO: encountered error when vpc_config["SubnetIds"] or vpc_config["SecurityGroupIds"] is missing
    # We need to make the code more robust in this case and avoid the KeyError
    def test_zappa_core_deploy_lambda_alb_missing_cert_arn(self):
        kwargs = {
            "lambda_arn": "adatok",
            "lambda_name": "test",
            "alb_vpc_config": {
                "SubnetIds": [],
                "SecurityGroupIds": [],
                "CertificateArn": None,
            },
            "timeout": "30",
        }

        zappa_core = Zappa(
            boto_session=mock.Mock(),
            profile_name="test",
            aws_region="test",
            load_credentials=False,
        )

        with self.assertRaises(EnvironmentError) as context:
            zappa_core.deploy_lambda_alb(**kwargs)

    def test_zappa_core_deploy_lambda_alb(self):
        kwargs = {
            "lambda_arn": str(uuid.uuid4()),
            "lambda_name": str(uuid.uuid4()),
            "alb_vpc_config": {
                "SubnetIds": [],
                "SecurityGroupIds": [],
                "CertificateArn": str(uuid.uuid4()),
            },
            "timeout": "30",
        }

        zappa_core = Zappa(
            boto_session=mock.Mock(),
            profile_name="test",
            aws_region="test",
            load_credentials=False,
        )
        zappa_core.elbv2_client = botocore.session.get_session().create_client("elbv2")
        zappa_core.lambda_client = botocore.session.get_session().create_client(
            "lambda"
        )
        elbv2_stubber = botocore.stub.Stubber(zappa_core.elbv2_client)
        lambda_stubber = botocore.stub.Stubber(zappa_core.lambda_client)

        loadbalancer_arn = str(uuid.uuid4())
        targetgroup_arn = str(uuid.uuid4())

        elbv2_stubber.add_response(
            "create_load_balancer",
            expected_params={
                "Name": kwargs["lambda_name"],
                "Subnets": kwargs["alb_vpc_config"]["SubnetIds"],
                "SecurityGroups": kwargs["alb_vpc_config"]["SecurityGroupIds"],
                "Scheme": "internet-facing",
                "Type": "application",
                "IpAddressType": "ipv4",
            },
            service_response={
                "LoadBalancers": [
                    {
                        "LoadBalancerArn": loadbalancer_arn,
                        "DNSName": "test",
                        "VpcId": "test",
                        "State": {"Code": "OK"},
                    }
                ]
            },
        )
        elbv2_stubber.add_response(
            "describe_load_balancers",
            expected_params={
                "LoadBalancerArns": [loadbalancer_arn],
            },
            service_response={
                "LoadBalancers": [
                    {"LoadBalancerArn": loadbalancer_arn, "State": {"Code": "active"}}
                ]
            },
        )
        elbv2_stubber.add_response(
            "modify_load_balancer_attributes",
            expected_params={
                "LoadBalancerArn": loadbalancer_arn,
                "Attributes": [
                    {"Key": "idle_timeout.timeout_seconds", "Value": kwargs["timeout"]}
                ],
            },
            service_response={
                "Attributes": [
                    {"Key": "idle_timeout.timeout_seconds", "Value": kwargs["timeout"]}
                ]
            },
        )

        elbv2_stubber.add_response(
            "create_target_group",
            expected_params={
                "Name": kwargs["lambda_name"],
                "TargetType": "lambda",
            },
            service_response={
                "TargetGroups": [
                    {
                        "TargetGroupArn": targetgroup_arn,
                    }
                ]
            },
        )
        elbv2_stubber.add_response(
            "modify_target_group_attributes",
            expected_params={
                "TargetGroupArn": targetgroup_arn,
                "Attributes": [
                    {"Key": "lambda.multi_value_headers.enabled", "Value": "true"}
                ],
            },
            service_response={
                "Attributes": [
                    {"Key": "lambda.multi_value_headers.enabled", "Value": "true"}
                ],
            },
        )

        lambda_stubber.add_response(
            "add_permission",
            expected_params={
                "Action": "lambda:InvokeFunction",
                "FunctionName": "{}:{}".format(kwargs["lambda_arn"], ALB_LAMBDA_ALIAS),
                "Principal": "elasticloadbalancing.amazonaws.com",
                "SourceArn": targetgroup_arn,
                "StatementId": kwargs["lambda_name"],
            },
            service_response={},
        )
        elbv2_stubber.add_response(
            "register_targets",
            expected_params={
                "TargetGroupArn": targetgroup_arn,
                "Targets": [
                    {"Id": "{}:{}".format(kwargs["lambda_arn"], ALB_LAMBDA_ALIAS)}
                ],
            },
            service_response={},
        )
        elbv2_stubber.add_response(
            "create_listener",
            expected_params={
                "Certificates": [
                    {
                        "CertificateArn": kwargs["alb_vpc_config"]["CertificateArn"],
                    }
                ],
                "DefaultActions": [
                    {
                        "Type": "forward",
                        "TargetGroupArn": targetgroup_arn,
                    }
                ],
                "LoadBalancerArn": loadbalancer_arn,
                "Protocol": "HTTPS",
                "Port": 443,
            },
            service_response={},
        )
        lambda_stubber.activate()
        elbv2_stubber.activate()
        zappa_core.deploy_lambda_alb(**kwargs)

    def test_zappa_core_undeploy_lambda_alb(self):
        kwargs = {
            "lambda_name": str(uuid.uuid4()),
        }

        zappa_core = Zappa(
            boto_session=mock.Mock(),
            profile_name="test",
            aws_region="test",
            load_credentials=False,
        )
        zappa_core.elbv2_client = botocore.session.get_session().create_client("elbv2")
        zappa_core.lambda_client = botocore.session.get_session().create_client(
            "lambda"
        )
        elbv2_stubber = botocore.stub.Stubber(zappa_core.elbv2_client)
        lambda_stubber = botocore.stub.Stubber(zappa_core.lambda_client)

        loadbalancer_arn = str(uuid.uuid4())
        listener_arn = str(uuid.uuid4())
        function_arn = str(uuid.uuid4())
        targetgroup_arn = str(uuid.uuid4())

        lambda_stubber.add_response(
            "remove_permission",
            expected_params={
                "FunctionName": kwargs["lambda_name"],
                "StatementId": kwargs["lambda_name"],
            },
            service_response={},
        )
        elbv2_stubber.add_response(
            "describe_load_balancers",
            expected_params={
                "Names": [kwargs["lambda_name"]],
            },
            service_response={
                "LoadBalancers": [
                    {
                        "LoadBalancerArn": loadbalancer_arn,
                    }
                ]
            },
        )
        elbv2_stubber.add_response(
            "describe_listeners",
            expected_params={
                "LoadBalancerArn": loadbalancer_arn,
            },
            service_response={
                "Listeners": [
                    {
                        "ListenerArn": listener_arn,
                    }
                ]
            },
        )
        elbv2_stubber.add_response(
            "delete_listener",
            expected_params={
                "ListenerArn": listener_arn,
            },
            service_response={},
        )
        elbv2_stubber.add_response(
            "delete_load_balancer",
            expected_params={
                "LoadBalancerArn": loadbalancer_arn,
            },
            service_response={},
        )
        elbv2_stubber.add_client_error(
            "describe_load_balancers",
            service_error_code="LoadBalancerNotFound",
        )
        lambda_stubber.add_response(
            "get_function",
            expected_params={
                "FunctionName": kwargs["lambda_name"],
            },
            service_response={"Configuration": {"FunctionArn": function_arn}},
        )
        elbv2_stubber.add_response(
            "describe_target_groups",
            expected_params={
                "Names": [kwargs["lambda_name"]],
            },
            service_response={
                "TargetGroups": [{"TargetGroupArn": targetgroup_arn}],
            },
        )
        elbv2_stubber.add_response(
            "deregister_targets",
            service_response={},
        )
        elbv2_stubber.add_client_error(
            "describe_target_health",
            service_error_code="InvalidTarget",
        )
        elbv2_stubber.add_response(
            "delete_target_group",
            expected_params={
                "TargetGroupArn": targetgroup_arn,
            },
            service_response={},
        )
        lambda_stubber.activate()
        elbv2_stubber.activate()
        zappa_core.undeploy_lambda_alb(**kwargs)

    @mock.patch("botocore.client")
    def test_set_lambda_concurrency(self, client):
        boto_mock = mock.MagicMock()
        zappa_core = Zappa(
            boto_session=boto_mock,
            profile_name="test",
            aws_region="test",
            load_credentials=True,
        )
        zappa_core.lambda_client.create_function.return_value = {
            "FunctionArn": "abc",
            "Version": 1,
        }
        access_logging_patch = zappa_core.create_lambda_function(
            concurrency=5,
        )
        boto_mock.client().put_function_concurrency.assert_called_with(
            FunctionName="abc",
            ReservedConcurrentExecutions=5,
        )

    @mock.patch("botocore.client")
    def test_update_lambda_concurrency(self, client):
        boto_mock = mock.MagicMock()
        zappa_core = Zappa(
            boto_session=boto_mock,
            profile_name="test",
            aws_region="test",
            load_credentials=True,
        )
        zappa_core.lambda_client.create_function.return_value = {
            "FunctionArn": "abc",
            "Version": 1,
        }
        access_logging_patch = zappa_core.update_lambda_function(
            bucket="test",
            function_name="abc",
            concurrency=5,
        )
        boto_mock.client().put_function_concurrency.assert_called_with(
            FunctionName="abc",
            ReservedConcurrentExecutions=5,
        )
        boto_mock.client().delete_function_concurrency.assert_not_called()

    @mock.patch("botocore.client")
    def test_delete_lambda_concurrency(self, client):
        boto_mock = mock.MagicMock()
        zappa_core = Zappa(
            boto_session=boto_mock,
            profile_name="test",
            aws_region="test",
            load_credentials=True,
        )
        zappa_core.lambda_client.create_function.return_value = {
            "FunctionArn": "abc",
            "Version": 1,
        }
        access_logging_patch = zappa_core.update_lambda_function(
            bucket="test",
            function_name="abc",
        )
        boto_mock.client().put_function_concurrency.assert_not_called()
        boto_mock.client().delete_function_concurrency.assert_called_with(
            FunctionName="abc",
        )


if __name__ == "__main__":
    unittest.main()
