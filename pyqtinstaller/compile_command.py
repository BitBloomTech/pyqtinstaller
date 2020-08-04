# pyqttoolkit
# Copyright (C) 2018-2019, Simmovation Ltd.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
"""CompileCommand

This module defines the "compile" command, which will compile an installer from a pyqt5 application
"""
from subprocess import call, check_output
import sys
import os
from os import path
import shutil
from glob import glob
from typing import Sequence
import importlib.util
from datetime import datetime

from setuptools import Command
from jinja2 import Template

def assert_call(cmd: Sequence[str], **kwargs):
    """Wraps `subprocess.call` in an assert
    """
    result = call(cmd, **kwargs)
    assert not result, \
        '{} exited with code {} - see output for details'.format(' '.join(cmd), result)

def get_vc_env(vc_dir: str, platform: str):
    """Gets the environment variables to be used when compiling using visual studio c++ compiler
    """
    vcvars = check_output(['cmd', '/c', f'vcvarsall.bat {platform}&set'], cwd=vc_dir).decode('utf8')
    vc_env = {}
    for line in vcvars.splitlines():
        name, value = line.split('=')
        vc_env[name.upper()] = value
    vc_env['PATH'] = '{};{}'.format(get_vc_bin_dir(vc_dir, platform), vc_env['PATH'])
    return vc_env

def get_vc_bin_dir(vc_dir: str, platform: str):
    """Gets visual c++ compiler binary directory (changes depending on platform)
    """
    bin_dir = 'bin' if platform == 'x86' else path.join('bin', platform)
    return path.join(vc_dir, bin_dir)


def get_version(package: str, allow_untagged):
    """Gets the version of the package we're building
    """
    package_version = check_output('git describe --tags').decode('utf8').strip()
    if package_version:
        version_parts = package_version.strip('v').split('-')
        if not allow_untagged and len(version_parts) > 2:
            # Untagged commits have the pattern <tag>-<distance>-<commit>
            raise ValueError('Untagged version not allowed! Description: {}'.format(package_version))
        return '-'.join(version_parts if len(version_parts) <= 2 else version_parts[:-1])
    else:
        exec(f'import {package}') #pylint: disable=exec-used
        package_version = eval(f'{package}.__version__') #pylint: disable=eval-used

        build = datetime.now().strftime('%Y%m%d%H%M%S')

        version_parts = package_version.split('-')
        if len(version_parts) == 1:
            version_parts.append(build)
        else:
            version_parts[-1] = build
        return '-'.join(version_parts)


def get_template(name: str) -> Template:
    """Loads a jinja template from the name of the template file
    """
    template_path = path.join(path.realpath(path.dirname(__file__)), f'{name}.jinja')
    with open(template_path) as fp:
        return Template(fp.read())


def get_python_version(python_dir: str):
    """Gets the version of python that is being used to compile
    """
    version_string = check_output([path.join(python_dir, 'python.exe'), '--version']).decode('utf8')
    version = version_string.replace('Python', '').strip().split('.')
    return {'major': version[0], 'minor': version[1], 'patch': version[2]}


def to_str_list(comma_delimited):
    return comma_delimited.split(',') if comma_delimited else []


def to_bool(arg):
    return arg.lower() in ['1', 'true', 't', 'yes'] if arg else False

