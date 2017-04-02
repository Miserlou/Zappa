# -*- coding: utf8 -*-
import base64
import boto3
import collections
import json
from contextlib import nested

from cStringIO import StringIO as OldStringIO
from io import BytesIO, StringIO
import flask
import mock
import os
import random
import string
import zipfile
import re
import unittest
import shutil
import sys
import tempfile

from click.exceptions import ClickException
from lambda_packages import lambda_packages


from zappa.async import AsyncException, LambdaAsyncResponse, SnsAsyncResponse
from zappa.async import import_and_get_task, \
                        get_func_task_path, \
                        route_lambda_task, \
                        route_sns_task, \
                        run, \
                        task, \
                        is_from_router

from zappa.cli import ZappaCLI, shamelessly_promote
from zappa.zappa import Zappa, \
                        ASSUME_POLICY, \
                        ATTACH_POLICY

class TestZappa(unittest.TestCase):
    def setUp(self):
        self.sleep_patch = mock.patch('time.sleep', return_value=None)
        # Tests expect us-east-1.
        # If the user has set a different region in env variables, we set it aside for now and use us-east-1
        self.users_current_region_name = os.environ.get('AWS_DEFAULT_REGION', None)
        os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
        if not os.environ.get('PLACEBO_MODE') == 'record':
            self.sleep_patch.start()

    def tearDown(self):
        if not os.environ.get('PLACEBO_MODE') == 'record':
            self.sleep_patch.stop()
        del os.environ['AWS_DEFAULT_REGION']
        if self.users_current_region_name is not None:
            # Give the user their AWS region back, we're done testing with us-east-1.
            os.environ['AWS_DEFAULT_REGION'] = self.users_current_region_name

    ##
    # Sanity Tests
    ##

    def test_test(self):
        self.assertTrue(True)
        self.assertFalse(False)

    def test_nofails_classes(self):

        boto_session = boto3.Session(region_name=os.environ['AWS_DEFAULT_REGION'])

        a = AsyncException()
        l = LambdaAsyncResponse(boto_session=boto_session)
        # s = SnsAsyncResponse()
        s = SnsAsyncResponse(arn="arn:abc:def", boto_session=boto_session)

    def test_nofails_funcs(self):
        funk = import_and_get_task("tests.test_app.schedule_me")
        get_func_task_path(funk)
        is_from_router()

    ##
    # Functional tests
    ##
