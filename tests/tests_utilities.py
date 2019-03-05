# -*- coding: utf8 -*-
import unittest

from zappa.utilities import merge_headers


class TestZappa(unittest.TestCase):
    #
    # Header merging - see https://github.com/Miserlou/Zappa/pull/1802.
    #
    def test_merge_headers_no_multi_value(self):
        event = {
            'headers': {
                'a': 'b'
            }
        }

        merged = merge_headers(event)
        self.assertEqual(merged['a'], 'b')

    def test_merge_headers_combine_values(self):
        event = {
            'headers': {
                'a': 'b',
                'z': 'q'
            },
            'multiValueHeaders': {
                'a': ['c'],
                'x': ['y']
            }
        }

        merged = merge_headers(event)
        self.assertEqual(merged['a'], 'c, b')
        self.assertEqual(merged['x'], 'y')
        self.assertEqual(merged['z'], 'q')

    def test_merge_headers_no_single_value(self):
        event = {
            'multiValueHeaders': {
                'a': ['c', 'd'],
                'x': ['y', 'z', 'f']
            }
        }
        merged = merge_headers(event)
        self.assertEqual(merged['a'], 'c, d')
        self.assertEqual(merged['x'], 'y, z, f')
