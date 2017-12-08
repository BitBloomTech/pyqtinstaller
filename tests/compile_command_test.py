import pytest

from setuptools import Distribution

from pyqtinstaller import CompileCommand

def test_assertion_error_if_qmake_path_not_provided():
    with pytest.raises(AssertionError):
        CompileCommand(Distribution()).finalize_options()