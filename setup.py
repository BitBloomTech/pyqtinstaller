from setuptools import setup

setup(
    name='pyqtinstaller',
    version='0.1.0',
    packages=['pyqtinstaller'],
    entry_points={
        'distutils.commands': [
            'compile = pyqtinstaller:CompileCommand'
        ]
    }
)
