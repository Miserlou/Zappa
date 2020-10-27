import sys

SUPPORTED_VERSIONS = [(3, 6), (3, 7), (3, 8)]

if sys.version_info[:2] not in SUPPORTED_VERSIONS:
    formatted_supported_versions = ['{}.{}'.format(*version) for version in SUPPORTED_VERSIONS]
    err_msg = ('This version of Python ({}.{}) is not supported!\n'.format(*sys.version_info) +
               'Zappa (and AWS Lambda) support the following versions of Python: {}'.format(formatted_supported_versions))
    raise RuntimeError(err_msg)

__version__ = '0.52.0'
