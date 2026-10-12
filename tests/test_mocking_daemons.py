"""
Unit Testing II (Mocking & Stubbing) - SWEN-777 - Leon

Component: httpie/internal/daemons.py

This module forks the process, calls os.setsid / os._exit, and launches a
subprocess with Popen. None of that can run for real inside pytest (a real
os.fork would duplicate the test runner, os._exit would kill it). The
baseline had this file at ~57% on Windows and ~44% on Linux, and the Windows
and macOS branches were never covered at all on any one OS. Here os, Popen
and the platform flags are all stubbed so each branch can be driven directly.
"""
import os
import sys
from unittest import mock

import pytest

from httpie.internal import daemons
from httpie.internal.daemons import (
    _spawn,
    _spawn_posix,
    _spawn_windows,
    _start_process,
    spawn_daemon,
)


class Exit(Exception):
    """Stand in for os._exit so the test can see it was called and with what code."""
    def __init__(self, code):
        self.code = code


@pytest.fixture
def fake_exit(monkeypatch):
    def _exit(code):
        raise Exit(code)
    monkeypatch.setattr(daemons.os, '_exit', _exit)


@pytest.fixture
def popen(monkeypatch):
    proc = mock.Mock(name='Popen()')
    cls = mock.Mock(name='Popen', return_value=proc)
    monkeypatch.setattr(daemons, 'Popen', cls)
    return cls


# 1. _start_process: builds the command line and hands it to Popen

def test_start_process_uses_python_and_main_entrypoint_when_not_frozen(popen, monkeypatch):
    monkeypatch.setattr(daemons, 'is_frozen', False)
    _start_process(['fetch_updates', '--daemon'], env={'A': '1'})

    popen.assert_called_once()
    argv = popen.call_args.args[0]
    kwargs = popen.call_args.kwargs
    assert argv[0] == sys.executable
    assert argv[1].endswith('__main__.py')
    assert argv[2:] == ['fetch_updates', '--daemon']
    assert kwargs['close_fds'] is True
    assert kwargs['shell'] is False
    assert kwargs['stdout'] is daemons.DEVNULL
    assert kwargs['stderr'] is daemons.DEVNULL
    assert kwargs['env'] == {'A': '1'}


def test_start_process_skips_entrypoint_when_frozen(popen, monkeypatch):
    # In a frozen binary sys.executable IS the http binary, so no __main__.py in between
    monkeypatch.setattr(daemons, 'is_frozen', True)
    _start_process(['check_status', '--daemon'])
    argv = popen.call_args.args[0]
    assert argv == [sys.executable, 'check_status', '--daemon']


# 2. _spawn_windows: Windows only flags, tested on any OS by faking the subprocess constants

def test_spawn_windows_sets_detached_creation_flags(popen, monkeypatch):
    import subprocess
    # These names only exist in subprocess on Windows, so inject them.
    startupinfo = mock.Mock(dwFlags=0)
    monkeypatch.setattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0x200, raising=False)
    monkeypatch.setattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000, raising=False)
    monkeypatch.setattr(subprocess, 'STARTF_USESHOWWINDOW', 1, raising=False)
    monkeypatch.setattr(subprocess, 'STARTUPINFO', mock.Mock(return_value=startupinfo), raising=False)
    monkeypatch.setattr(daemons, 'is_frozen', False)

    _spawn_windows(['fetch_updates', '--daemon'], {'PYTHONPATH': '/x'})

    kwargs = popen.call_args.kwargs
    assert kwargs['creationflags'] == 0x200 | 0x08000000
    assert kwargs['startupinfo'] is startupinfo
    assert startupinfo.dwFlags & 1
    assert kwargs['env'] == {'PYTHONPATH': '/x'}


# 3. _spawn_posix: the double fork. os.fork is stubbed to return a scripted sequence of pids.

@pytest.fixture
def posix_io(monkeypatch):
    # The grandchild closes stdin/stdout/stderr. Swapping the real sys streams fights with
    # pytest's output capture, so replace the module's reference to `sys` with a stand in
    # that has mock streams (and keeps sys.executable for _start_process).
    fake_sys = mock.Mock(stdin=mock.Mock(), stdout=mock.Mock(), stderr=mock.Mock(), executable=sys.executable)
    monkeypatch.setattr(daemons, 'sys', fake_sys)
    monkeypatch.setattr(daemons.os, 'setsid', mock.Mock())
    return fake_sys


def test_spawn_posix_parent_returns_immediately_after_first_fork(fake_exit, posix_io, popen, monkeypatch):
    monkeypatch.setattr(daemons.os, 'fork', mock.Mock(return_value=1234))  # pid > 0 means "I am the parent"
    assert _spawn_posix(['fetch_updates', '--daemon'], {}) is None
    daemons.os.setsid.assert_not_called()
    popen.assert_not_called()


