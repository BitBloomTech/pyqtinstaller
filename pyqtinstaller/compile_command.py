"""CompileCommand

This module defines the "compile" command, which will compile an installer from a pyqt5 application
"""
from subprocess import call, check_output
import os
from os import path
from configparser import ConfigParser
import shutil
from distutils.version import StrictVersion
from glob import glob

from setuptools import Command
from jinja2 import Template

def assert_call(cmd, **kwargs):
    """Wraps `subprocess.call` in an assert
    """
    result = call(cmd, **kwargs)
    assert not result, \
        '{} exited with code {} - see output for details'.format(' '.join(cmd), result)

def get_vc_env(vc_dir, platform):
    """Gets the environment variables to be used when compiling using visual studio c++ compiler
    """
    vcvars = check_output(['cmd', '/c', f'vcvarsall.bat {platform}&set'], cwd=vc_dir).decode('utf8')
    vc_env = {}
    for line in vcvars.splitlines():
        name, value = line.split('=')
        vc_env[name] = value
    vc_env['Path'] = '{};{}'.format(get_vc_bin_dir(vc_dir, platform), vc_env['Path'])
    return vc_env

def get_vc_bin_dir(vc_dir, platform):
    """Gets visual c++ compiler binary directory (changes depending on platform)
    """
    bin_dir = 'bin' if platform == 'x86' else path.join('bin', platform)
    return path.join(vc_dir, bin_dir)

def get_version(package):
    """Gets the version of the package we're building
    """
    exec(f'import {package}') #pylint: disable=exec-used
    return eval(f'{package}.__version__') #pylint: disable=eval-used

def get_template(name):
    """Loads a jinja template from the name of the template file
    """
    template_path = path.join(path.realpath(path.dirname(__file__)), f'{name}.jinja')
    with open(template_path) as fp:
        return Template(fp.read())


def get_python_version(python_dir):
    """Gets the version of python that is being used to compile
    """
    version_string = check_output([path.join(python_dir, 'python.exe'), '--version']).decode('utf8')
    version = StrictVersion(version_string.replace('Python', '').strip()).version
    return {'major': version[0], 'minor': version[1], 'patch': version[2]}


