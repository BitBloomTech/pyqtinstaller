"""pyqtinstaller

This module defines the interface for the pyqtinstaller package
"""
from .compile_command import CompileCommand

from ._version import get_versions
__version__ = get_versions()['version']
del get_versions
