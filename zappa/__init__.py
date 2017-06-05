
import sys

SUPPORTED_VERSIONS = [(2, 7), (3, 6)]

python_major_version = sys.version_info[0]
python_minor_version = sys.version_info[1]

if (python_major_version, python_minor_version) not in SUPPORTED_VERSIONS:
    formatted_supported_versions = ['{}.{}'.format(mav, miv) for mav, miv in SUPPORTED_VERSIONS]
    err_msg = 'This version of Python ({}.{}) is not supported!\n'.format(python_major_version, python_minor_version) +\
              'Zappa (and AWS Lambda) support the following versions of Python: {}'.format(formatted_supported_versions)
    raise RuntimeError(err_msg)
