# Copyright 2015 Open Source Robotics Foundation, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import os
import sys

# Make sure to get osrf_pycommon from the vendor folder
vendor_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'vendor'))
sys.path.insert(0, os.path.join(vendor_path, 'osrf_pycommon'))
import osrf_pycommon
# Assert that we got it from the right place
assert osrf_pycommon.__file__.startswith(vendor_path), \
    ("osrf_pycommon imported from '{0}' which is not in the vendor folder '{1}'"
     .format(osrf_pycommon.__file__, vendor_path))
from osrf_pycommon.process_utils import async_execute_process
from osrf_pycommon.process_utils import AsyncSubprocessProtocol
from osrf_pycommon.process_utils import get_loop
from osrf_pycommon.terminal_color import format_color


def log(*args, **kwargs):
    msg = ''
    # Do color formatting for each arg and combine them.
    for arg in args:
        msg += format_color(arg)
    # Extract fargs and/or fkwargs and format the now colorized string.
    fargs, fkwargs = None, None
    if 'fargs' in kwargs:
        fargs = kwargs['fargs']
        del kwargs['fargs']
    if 'fkwargs' in kwargs:
        fkwargs = kwargs['fkwargs']
        del kwargs['fkwargs']
    if fargs is not None or fkwargs is not None:
        fargs = fargs or []
        fkwargs = fkwargs or {}
        msg = msg.format(*fargs, **kwargs)
    # If the user did not provide an end kwarg, automatically clear the coloring.
    if 'end' not in kwargs:
        msg += format_color("@|")
    # Hand off to print.
    print(msg, **kwargs)


def info(*args, **kwargs):
    log("@!II>@| ", *args, **kwargs)


def warn(*args, **kwargs):
    kwargs['file'] = kwargs.get('file', sys.stderr)
    log("@{yf}WW> ", *args, **kwargs)


class MyProtocol(AsyncSubprocessProtocol):
    def __init__(self, cmd, exit_on_error, *args, **kwargs):
        self.cmd = cmd
        self.exit_on_error = exit_on_error
        AsyncSubprocessProtocol.__init__(self, *args, **kwargs)

    def on_stdout_received(self, data):
        sys.stdout.write(data.decode())

    def on_stderr_received(self, data):
        sys.stderr.write(data.decode())

    def on_process_exited(self, returncode):
        if self.exit_on_error and returncode != 0:
            log("@{rf}@!<==@| '{0}' exited with return code '{1}'",
                fargs=(" ".join(self.cmd), returncode))


def run(cmd, exit_on_error=True, **kwargs):
    log("@{bf}==>@| @!{0}", fargs=(" ".join(cmd),))
    ret = _run(cmd, exit_on_error=exit_on_error, **kwargs)
    print()
    return ret


def run_with_prefix(prefix, cmd, exit_on_error=True, **kwargs):
    log("@{bf}==>@| @!{0}", fargs=(" ".join(cmd),))
    ret = _run(prefix + cmd, exit_on_error=exit_on_error, **kwargs)
    print()
    return ret


def _run(cmd, exit_on_error=True, **kwargs):
    def create_protocol(*args, **kwargs):
        return MyProtocol(cmd, exit_on_error, *args, **kwargs)

    @asyncio.coroutine
    def run_coroutine(future):
        kwargs['emulate_tty'] = True
        transport, protocol = yield from async_execute_process(create_protocol, cmd, **kwargs)
        returncode = yield from protocol.complete
        future.set_result(returncode)

    future = asyncio.Future()
    task = asyncio.async(run_coroutine(future))
    get_loop().run_until_complete(task)
    retcode = future.result()
    if exit_on_error and retcode != 0:
        sys.exit(retcode)
    return retcode


class change_directory:
    def __init__(self, directory=''):
        self.directory = directory
        self.original_cwd = None

    def __enter__(self):
        self.original_cwd = os.getcwd()
        os.chdir(self.directory)
        return self.directory

    def __exit__(self, exc_type, exc_value, traceback):
        if self.original_cwd and os.path.exists(self.original_cwd):
            os.chdir(self.original_cwd)


def generated_venv_vars():
    venv_path = os.path.abspath(os.path.join(os.getcwd(), 'venv'))
    venv_python = os.path.join(venv_path, 'bin', 'python')
    venv_pip = os.path.join(venv_path, 'bin', 'pip')
    # Note(wjwwood): I have intentionally stripped a few choice env variables
    # from the environment passed to venv subprocesses, because they cause pip
    # to install things into the wrong prefix by default. Some related links:
    #   https://bitbucket.org/hpk42/tox/issue/148/__pyvenv_launcher__-causing-issues-on-os-x
    #   http://bugs.python.org/issue22490
    #   https://github.com/pypa/pip/issues/2031
    # This issue only occurs (based on my testing) iff when __PYVENV_LAUNCHER__ is set
    # and pip is run from the venv through a subprocess and shell=True for the subprocess.
    venv_env = {}
    for x in os.environ:
        if x not in ['__PYVENV_LAUNCHER__']:
            venv_env[x] = os.environ[x]

    def venv(cmd, **kwargs):
        kwargs['shell'] = True
        if 'env' not in kwargs:
            kwargs['env'] = venv_env
        this_venv_path = os.path.relpath(venv_path, os.getcwd())
        activate = os.path.join(this_venv_path, 'bin', 'activate')
        prefix = ['source', activate, '&&']
        log('(venv)')
        return run_with_prefix(prefix, cmd, **kwargs)

    return venv, venv_python, venv_pip