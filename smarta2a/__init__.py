"""
py_a2a - A Python package for implementing an A2A server
"""

__version__ = "0.1.0" 

from .server import SmartA2A
from . import types as models

__all__ = ["SmartA2A", "models"]