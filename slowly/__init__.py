import importlib.metadata

__title__ = "slowly"
__author__ = "tiagovla"
__license__ = "GPL-3.0-or-later"
__version__ = importlib.metadata.version("slowly.py")

import logging

from .client import Client

__all__ = ["Client"]

from logging import NullHandler

logging.getLogger(__name__).addHandler(NullHandler())

del logging