class CompileCommand(Command):
    """CompileCommand
    Implements the `Command` interface from `setuptools`
    to compile a windows installer from a pyqt5 application
    """
    #pylint: disable=too-many-instance-attributes
    user_options = [
        ('qmake-path=', None, 'The path to qmake'),
        ('prebuilt-libraries-dir=', None, 'The base directory of the prebuild libraries'),
        ('python-dir=', None, 'The directory containing python'),
        ('vc-dir=', None, 'The path the Visual Studio 2015 VC directory'),
        ('platform=', None, 'The platform to compile for'),
        ('qt-modules=', None, 'The QT modules to compile'),
        ('package=', None, 'The package to compile'),
        ('inno-setup-path=', None, 'The path to inno setup'),
        ('win-console=', None, 'Whether or not the resulting application should use the console')
    ]


    def initialize_options(self):
        """Implementation of `Command` initialize_options
        Loads default options from user configuration
        """
        #pylint: disable=attribute-defined-outside-init
        assert path.exists('setup.cfg'), 'setup.cfg not found'
        with open('setup.cfg') as fp:
            config = ConfigParser()
            config.read_file(fp)
            compile_config = config['compile'] if config.has_section('compile') else {}

        self.qt_modules = compile_config.get('qt_modules', None)

        if path.exists('setup.user.cfg'):
            with open('setup.user.cfg') as fp:
                config = ConfigParser()
                config.read_file(fp)
                user_compile_config = config['compile'] if config.has_section('compile') else {}
        else:
            user_compile_config = {}

        self.qmake_path = user_compile_config.get('qmake_path', None)
        self.vc_dir = user_compile_config.get('vc_dir', None)
        self.platform = user_compile_config.get('platform', 'amd64')
        self.prebuilt_libraries_dir = user_compile_config.get('prebuilt_libraries_dir')
        self.python_dir = user_compile_config.get('python_dir', None)
        self.inno_setup_path = user_compile_config.get('inno_setup_path', None)
        self.package = None
        self.app_name = None
        self.app_icon = None
        self.build_dir = None
        self.resources_dir = None
        self.win_console = False

    def finalize_options(self):
        """Implentation of `Command` finalize_options
        Performs validation on the parameters provided
        """
        #pylint: disable=attribute-defined-outside-init

        # User options
        assert self.qmake_path, 'qmake-path must be provided'
        assert self.vc_dir, 'vc-path must be provided'
        assert self.platform, 'platform must be specified'
        assert self.prebuilt_libraries_dir, 'prebuilt-libraries-dir must be specified'
        assert self.python_dir, 'python-dir must be provided'
        assert self.inno_setup_path, 'inno-setup-path must be provided'
        assert path.isfile(self.qmake_path), 'qmake path does not exist'
        assert path.isdir(self.vc_dir), 'vc directory path does not exist'
        assert self.platform in ['amd64'],\
            f'Platform {self.platform} is not currently supported'
        assert path.isdir(self.prebuilt_libraries_dir),\
            'prebuilt libraries directory does not exist'
        assert path.isdir(self.python_dir), 'python directory could not be found'
        assert path.isfile(self.inno_setup_path), 'inno setup path does not exist'

        # General options
        assert self.qt_modules, 'qt-modules must be specified'
        assert self.package, 'package must be specified'
        assert self.app_name, 'Must provide an app name'
        assert path.isdir(self.package), 'package not found'
        assert not self.resources_dir or path.isdir(self.resources_dir),\
            'Resources directory provided is not a directory'
        self.qt_modules = self.qt_modules.split(',')
        self.win_console =\
            self.win_console.lower() in ['1', 'true', 't', 'yes'] if self.win_console\
            else False

        self.build_dir = self.build_dir or 'build'

        # Installer options
        self.app_config = {
            'app_version': get_version(self.package),
            'exe_filename': f'{self.package}.exe',
            'platform': self.platform,
            'app_name': self.app_name.replace(' ', ''),
            'app_icon': self.app_icon,
            'resources_dir': self.resources_dir
        }

        self._save_compile_user_config()


    def run(self):
        """Runs the command
        Performs the steps required to compile the application and generate an installer
        """
        # Build the package project file
        self._build_project_file()

        # Create the app resources
        self._create_app_resources()

        vc_env = self._get_vc_env()

        # Build the qt project file
        self._run_pyqtdeploy(vc_env)

        # Build the nmake Makefiles
        self._run_qmake(vc_env)

        # Build the exe
        self._run_nmake(vc_env)

        dest = path.join(self.build_dir, 'release')

        # Copy the dlls to the release directory
        self._copy_binaries(dest)

        # Build the installer
        self._build_installer(dest)


    def _build_project_file(self):
        args = {
            'app_name': self.app_name.replace(' ', ''),
            'package': self.package,
            'qt_modules': self.qt_modules,
            'build_dir': self.build_dir,
            'python_version': get_python_version(self.python_dir),
            'win_console': '1' if self.win_console else '0'
        }
        with open(f'{self.package}.pdy', 'w') as fp:
            fp.write(get_template('package.pdy').render(args))


    def _create_app_resources(self):
        app_resource_files = glob(f'{self.package}/**/*.qml', recursive=True)
        args = {
            'files': app_resource_files
        }
        app_resources_dir = path.join(self.build_dir, 'app_resources')
        if not path.isdir(app_resources_dir):
            os.makedirs(app_resources_dir)

        with open(path.join(app_resources_dir, 'app_resources.qrc'), 'w') as fp:
            fp.write(get_template('app_resources.qrc').render(args))
        for resource_file in app_resource_files:
            dest = path.join(self.build_dir, 'app_resources', resource_file)
            if not path.isdir(path.dirname(dest)):
                os.makedirs(path.dirname(dest))
            shutil.copyfile(resource_file, dest)

        other_resource_files = glob(f'{self.resources_dir}/**/*', recursive=True)
        for resource_file in other_resource_files:
            dest = path.join(self.build_dir, 'release', resource_file)
            if not path.isdir(path.dirname(dest)):
                os.makedirs(path.dirname(dest))
            shutil.copyfile(resource_file, dest)


    def _get_vc_env(self):
        vc_env = get_vc_env(self.vc_dir, self.platform)

        vc_env['LIB'] = '{};{};{}'.format(
            ';'.join(self._get_pyqt_lib_paths()),
            self._get_sip_lib_path(),
            vc_env['LIB']
        )

        vc_env['PYTHON_DIR'] = self.python_dir
        return vc_env


    def _run_pyqtdeploy(self, env):
        assert_call(['pyqtdeploycli', self.build_dir, '--project', f'{self.package}.pdy'], env=env)


    def _run_qmake(self, env):
        assert_call([self.qmake_path], cwd=self.build_dir, env=env)


    def _run_nmake(self, env):
        assert_call(
            [path.join(get_vc_bin_dir(self.vc_dir, self.platform), 'nmake')],
            cwd=self.build_dir,
            env=env
        )

    def _build_installer(self, dest):
        setup_script = get_template('setup.iss').render(**self.app_config)

        with open(path.join(dest, 'setup.iss'), 'w') as fp:
            fp.write(setup_script)

        assert_call([self.inno_setup_path, fp.name])

    def _copy_binaries(self, dest):
        for dll_path in self._get_dll_paths():
            shutil.copyfile(dll_path, path.join(dest, path.basename(dll_path)))

    def _save_compile_user_config(self):
        config = ConfigParser()
        if path.exists('setup.user.cfg'):
            with open('setup.user.cfg') as fp:
                config.read_file(fp)

        if 'compile' not in config:
            config['compile'] = {
                'qmake_path': self.qmake_path,
                'vc_dir': self.vc_dir,
                'prebuilt_libraries_dir': self.prebuilt_libraries_dir,
                'platform': self.platform,
                'python_dir': self.python_dir,
                'inno_setup_path': self.inno_setup_path
            }
            with open('setup.user.cfg', 'w') as fp:
                config.write(fp)

    def _get_dll_paths(self):
        pyqt_dlls = [
            path.join(p, f'{m}.dll') for p, m in zip(self._get_pyqt_lib_paths(), self.qt_modules)
        ]
        sip_dll = path.join(self._get_sip_lib_path(), 'sip.pyd')
        qt_dll_base = path.dirname(self.qmake_path)
        qt_dll_modules = self.qt_modules
        if 'QtQuick' in qt_dll_modules:
            qt_dll_modules = qt_dll_modules + ['QtQuickControls2', 'QtQuickTemplates2']
        qt_dlls = [
            path.join(qt_dll_base, m.replace('Qt', 'Qt5') + '.dll')\
                for m in qt_dll_modules if m != 'Qt'
        ]
        python_dlls = [path.join(self.python_dir, f'{d}.dll') for d in ['python3', 'python36']]
        return pyqt_dlls + [sip_dll] + qt_dlls + python_dlls

    def _get_pyqt_lib_paths(self):
        return [
            path.join(
                self.prebuilt_libraries_dir,
                'PyQt5_gpl-5.9.1',
                q,
                'release'
            ) for q in self.qt_modules
        ]

    def _get_sip_lib_path(self):
        return path.join(self.prebuilt_libraries_dir, 'sip-4.19.5', 'siplib')
