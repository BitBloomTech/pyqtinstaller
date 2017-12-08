from setuptools import setup

setup(
    name='pyqtinstaller',
    version='0.1.0',
    packages=['pyqtinstaller'],
    install_requires=['jinja2'],
    setup_requires=['setuptools-lint'],
    entry_points={
        'distutils.commands': [
            'compile = pyqtinstaller:CompileCommand'
        ]
    }
)
