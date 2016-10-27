import unittest
from zappa.handler import LambdaHandler


def no_args():
    return


def one_arg(first):
    return first


def two_args(first, second):
    return first, second


def var_args(*args):
    return args


def var_args_with_one(first, *args):
    return first, args[0]

def unsupported(first, second, third):
    return first, second, third


class TestZappa(unittest.TestCase):

    def test_run_function(self):
        self.assertIsNone(LambdaHandler.run_function(no_args, 'e', 'c'))
        self.assertEqual(LambdaHandler.run_function(one_arg, 'e', 'c'), 'e')
        self.assertEqual(LambdaHandler.run_function(two_args, 'e', 'c'), ('e', 'c'))
        self.assertEqual(LambdaHandler.run_function(var_args, 'e', 'c'), ('e', 'c'))
        self.assertEqual(LambdaHandler.run_function(var_args_with_one, 'e', 'c'), ('e', 'c'))

        try:
            LambdaHandler.run_function(unsupported, 'e', 'c')
            self.fail('Exception expected')
        except RuntimeError as e:
            pass