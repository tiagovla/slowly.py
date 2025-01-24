__title__ = "tinder"
__author__ = "tiagovla"
__version__ = "0.1.2"
__license__ = "GPL-3.0-or-later"

import logging

from .client import Client

__all__ = ["Client"]

from logging import NullHandler

logging.getLogger(__name__).addHandler(NullHandler())

del logging