class CompileCommand(Command):
    """CompileCommand
    Implements the `Command` interface from `setuptools`
    to compile a windows installer from a pyqt5 application
    """
    #pylint: disable=too-many-instance-attributes
    user_options = [
        ('qmake-path=', None, 'The path to qmake'),
        ('pyqt-dir=', None, 'The base directory of PyQt'),
        ('sip-dir=', None, 'The base directory of Sip'),
        ('python-dir=', None, 'The directory containing python'),
        ('vc-dir=', None, 'The path the Visual Studio 2015 VC directory'),
        ('platform=', None, 'The platform to compile for'),
        ('qt-modules=', None, 'The QT modules to compile'),
        ('package=', None, 'The package to compile'),
        ('entrypoint=', None, 'The entrypoint, defaults to <package>/__main__.py'),
        ('inno-setup-path=', None, 'The path to inno setup'),
        ('win-console=', None, 'Whether or not the resulting application should use the console'),
        ('skip-installer=', None, 'Skip the installer'),
        ('skip-post-build=', None, 'Skip the post build step'),
        ('compiled-packages=', None, 'Packages to compile'),
        ('allow-untagged=', None, 'Allow untagged releases'),
        ('signtool=', None, 'Command to use for signing installers'),
        ('additional-libs=', None, 'Additional library files to compile'),
        ('source-files=', None, 'Source files')
    ]

    def initialize_options(self):
        """Implementation of `Command` initialize_options
        Loads default options from user configuration
        """
        #pylint: disable=attribute-defined-outside-init
        self.qt_modules = None
        self.qmake_path = None
        self.vc_dir = None
        self.platform = 'amd64'
        self.pyqt_dir = None
        self.sip_dir = None
        self.python_dir = None
        self.inno_setup_path = None
        self.package = None
        self.entrypoint = None
        self.app_name = None
        self.file_extension = None
        self.app_icon = None
        self.license_file = None
        self.build_dir = None
        self.resources_dirs = None
        self.win_console = False
        self.languages = None
        self.stdlib_modules = None
        self.external_stdlib_modules = None
        self.stdlib_binaries = None
        self.external_packages = None
        self.skip_installer = False
        self.skip_post_build = False
        self.post_build = None
        self.pre_build = None
        self.compiled_packages = None
        self.allow_untagged = None
        self.signtool = None
        self.additional_libs = None
        self.source_files = None

    def finalize_options(self):
        """Implentation of `Command` finalize_options
        Performs validation on the parameters provided
        """
        #pylint: disable=attribute-defined-outside-init

        # User options
        assert self.qmake_path, 'qmake-path must be provided'
        assert self.vc_dir, 'vc-path must be provided'
        assert self.platform, 'platform must be specified'
        assert self.pyqt_dir, 'pyqt-dir must be specified'
        assert self.sip_dir, 'sip-dir must be specified'
        assert self.python_dir, 'python-dir must be provided'
        assert path.isfile(self.qmake_path), 'qmake path does not exist'
        assert path.isdir(self.vc_dir), 'vc directory path does not exist'
        assert self.platform in ['amd64'],\
            f'Platform {self.platform} is not currently supported'
        assert path.isdir(self.pyqt_dir),\
            'pyqt directory does not exist'
        assert path.isdir(self.sip_dir),\
            'sip directory does not exist'
        assert path.isdir(self.python_dir), 'python directory could not be found'

        # General options
        assert self.qt_modules, 'qt-modules must be specified'
        assert self.package, 'package must be specified'
        assert self.app_name, 'Must provide an app name'
        assert path.isdir(self.package), 'package not found'
        assert not self.entrypoint or path.isfile(self.entrypoint), 'entrypoint not found'
        self.resources_dirs = to_str_list(self.resources_dirs)
        self.qt_modules = to_str_list(self.qt_modules)
        self.stdlib_modules = to_str_list(self.stdlib_modules)
        self.external_stdlib_modules = to_str_list(self.external_stdlib_modules)
        self.stdlib_binaries = to_str_list(self.stdlib_binaries)
        self.external_packages = to_str_list(self.external_packages)
        self.languages = to_str_list(self.languages)
        self.post_build = to_str_list(self.post_build)
        self.pre_build = to_str_list(self.pre_build)
        self.win_console = to_bool(self.win_console)
        self.skip_installer = to_bool(self.skip_installer)
        self.skip_post_build = to_bool(self.skip_post_build)
        self.compiled_packages = to_str_list(self.compiled_packages)
        self.allow_untagged = to_bool(self.allow_untagged)
        self.additional_libs = to_str_list(self.additional_libs)
        if self.source_files:
            self.source_files = {source: dest for source, dest in [f.split(':') for f in self.source_files.split(',')]}

        if not self.skip_installer:
            assert self.inno_setup_path, 'inno-setup-path must be provided'
            assert path.isfile(self.inno_setup_path), 'inno setup path does not exist'

        self.build_dir = self.build_dir or 'build'

        self.external_exe_files = []

        self._app_version_c = None

        # Installer options
        self.app_config = {
            'app_version': self._app_version,
            'app_name': self.app_name,
            'app_icon': self.app_icon,
            'resources_dirs': self.resources_dirs,
            'entrypoint': self.entrypoint or f'{self.package}/__main__.py',
            'license_file': self.license_file,
            'file_extension': self.file_extension
        }


    def run(self):
        """Runs the command
        Performs the steps required to compile the application and generate an installer
        """
        sys.stdout.write('{} Building {} version "{}" {}\n'.format('*' * 10, self.app_name, self._app_version, '*' * 10))
        # Apply version
        self._apply_version()
        
        # Clean the output directory
        self._clean()

        # Exec pre build
        for pre_build_step in self.pre_build:
            self._exec_build_step(pre_build_step)

        # Build the package project file
        self._build_project_file()

        # Create the app resources
        self._create_app_resources()

        vc_env = self._get_vc_env()

        # Build the qt project file
        self._run_pyqtdeploy(vc_env)

        # Remove version
        self._remove_version()

        # Generate translations
        self._generate_ts(vc_env)
        self._generate_qm(vc_env)

        # Build the nmake Makefiles
        self._run_qmake(vc_env)

        # Update source_files
        self._update_source_files()

        # Build the exe
        self._run_nmake(vc_env)

        # Copy the dlls to the release directory
        self._copy_binaries(vc_env)

        # Copy the external packages to the release directory
        self._copy_external_packages()

        if 'QtWebEngine' in self.qt_modules:
            self._copy_qt_web_engine_resources()

        output_dirs = {}

        if not self.skip_post_build:
            for post_build_step in self.post_build:
                output_dirs = {**output_dirs, **self._exec_build_step(post_build_step)}

            output_dirs = output_dirs or {'': self.output_dir}

        if not self.skip_installer:
            for name, output in output_dirs.items():
                self._build_installer(name, output)

    @staticmethod
    def assert_call(cmd, **kwargs):
        """function:: assert_call(cmd, **kwargs)
        Makes a call to a process
        """
        return assert_call(cmd, **kwargs)

    def _clean(self):
        if path.isdir(self.build_dir):
            shutil.rmtree(self.build_dir)


    @property
    def _qt_dir(self):
        return path.dirname(self.qmake_path)


    @property
    def _project_name(self):
        return self.app_name.replace(' ', '')


    @property
    def _installer_filename(self):
        return self._project_name + '_' + self._app_version + '_' + self.platform


    @property
    def _app_version(self):
        if self._app_version_c is None:
            self._app_version_c = get_version(self.package, self.allow_untagged)
        return self._app_version_c


    @property
    def _app_version_short(self):
        version_parts = self._app_version.split('-')
        if len(version_parts) == 1:
            return version_parts[0]
        else:
            return version_parts[0] + '.' + version_parts[-1]

    @property
    def output_dir(self):
        return path.join(self.build_dir, 'release')

    
    @property
    def qmake_pro_file(self):
        return path.join(self.build_dir, f'{self._project_name}.pro')

    def _update_source_files(self):
        if self.source_files:
            for source, dest in self.source_files.items():
                shutil.copyfile(source, path.join(self.build_dir, dest))

    def _build_project_file(self):

        app_packages = [self._get_py_packages('.', self.package)]
        if self.compiled_packages:
            compiled_packages_dir = self._get_external_package_path(self.compiled_packages)
            compiled_packages = [{
                'name': compiled_packages_dir,
                'packages': [self._get_py_packages(compiled_packages_dir, p) for p in self.compiled_packages],
                'modules': []
            }]
        else:
            compiled_packages = []

        args = {
            **self.app_config,
            'project_name': self._project_name,
            'package': self.package,
            'qt_modules': self.qt_modules,
            'build_dir': self.build_dir,
            'python_version': get_python_version(self.python_dir),
            'app_version': self._app_version_short,
            'win_console': '1' if self.win_console else '0',
            'translation_files': self._get_translation_files(),
            'py_packages': app_packages,
            'stdlib_modules': self.stdlib_modules,
            'compiled_packages': compiled_packages,
            'python_dir': self.python_dir,
            'additional_libs': self.additional_libs
        }
        with open(f'{self._project_name}.pdy', 'w') as fp:
            fp.write(get_template('package.pdy').render(args))

    def _apply_version(self):
        with open(path.join(self.package, '__version__.py'), 'w') as fp:
            fp.write(f'__version__ = \'{self._app_version}\'')
    
    def _remove_version(self):
        os.remove(path.join(self.package, '__version__.py'))

    def _get_external_package_path(self, requires, package_exists=None):
        valid_package_paths = sys.path + ['.']
        package_exists = package_exists or (lambda d, r: path.isdir(path.join(d, r)) or path.isfile(path.join(d, f'{r}.py')) or path.isfile(path.join(d, f'{r}.egg-link')) or glob(path.join(d, f'{r}.*.pyd')))
        for require in requires:
            valid_package_paths = [d for d in valid_package_paths if package_exists(d, require)]
            assert valid_package_paths, f'No valid package paths found for {require}'
        return valid_package_paths[0]


    def _get_py_packages(self, base, package):
        basepath = path.join(base, package)
        files = os.listdir(basepath)
        packages = [self._get_py_packages(basepath, p) for p in files if path.isdir(path.join(basepath, p)) and not p.startswith('__')]
        modules = [m for m in files if m.endswith('.py')]
        return {'name': package, 'packages': packages, 'modules': modules}


    def _create_app_resources(self):
        app_resource_files = glob(f'{self.package}/**/*.qml', recursive=True)
        args = {
            'files': app_resource_files
        }
        app_resources_dir = path.join(self.build_dir, 'app_resources')
        if not path.isdir(app_resources_dir):
            os.makedirs(app_resources_dir)

        with open(path.join(app_resources_dir, 'app_resources.qrc'), 'w') as fp:
            fp.write(get_template('resources.qrc').render(args))
        for resource_file in app_resource_files:
            dest = path.join(self.build_dir, 'app_resources', resource_file)
            if not path.isdir(path.dirname(dest)):
                os.makedirs(path.dirname(dest))
            shutil.copyfile(resource_file, dest)

        for resources_dir in self.resources_dirs:
            other_resource_files = glob(f'{resources_dir}/**/*', recursive=True)
            for resource_file in [f for f in other_resource_files if path.isfile(f)]:
                dest = path.join(self.output_dir, resource_file)
                if not path.isdir(path.dirname(dest)):
                    os.makedirs(path.dirname(dest))
                shutil.copyfile(resource_file, dest)


    def _copy_qt_web_engine_resources(self):
        shutil.copyfile(path.join(self._qt_dir, 'QtWebEngineProcess.exe'), path.join(self.output_dir, 'QtWebEngineProcess.exe'))
        qt_resources_dir = path.abspath(path.join(self._qt_dir, '..', 'resources'))
        qt_translations_dir = path.join(self._qt_dir, '..', 'translations')
        for resource in glob(qt_resources_dir + '/*'):
            shutil.copyfile(resource, path.join(self.output_dir, 'resources', path.basename(resource)))
        locales_dest = path.join(self.output_dir, 'translations', 'qtwebengine_locales')
        if not path.isdir(locales_dest):
            shutil.copytree(path.join(qt_translations_dir, 'qtwebengine_locales'), locales_dest)
        
        self.external_exe_files.append('QtWebEngineProcess.exe')


    def _generate_ts(self, env):
        if self.languages:
            temp_tr_filename = path.join(self.build_dir, 'temp_tr.py')
            with open(temp_tr_filename, 'w') as temp_tr:
                for filename in glob(f'{self.package}/**/*.py', recursive=True):
                    with open(filename) as src:
                        temp_tr.writelines(src.readlines())
            if not path.isdir('translations'):
                os.makedirs('translations')
            assert_call([
                'pylupdate5',
                '-verbose',
                temp_tr_filename,
                '-ts'
            ] + self._get_translation_files(), env=env)
            dest = path.join(self.build_dir, 'translations')
            if os.path.exists(dest):
                shutil.rmtree(dest)
            shutil.copytree('translations', dest)


    def _generate_qm(self, env):
        assert_call([
            path.join(self._qt_dir, 'lrelease'),
            '-verbose',
            self.qmake_pro_file
        ], env=env)

        qm_files = glob(path.join(self.build_dir, 'translations', '*.qm'))
        dest = path.join(self.output_dir, 'translations')
        if not path.isdir(dest):
            os.makedirs(dest)
        for qm_file in qm_files:
            shutil.copy(qm_file, dest)


    def _get_translation_files(self):
        return [f'translations/{self.package}_{lang}.ts' for lang in self.languages]


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
        assert_call(['pyqtdeploycli', 'build', '--output', self.build_dir, '--project', f'{self._project_name}.pdy'], env=env)


    def _run_qmake(self, env):
        assert_call([self.qmake_path], cwd=self.build_dir, env=env)


    def _run_nmake(self, env):
        assert_call(
            [path.join(get_vc_bin_dir(self.vc_dir, self.platform), 'nmake')],
            cwd=self.build_dir,
            env=env
        )

    def _build_installer(self, name, output):
        installer_filename = self._installer_filename if not name else f'{self._installer_filename}-{name}'
        if isinstance(output, dict):
            output_dir = output['output_dir']
            additional_files = output.get('additional_files', [])
            additional_temp_files = output.get('additional_temp_files', [])
            run_commands = output.get('run', [])
            uninstall_commands = output.get('uninstall', [])
            uninstall_files = output.get('uninstall_files', [])
        else:
            output_dir = output
            additional_files = []
            run_commands = []
            uninstall_commands = []
            additional_temp_files = []
            uninstall_files = []

        installer_config = {
            **self.app_config,
            'installer_filename': installer_filename,
            'additional_files': additional_files,
            'run_commands': run_commands,
            'uninstall_commands': uninstall_commands,
            'uninstall_files': uninstall_files,
            'external_exe_files': self.external_exe_files,
            'additional_temp_files': additional_temp_files,
            'include_translations': True if self.languages else False
        }

        setup_script = get_template('setup.iss').render(installer_config)

        with open(path.join(output_dir, 'setup.iss'), 'w') as fp:
            fp.write(setup_script)

        assert_call([self.inno_setup_path, fp.name])

        filename = installer_config['installer_filename'] + '.exe'

        if self.signtool:
            assert_call(self.signtool + ' ' + path.join(output_dir, filename))

        shutil.move(path.join(output_dir, filename), path.join(path.abspath('.'), filename))


    def _copy_binaries(self, env):
        # Copy the dll paths we know about
        for dll_path in self._get_dll_paths():
            shutil.copyfile(dll_path, path.join(self.output_dir, path.basename(dll_path)))
        
        # for pyd_src, pyd_dest in self._get_pyd_paths():
        #     shutil.copyfile(pyd_src, path.join(self.output_dir, pyd_dest))

        # Copy the qwindows.dll file
        platforms_dir = path.join(self._qt_dir, '..', 'plugins', 'platforms')
        dest_platforms_dir = path.join(self.output_dir, 'platforms')
        if not path.isdir(dest_platforms_dir):
            os.makedirs(dest_platforms_dir)
        shutil.copyfile(
            path.join(platforms_dir, 'qwindows.dll'),
            path.join(dest_platforms_dir, 'qwindows.dll')
        )

        # Run windeployqt
        app_binary = path.join(self.output_dir, f'{self._project_name}.exe')
        assert_call([
            path.join(self._qt_dir, 'windeployqt'),
            '--release',
            app_binary
        ], env=env)
    
    def _resolve_egg_link(self, external_packages_path, package):
        if not path.isfile(path.join(external_packages_path, package + '.egg-link')):
            return external_packages_path, package
        else:
            with open(path.join(external_packages_path, package + '.egg-link'), 'r') as fp:
                current_path = fp.readlines()[0]
            return current_path, package
        

    def _copy_external_packages(self):
        external_packages_path = self._get_external_package_path(self.external_packages)
        package_dest = path.join(self.output_dir, 'packages')
        for package in self.external_packages:
            current_path, package = self._resolve_egg_link(external_packages_path, package)
            if path.isdir(path.join(current_path, package)) and not path.isdir(path.join(package_dest, package)):
                shutil.copytree(path.join(current_path, package), path.join(package_dest, package), ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            elif path.isfile(path.join(current_path, f'{package}.py')) and not path.isfile(path.join(package_dest, f'{package}.py')):
                shutil.copyfile(path.join(current_path, f'{package}.py'), path.join(package_dest, f'{package}.py'))
            elif glob(path.join(current_path, f'{package}.*.pyd')):
                compiled_package_binary = glob(path.join(current_path, f'{package}.*.pyd'))[0]
                shutil.copyfile(compiled_package_binary, path.join(package_dest, path.basename(compiled_package_binary)))

        external_stdlib_path = self._get_external_package_path(self.external_stdlib_modules)
        for package in self.external_stdlib_modules:
            if path.isdir(path.join(external_stdlib_path, package)) and not path.isdir(path.join(package_dest, package)):
                shutil.copytree(path.join(external_stdlib_path, package), path.join(package_dest, package), ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))

    def _get_dll_paths(self):
        pyqt_dlls = [
            path.join(p, f'{m}.dll') for p, m in zip(self._get_pyqt_lib_paths(), self.qt_modules)
        ]
        sip_dll = path.join(self._get_sip_lib_path(), 'sip.pyd')
        qt_dll_modules = self.qt_modules
        qt_dlls = [
            path.join(self._qt_dir, m.replace('Qt', 'Qt5') + '.dll')\
                for m in qt_dll_modules if m != 'Qt'
        ]
        python_dlls = [path.join(self.python_dir, f'{d}.dll') for d in ['python3', 'python36']]
        if self.stdlib_binaries:
            module_path = self._get_external_package_path(self.stdlib_binaries, lambda d, r: path.isfile(path.join(d, f'{r}.pyd')))
            python_compiled_module_dlls = [path.join(module_path, f'{r}.pyd') for r in self.stdlib_binaries]
        else:
            python_compiled_module_dlls = []
        external_module_dlls = []
        packages_path = self._get_external_package_path(self.external_packages)
        for package in self.external_packages:
            external_module_dlls += glob(path.join(packages_path, package) + '/**/*.dll')
        return pyqt_dlls + [sip_dll] + qt_dlls + python_dlls + python_compiled_module_dlls + external_module_dlls

    def _get_pyd_paths(self):
        pyd_paths = []
        packages_path = self._get_external_package_path(self.external_packages)

        def source_to_dest(src, packages_path):
            source_dir = path.dirname(src)
            source_file = path.basename(src).split('.')[0] + '.pyd'
            return path.relpath(source_dir, packages_path).replace(path.sep, '.') + '.' + source_file

        for package in self.external_packages:
            source_files = glob(path.join(packages_path, package) + '/**/*.pyd')
            dest_files = [source_to_dest(src, packages_path) for src in source_files]
            pyd_paths += list(zip(source_files, dest_files))
        return pyd_paths

    def _get_pyqt_lib_paths(self):
        return [
            path.join(
                self.pyqt_dir,
                q,
                'release'
            ) for q in self.qt_modules
        ]

    def _get_sip_lib_path(self):
        return path.join(self.sip_dir, 'siplib')


    def _exec_build_step(self, build_step):
        filename, function = build_step.split(':')
        spec = importlib.util.spec_from_file_location("module", filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not function in module.__dict__:
            raise RuntimeError(f'Could not find function {function} in file {filename}')
        return module.__dict__[function](self) or {}
