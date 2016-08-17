#!/usr/bin/env python


"""
Setup script for `PrintItBold`
"""


from setuptools import setup


setup(
    name='Zappa Plugin Example',
    version='0.1dev0',
    packages=['zappa_plugin_example'],
    install_requires=[
        'zappa',
    ],
    entry_points='''
        [zappa.plugins]
        example=zappa_plugin_example.core:example
    '''
)