"""CompileCommand

This module defines the "compile" command, which will compile an installer from a pyqt5 application
"""
from subprocess import call, check_output
import sys
import os
from os import path
from configparser import ConfigParser
import shutil
from glob import glob
from typing import Sequence

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
        vc_env[name] = value
    vc_env['Path'] = '{};{}'.format(get_vc_bin_dir(vc_dir, platform), vc_env['Path'])
    return vc_env

def get_vc_bin_dir(vc_dir: str, platform: str):
    """Gets visual c++ compiler binary directory (changes depending on platform)
    """
    bin_dir = 'bin' if platform == 'x86' else path.join('bin', platform)
    return path.join(vc_dir, bin_dir)


def get_version(package: str):
    """Gets the version of the package we're building
    """
    exec(f'import {package}') #pylint: disable=exec-used
    return eval(f'{package}.__version__') #pylint: disable=eval-used


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
        ('win-console=', None, 'Whether or not the resulting application should use the console'),
        ('skip-installer=', None, 'Skip the installer')
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
        self.languages = None
        self.vc_redist_dir = None
        self.qtquick_modules = None
        self.stdlib_modules = None
        self.external_stdlib_modules = None
        self.stdlib_binaries = None
        self.external_packages = None
        self.skip_installer = False

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
        assert path.isdir(self.vc_redist_dir), 'vc_redist_dir not found'
        self.qt_modules = to_str_list(self.qt_modules)
        self.qtquick_modules = to_str_list(self.qtquick_modules)
        self.stdlib_modules = to_str_list(self.stdlib_modules)
        self.external_stdlib_modules = to_str_list(self.external_stdlib_modules)
        self.stdlib_binaries = to_str_list(self.stdlib_binaries)
        self.external_packages = to_str_list(self.external_packages)
        self.languages = [] if not self.languages else self.languages.split(',')
        self.win_console =\
            self.win_console.lower() in ['1', 'true', 't', 'yes'] if self.win_console\
            else False
        self.skip_installer =\
            self.skip_installer.lower() in ['1', 'true', 't', 'yes'] if self.skip_installer\
            else False

        self.build_dir = self.build_dir or 'build'

        # Installer options
        self.app_config = {
            'app_version': get_version(self.package),
            'exe_filename': f'{self.package}.exe',
            'platform': self.platform,
            'app_name': self.app_name,
            'app_icon': self.app_icon,
            'resources_dir': self.resources_dir,
            'package': self.package
        }

        self.externals_config = {
            'vc_redist_dir': path.join(self.vc_redist_dir, 'vc14')
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
        self._copy_qml_modules()

        vc_env = self._get_vc_env()

        # Build the qt project file
        self._run_pyqtdeploy(vc_env)

        # Generate translations
        self._generate_ts(vc_env)
        self._generate_qm(vc_env)

        # Build the nmake Makefiles
        self._run_qmake(vc_env)

        # Build the exe
        self._run_nmake(vc_env)

        dest = path.join(self.build_dir, 'release')

        # Copy the qml files
        self._copy_qml(dest)

        # Copy the dlls to the release directory
        self._copy_binaries(dest)

        # Copy the external packages to the release directory
        self._copy_external_packages(dest)

        if 'QtWebEngine' in self.qt_modules:
            self._copy_qt_web_engine_resources(dest)

        if not self.skip_installer:
            # Build the installer
            self._build_installer(dest)


    @property
    def _qt_dir(self):
        return path.dirname(self.qmake_path)


    @property
    def _project_name(self):
        return self.app_name.replace(' ', '')


    def _build_project_file(self):
        app_packages = [self._get_py_packages('.', self.package)]
        # external_package_definitions = []
        # external_modules = []
        # external_package_path = path.relpath(self._get_external_package_path(self.external_packages), '.')
        # for require in self.external_packages:
        #     if path.isdir(path.join(external_package_path, require)):
        #         package = self._get_py_packages(external_package_path, require)
        #         external_package_definitions.append(package)
        #     elif path.isfile(path.join(external_package_path, f'{require}.py')):
        #         external_modules.append(f'{require}.py')
        
        args = {
            'project_name': self._project_name,
            'package': self.package,
            'qt_modules': self.qt_modules,
            'build_dir': self.build_dir,
            'python_version': get_python_version(self.python_dir),
            'win_console': '1' if self.win_console else '0',
            'translation_files': self._get_translation_files(),
            'py_packages': app_packages,
            # 'external_packages': [{
            #     'name': external_package_path,
            #     'packages': external_package_definitions,
            #     'modules': external_modules
            # }],
            'stdlib_modules': self.stdlib_modules
        }
        with open(f'{self._project_name}.pdy', 'w') as fp:
            fp.write(get_template('package.pdy').render(args))


    def _get_external_package_path(self, requires, package_exists=None):
        valid_package_paths = sys.path
        package_exists = package_exists or (lambda d, r: path.isdir(path.join(d, r)) or path.isfile(path.join(d, f'{r}.py')))
        for require in requires:
            valid_package_paths = [d for d in valid_package_paths if package_exists(d, require)]
        assert valid_package_paths, 'No valid package paths found'
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

        other_resource_files = glob(f'{self.resources_dir}/**/*', recursive=True)
        for resource_file in other_resource_files:
            dest = path.join(self.build_dir, 'release', resource_file)
            if not path.isdir(path.dirname(dest)):
                os.makedirs(path.dirname(dest))
            shutil.copyfile(resource_file, dest)


    def _copy_qml_modules(self):
        qml_dir_files = glob(f'{self.package}/**/qmldir', recursive=True)

        for qml_dir_file in qml_dir_files:
            dest = path.join(self.build_dir, 'release', qml_dir_file)
            if not path.isdir(path.dirname(dest)):
                os.makedirs(path.dirname(dest))
            shutil.copyfile(qml_dir_file, dest)

    def _copy_qt_web_engine_resources(self, dest):
        shutil.copyfile(path.join(self._qt_dir, 'QtWebEngineProcess.exe'), path.join(dest, 'QtWebEngineProcess.exe'))
        qt_resources_dir = path.abspath(path.join(self._qt_dir, '..', 'resources'))
        qt_translations_dir = path.join(self._qt_dir, '..', 'translations')
        for resource in glob(qt_resources_dir + '/*'):
            shutil.copyfile(resource, path.join(dest, 'resources', path.basename(resource)))
        locales_dest = path.join(dest, 'translations', 'qtwebengine_locales')
        if not path.isdir(locales_dest):
            shutil.copytree(path.join(qt_translations_dir, 'qtwebengine_locales'), locales_dest)


    def _generate_ts(self, env):
        if self.languages:
            if not path.isdir('translations'):
                os.makedirs('translations')
            assert_call([
                path.join(self._qt_dir, 'lupdate'),
                '-verbose',
                self.package,
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
            path.join(self.build_dir, f'{self._project_name}.pro')
        ], env=env)

        qm_files = glob(path.join(self.build_dir, 'translations', '*.qm'))
        dest = path.join(self.build_dir, 'release', 'translations')
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
        setup_script = get_template('setup.iss').render({
            **self.app_config,
            **self.externals_config
        })

        with open(path.join(dest, 'setup.iss'), 'w') as fp:
            fp.write(setup_script)

        assert_call([self.inno_setup_path, fp.name])

    def _copy_qml(self, dest):
        qml_dest = path.join(dest, 'qml')
        if path.isdir(qml_dest):
            shutil.rmtree(qml_dest)

        os.makedirs(qml_dest)

        for module in self.qtquick_modules:
            qml_dir = path.join(self._qt_dir, '..', 'qml')
            module_src = path.join(qml_dir, module)
            exclude_endswith = ['d.dll', '.pdb']
            for module_file in glob(f'{module_src}/**/*', recursive=True):
                if path.isfile(module_file) and not any(map(module_file.endswith, exclude_endswith)):
                    dest = path.join(qml_dest, path.relpath(module_file, qml_dir))
                    if not path.isdir(path.dirname(dest)):
                        os.makedirs(path.dirname(dest))
                    shutil.copyfile(module_file, dest)


    def _copy_binaries(self, dest):
        # Copy the dll paths we know about
        for dll_path in self._get_dll_paths():
            shutil.copyfile(dll_path, path.join(dest, path.basename(dll_path)))
        
        # for pyd_src, pyd_dest in self._get_pyd_paths():
        #     shutil.copyfile(pyd_src, path.join(dest, pyd_dest))

        # Copy the qwindows.dll file
        platforms_dir = path.join(self._qt_dir, '..', 'plugins', 'platforms')
        dest_platforms_dir = path.join(dest, 'platforms')
        if not path.isdir(dest_platforms_dir):
            os.makedirs(dest_platforms_dir)
        shutil.copyfile(
            path.join(platforms_dir, 'qwindows.dll'),
            path.join(dest_platforms_dir, 'qwindows.dll')
        )

        # Run windeployqt
        qml_dir = path.join(self._qt_dir, '..', 'qml')
        app_binary = path.join(dest, f'{self._project_name}.exe')
        assert_call([
            path.join(self._qt_dir, 'windeployqt'),
            '--release',
            '--qmldir', qml_dir,
            app_binary
        ])

    def _copy_external_packages(self, dest):
        external_packages_path = self._get_external_package_path(self.external_packages)
        package_dest = path.join(dest, 'packages')
        for package in self.external_packages:
            if path.isdir(path.join(external_packages_path, package)) and not path.isdir(path.join(package_dest, package)):
                shutil.copytree(path.join(external_packages_path, package), path.join(package_dest, package))
            elif path.isfile(path.join(external_packages_path, f'{package}.py')) and not path.isfile(path.join(package_dest, f'{package}.py')):
                shutil.copyfile(path.join(external_packages_path, f'{package}.py'), path.join(package_dest, f'{package}.py'))
        
        external_stdlib_path = self._get_external_package_path(self.external_stdlib_modules)
        for package in self.external_stdlib_modules:
            if path.isdir(path.join(external_stdlib_path, package)) and not path.isdir(path.join(package_dest, package)):
                shutil.copytree(path.join(external_stdlib_path, package), path.join(package_dest, package))


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
        qt_dll_modules = self.qt_modules
        if 'QtQuick' in qt_dll_modules:
            qt_dll_modules = qt_dll_modules + ['QtQuickControls2', 'QtQuickTemplates2']
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
                self.prebuilt_libraries_dir,
                'PyQt5_gpl-5.9.1',
                q,
                'release'
            ) for q in self.qt_modules
        ]

    def _get_sip_lib_path(self):
        return path.join(self.prebuilt_libraries_dir, 'sip-4.19.5', 'siplib')
