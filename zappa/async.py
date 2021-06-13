# -*- coding: utf-8 -*-
import warnings

warnings.warn(
    'Module "zappa.async" is deprecated; please use "zappa.asynchronous" instead.',
    category=DeprecationWarning,
)
from .asynchronous import *
