#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import collections
import copy
import json
import os
import random
import string

from munch import Munch
from six import iteritems

__all__ = ['Settings']


SETTINGS_DEFAULT = {
    'api_stage': None,
    'api_key': None,
    'api_key_required': False,
    'project_name': None,
    'lambda_name': None,
    'lambda_description': "Zappa Deployment",
    's3_bucket': "zappa-" + ''.join(
                random.choice(string.ascii_lowercase + string.digits) for _ in range(9)),
    'vpc_config': {},
    'memory_size': 512,
    'app_function': None,
    'aws_region': 'us-east-1',
    'debug': True,
    'prebuild_script': None,
    'profile_name': None,
    'log_level': "DEBUG",
    'domain': None,
    'timeout_seconds': 30,
    'use_apigateway': True,
    'integration_content_type_aliases': {},
    'lambda_handler': 'handler.lambda_handler',
    'remote_env_bucket': None,
    'remote_env_file': None,
    'remove_logs': False,
    'settings_file': None,
    'django_settings': None,
    'manage_roles': True,
    'cloudwatch_log_level': 'OFF',
    'cloudwatch_data_trace': False,
    'cloudwatch_metrics_enabled': False,
    'touch': True,
    'delete_zip': True,
    'keep_warm': True,
    'keep_warm_expression': "rate(5 minutes)",
    'environment_variables': {}
}


class Settings(Munch):
    """

    """

    @classmethod
    def from_file(cls, filename):
        """ Return a new Settings instance from a JSON file.
            Arguments:
                filename  : File name to read.

            All open() and json.load() exceptions are propagated.
        """
        settings = cls()
        if os.path.exists(filename):
            settings.load_json(filename)
        else:
            raise RuntimeError("Settings file does not exist: {}".format(filename))
        return settings

    def load_json(self, filename=None):
        """ Load this dict from a JSON file.
            Raises the same errors as open() and json.load().
        """
        if filename or not self.getattr(self, '_settings_filename', None):
            self._settings_filename = filename

        if not self._settings_filename:
            raise ValueError('`_settings_filename` must be set.')

        with open(self._settings_filename, 'r') as f:
            data = json.load(f)

        if data is None:
            # JSON null.
            data = {}

        if not isinstance(data, dict):
            raise TypeError(
                'Data was replace with non dict type, got: {}'.format(
                    type(data)))

        self.deep_update(data)

    def save_json(self, filename=None, sort_keys=False):
        """ Save this dict to a JSON file.
            Raises the same errors as open() and json.dump().
        """
        if filename or not getattr(self, '_settings_filename', None):
            self._settings_filename = filename

        if not self._settings_filename:
            raise ValueError('`filename` must be set.')

        with open(self._settings_filename, 'w') as f:
            f.write(self.toJSON(indent=4, sort_keys=sort_keys))

    def deep_update(self, other):
        _deep_update(self, other)


def toJSON(self, **options):
    """
    Overrides the builtin Munch toJSON to remove attributes that begin with an '_' from the output
    """
    out = copy.deepcopy(self.toDict())
    for key in out.keys():
        if key.startswith('_'):
            del out[key]
    return json.dumps(out, **options)


Settings.toJSON = toJSON


def _deep_update(source,  overrides):
    """Update source with a nested dictionary or similar mapping.
    Modifies in place.
    """
    # http://stackoverflow.com/questions/3232943/update-value-of-a-nested-dictionary-of-varying-depth  # noqa
    for key, value in iteritems(overrides):
        if isinstance(value, collections.Mapping):
            if isinstance(value, collections.Mapping):
                returned = _deep_update(source.get(key, Munch()), value)
                source[key] = returned
            else:
                source[key] = overrides[key]
        else:
            source[key] = overrides[key]
    return source
