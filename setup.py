from setuptools import setup

setup(
    name='pyqtinstaller',
    version='0.2.8',
    packages=['pyqtinstaller'],
    install_requires=['jinja2', 'pyqtdeploy==1.3.2'],
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
