from setuptools import Command, setup
from subprocess import call, check_output
import os
from os import path
from configparser import ConfigParser
import shutil
import tempfile

def assert_call(cmd, **kwargs):
    result = call(cmd, **kwargs)
    assert not result, '{} exited with code {} - see output for details'.format(' '.join(cmd), result)

def get_vc_env(vc_dir, platform):
    vcvars = check_output(['cmd', '/c', f'vcvarsall.bat {platform}&set'], cwd=vc_dir).decode('utf8')
    vc_env = {}
    for line in vcvars.splitlines():
        name, value = line.split('=')
        vc_env[name] = value
    vc_env['Path'] = '{};{}'.format(get_vc_bin_dir(vc_dir, platform), vc_env['Path'])
    return vc_env

def get_vc_bin_dir(vc_dir, platform):
    bin_dir = 'bin' if platform == 'x86' else path.join('bin', platform)
    return path.join(vc_dir, bin_dir)

def get_version(package):
    exec(f'import {package}')
    return eval(f'{package}.__version__')

def get_setup_template():
    with open(path.join(path.realpath(path.dirname(__file__)), 'setup.iss.template')) as fp:
        return fp.read()

class CompileCommand(Command):
    user_options = [
        ('qmake-path=', None, 'The path to qmake'),
        ('prebuilt-libraries-dir=', None, 'The base directory of the prebuild libraries'),
        ('python-dir=', None, 'The directory containing python'),
        ('vc-dir=', None, 'The path the Visual Studio 2015 VC directory'),
        ('platform=', None, 'The platform to compile for'),
        ('qt-modules=', None, 'The QT modules to compile'),
        ('package=', None, 'The package to compile'),
        ('inno-setup-path=', None, 'The path to inno setup')
    ]


    def initialize_options(self):
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

    def finalize_options(self):
        # User options
        assert self.qmake_path, 'qmake-path must be provided'
        assert self.vc_dir, 'vc-path must be provided'
        assert self.platform, 'platform must be specified'
        assert self.prebuilt_libraries_dir, 'prebuilt-libraries-dir must be specified'
        assert self.python_dir, 'python-dir must be provided'
        assert self.inno_setup_path, 'inno-setup-path must be provided'
        assert path.isfile(self.qmake_path), 'qmake path does not exist'
        assert path.isdir(self.vc_dir), 'vc directory path does not exist'
        assert self.platform in ['amd64'], f'Platform {self.platform} is not currently supported'
        assert path.isdir(self.prebuilt_libraries_dir), 'prebuilt libraries directory does not exist'
        assert path.isdir(self.python_dir), 'python directory could not be found'
        assert path.isfile(self.inno_setup_path), 'inno setup path does not exist'

        # General options
        assert self.qt_modules, 'qt-modules must be specified'
        assert self.package, 'package must be specified'
        assert path.isdir(self.package), 'package not found'
        assert path.isfile(f'{self.package}.pdy'), 'qtdeploy project file does not exist - run pyqtdeploy'
        self.qt_modules = self.qt_modules.split(',')

        # Installer options
        app_config_parser = ConfigParser()
        with open('setup.cfg') as fp:
            app_config_parser.read_file(fp)
        self.app_config = {
            'app_version': get_version(self.package),
            'exe_filename': f'{self.package}.exe',
            'platform': self.platform,
            **app_config_parser['app']
        }

        self._save_compile_user_config()


    def run(self):
        # Build the qt project file
        vc_env = get_vc_env(self.vc_dir, self.platform)

        vc_env['LIB'] = '{};{};{}'.format(
            ';'.join(self._get_pyqt_lib_paths()),
            self._get_sip_lib_path(),
            vc_env['LIB']
        )

        vc_env['PYTHON_DIR'] = self.python_dir
        
        assert_call(['pyqtdeploycli', 'build', '--project', f'{self.package}.pdy'], env=vc_env)

        # Build the nmake Makefiles
        assert_call([self.qmake_path], cwd='build', env=vc_env)

        # Build the exe
        assert_call(
            [path.join(get_vc_bin_dir(self.vc_dir, self.platform), 'nmake')],
            cwd='build',
            env=vc_env
        )

        # Copy the dlls to the release directory
        dest = path.join('build', 'release')
        for f in self._get_dll_paths():
            shutil.copyfile(f, path.join(dest, path.basename(f)))

        setup_script = get_setup_template().format(**self.app_config)

        with open(path.join(dest, 'setup.iss'), 'w') as fp:
            fp.write(setup_script)

        assert_call([self.inno_setup_path, fp.name])


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
        pyqt_dlls = [path.join(p, f'{m}.dll') for p, m in zip(self._get_pyqt_lib_paths(), self.qt_modules)]
        sip_dll = path.join(self._get_sip_lib_path(), 'sip.pyd')
        qt_dll_base = path.dirname(self.qmake_path)
        qt_dlls = [path.join(qt_dll_base, m.replace('Qt', 'Qt5') + '.dll') for m in self.qt_modules]
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