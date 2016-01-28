import os
import sys
from setuptools import setup

# Set external files
try:
    from pypandoc import convert
    README = convert('README.md', 'rst')     
except ImportError:
    README = open(os.path.join(os.path.dirname(__file__), 'README.md')).read()

with open(os.path.join(os.path.dirname(__file__), 'requirements.txt')) as f:
    required = f.read().splitlines()

setup(
    name='zappa',
    version='0.5.0',
    packages=['zappa'],
    install_requires=required,  
    include_package_data=True,
    license='MIT License',
    description='Serverless WSGI With AWS Lambda + API Gateway',
    long_description=README,
    url='https://github.com/Miserlou/Zappa',
    author='Rich Jones',
    author_email='rich@openwatch.net',
    classifiers=[
        'Environment :: Console',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)
