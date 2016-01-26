import glob
import os
import re
import string
import sys
import unittest

import nose
from nose import case
from nose.pyversion import unbound_method
from nose import util

class TestZappa(unittest.TestCase):

    ##
    # Basic Tests
    ##

    def test_test(self):
        self.assertTrue(True)

if __name__ == '__main__':
    unittest.main()
