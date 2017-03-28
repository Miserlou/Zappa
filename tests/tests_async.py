# -*- coding: utf8 -*-
import base64
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
from zappa.async import _import_and_get_task, \
                        _get_func_task_path, \
                        route_lambda_task, \
                        route_sns_task, \
                        run, \
                        task

from zappa.cli import ZappaCLI, shamelessly_promote
from zappa.zappa import Zappa, \
                        ASSUME_POLICY, \
                        ATTACH_POLICY

class TestZappa(unittest.TestCase):
    def setUp(self):
        return
    def tearDown(self):
        return

    ##
    # Sanity Tests
    ##

    def test_test(self):
        self.assertTrue(True)
        self.assertFalse(False)

    def test_nofails_classes(self):
        a = AsyncException()
        l = LambdaAsyncResponse()
        # s = SnsAsyncResponse()
        s = SnsAsyncResponse(arn="arn:abc:def")

    def test_nofails_funcs(self):
        funk = _import_and_get_task("tests.test_app.schedule_me")
        _get_func_task_path(funk)

    ##
    # Functional tests
    ##
