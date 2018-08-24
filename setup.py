from setuptools import setup

setup(
    name='pyqtinstaller',
    version='0.2.2',
    packages=['pyqtinstaller'],
    install_requires=['jinja2', 'pyqtdeploy'],
    extras_require={
        'dev': ['tox']
    },
    entry_points={
        'distutils.commands': [
            'compile = pyqtinstaller:CompileCommand'
        ]
    },
    package_data={
        'pyqtinstaller': ['*.jinja']
    }
)
