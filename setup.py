import os
import sys
from setuptools import setup
from io import open
from zappa import __version__

with open('README.md') as readme_file:
    long_description = readme_file.read()

with open(os.path.join(os.path.dirname(__file__), 'requirements.txt')) as f:
    if sys.version_info[0] == 2:
        required = f.read().splitlines()
    else:
        # This logic is intended to prevent the futures package from being installed in python 3 environments
        # as it can cause unexpected syntax errors in other packages. Futures is in the standard library in python 3
        # and is should never be installed in these environments.
        # Related: https://github.com/Miserlou/Zappa/issues/1179
        required = []
        for package in f.read().splitlines():
            if 'futures' not in package:
                required.append(package)

with open(os.path.join(os.path.dirname(__file__), 'test_requirements.txt')) as f:
    test_required = f.read().splitlines()

setup(
    name='zappa',
    version=__version__,
    packages=['zappa'],
    install_requires=required,
    tests_require=test_required,
    test_suite='nose.collector',
    include_package_data=True,
    license='MIT License',
    description='Server-less Python Web Services for AWS Lambda and API Gateway',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/Miserlou/Zappa',
    author='Rich Jones',
    author_email='rich@openwatch.net',
    entry_points={
        'console_scripts': [
            'zappa=zappa.cli:handle',
            'z=zappa.cli:handle',
        ]
    },
    classifiers=[
        'Environment :: Console',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Framework :: Django',
        'Framework :: Django :: 1.11',
        'Framework :: Django :: 2.0',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)
