from distutils.core import setup
setup(
  name = 'zappa',
  packages = ['zappa'], 
  version = '0.0.1',
  description = 'WSGI Applications on AWS Lambda + API Gateway',
  license='MIT License',
  author='Rich Jones',
  author_email='rich@openwatch.net',
  url='https://github.com/Miserlou/Zappa',
  keywords = ['aws', 'lambda', 'apigateway'], # arbitrary keywords
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)