def test_spawn_posix_first_fork_failure_exits_1(fake_exit, posix_io, monkeypatch):
    monkeypatch.setattr(daemons.os, 'fork', mock.Mock(side_effect=OSError('no more processes')))
    with pytest.raises(Exit) as e:
        _spawn_posix(['fetch_updates', '--daemon'], {})
    assert e.value.code == 1


def test_spawn_posix_intermediate_child_exits_0_after_second_fork(fake_exit, posix_io, monkeypatch):
    # first fork returns 0 (we are the child), second returns a pid (we are the intermediate parent)
    monkeypatch.setattr(daemons.os, 'fork', mock.Mock(side_effect=[0, 5678]))
    with pytest.raises(Exit) as e:
        _spawn_posix(['fetch_updates', '--daemon'], {})
    assert e.value.code == 0
    daemons.os.setsid.assert_called_once()


def test_spawn_posix_grandchild_on_linux_runs_main_in_process(fake_exit, posix_io, popen, monkeypatch):
    monkeypatch.setattr(daemons.os, 'fork', mock.Mock(side_effect=[0, 0]))
    monkeypatch.setattr(daemons.platform, 'system', lambda: 'Linux')
    main = mock.Mock()
    monkeypatch.setattr('httpie.core.main', main)
    monkeypatch.setenv('PYTHONPATH', 'original')   # so the update below gets undone after the test

    with pytest.raises(Exit) as e:
        _spawn_posix(['fetch_updates', '--daemon'], {'PYTHONPATH': '/x'})

    assert e.value.code == 0
    main.assert_called_once_with(['http', 'fetch_updates', '--daemon'])
    assert os.environ['PYTHONPATH'] == '/x'           # process context was applied in process
    popen.assert_not_called()
    for stream in (posix_io.stdin, posix_io.stdout, posix_io.stderr):
        stream.close.assert_called_once()


def test_spawn_posix_grandchild_on_macos_uses_subprocess(fake_exit, posix_io, popen, monkeypatch):
    monkeypatch.setattr(daemons.os, 'fork', mock.Mock(side_effect=[0, 0]))
    monkeypatch.setattr(daemons.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(daemons, 'is_frozen', False)
    main = mock.Mock()
    monkeypatch.setattr('httpie.core.main', main)

    with pytest.raises(Exit) as e:
        _spawn_posix(['fetch_updates', '--daemon'], {'PYTHONPATH': '/x'})

    assert e.value.code == 0
    main.assert_not_called()
    popen.assert_called_once()
    assert popen.call_args.kwargs['env'] == {'PYTHONPATH': '/x'}
    popen.return_value.communicate.assert_called_once()   # waits for the subprocess


def test_spawn_posix_grandchild_swallows_errors_from_main(fake_exit, posix_io, monkeypatch):
    # Even if the daemon task blows up, the grandchild must still exit 0 and not leak a traceback
    monkeypatch.setattr(daemons.os, 'fork', mock.Mock(side_effect=[0, 0]))
    monkeypatch.setattr(daemons.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr('httpie.core.main', mock.Mock(side_effect=RuntimeError('boom')))
    with pytest.raises(Exit) as e:
        _spawn_posix(['x'], {})
    assert e.value.code == 0


# 4. _spawn / spawn_daemon: platform dispatch and the process context that gets passed down

@pytest.mark.parametrize('windows, expected', [(True, '_spawn_windows'), (False, '_spawn_posix')])
def test_spawn_dispatches_on_platform(monkeypatch, windows, expected):
    monkeypatch.setattr(daemons, 'is_windows', windows)
    with mock.patch.object(daemons, '_spawn_windows') as win, mock.patch.object(daemons, '_spawn_posix') as posix:
        _spawn(['t', '--daemon'], {'K': 'V'})
    called = win if windows else posix
    other = posix if windows else win
    called.assert_called_once_with(['t', '--daemon'], {'K': 'V'})
    other.assert_not_called()


def test_spawn_daemon_adds_daemon_flag_and_pythonpath(monkeypatch):
    monkeypatch.setattr(daemons, 'is_frozen', False)
    monkeypatch.setenv('SOME_VAR', 'kept')
    with mock.patch.object(daemons, '_spawn') as spawn:
        spawn_daemon('fetch_updates')

    args, ctx = spawn.call_args.args
    assert args == ['fetch_updates', '--daemon']
    assert ctx['SOME_VAR'] == 'kept'                      # copy of the current environment
    assert os.path.isdir(ctx['PYTHONPATH'])               # repo root so the child can import httpie
    assert os.path.isdir(os.path.join(ctx['PYTHONPATH'], 'httpie'))


def test_spawn_daemon_frozen_does_not_touch_pythonpath(monkeypatch):
    monkeypatch.setattr(daemons, 'is_frozen', True)
    monkeypatch.delenv('PYTHONPATH', raising=False)
    with mock.patch.object(daemons, '_spawn') as spawn:
        spawn_daemon('fetch_updates')
    _, ctx = spawn.call_args.args
    assert 'PYTHONPATH' not in ctx
