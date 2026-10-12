# Unit Testing II (Mocking and Stubbing): HTTPie CLI

Two components, one per student. Both live under `httpie/internal/` and are the part of HTTPie that checks for new releases in the background. We picked them because they are the clearest case in the codebase of code that talks to the outside world (a real HTTP API and the OS process layer) and because the baseline showed them as the worst covered non UI files.

| Student | Component | Test file | Why it needs mocking |
|---|---|---|---|
| Tenzin | `httpie/internal/update_warnings.py` | `tests/test_mocking_update_warnings.py` | Calls `requests.get` on `https://packages.httpie.io/latest.json` and spawns a daemon process. Also has time based logic (fetch every 2 weeks, warn every 1 week). |
| Leon | `httpie/internal/daemons.py` | `tests/test_mocking_daemons.py` | Does a double `os.fork`, calls `os.setsid` and `os._exit`, and launches a subprocess with `Popen`. Has separate Windows, Linux and macOS branches. |

Everything uses `unittest.mock` plus pytest's `monkeypatch`. No extra packages.

## Tenzin: update_warnings.py

### Mocking strategy

The existing `test_update_warnings.py` tests go through the whole CLI (`http fetch_updates --daemon`) and actually spawn the daemon, so they only cover the happy path and they are slow and a bit flaky. I wanted to test the module's functions directly.

What gets mocked and why:

- `requests.get` is patched on the module (`mock.patch.object(update_warnings.requests, 'get')`) and returns a `Mock(spec=requests.Response)` whose `.json()` gives back whatever version dict the test wants. This is the external API call. For the error case `raise_for_status` is given a `side_effect` of `requests.HTTPError`.
- `spawn_daemon` and `_fetch_updates` are patched when testing `fetch_updates` so I can assert which one got called for `lazy=True` vs `lazy=False` without forking anything.
- `fetch_updates` is patched when testing `maybe_fetch_updates` so the only thing under test is the 2 week interval check.
- `maybe_fetch_updates` is patched when testing `check_updates`, since the `_update_checker` decorator always calls it afterward and I did not want that side effect.
- `env.log_error` is patched with `mock.patch.object(env, 'log_error')` so I can assert the warning text and the `LogLevel.INFO` level instead of parsing stderr.

What is deliberately not mocked: the filesystem. `MockEnvironment` from `tests/utils` already gives a temp config dir, so the version info JSON file is written and read for real. That way the lockfile code in `open_with_lockfile` runs too. Time is also not mocked; instead the tests write `last_fetched_date` / `last_warned_date` as `now() minus some delta` and check whether the function acts.

### New test cases and rationale

| Group | Tests | What they pin down |
|---|---|---|
| `_fetch_updates` | 3 | Calls the right URL with `verify=False`, writes `last_released_versions` and a fresh `last_fetched_date`, keeps an existing `last_warned_date`, and on an HTTP error raises and writes nothing. |
| `fetch_updates` | 2 | `lazy=True` spawns the daemon and does not fetch inline; `lazy=False` does the opposite. |
| `maybe_fetch_updates` | 5 | Disabled in config means no fetch. No file yet means fetch. Otherwise only fetch once `FETCH_INTERVAL` has passed (tested just under and just over). |
| `_get_update_status` / `get_update_status` | 5 | No file, channel missing, up to date, newer version available (message contains the version and the docs URL), and a corrupt file is swallowed unless `developer_mode` is on. |
| `check_updates` | 4 | Logs at INFO with the version and records `last_warned_date`. Warned yesterday means no log. Warned more than `WARN_INTERVAL` ago means log again. Up to date means no log but the background fetch check still runs. |

19 tests, all pass, about 0.1 seconds total.

### Coverage

| File | Before (Week 5) | After |
|---|---|---|
| `httpie/internal/update_warnings.py` | 94.8% statements, 18 of 24 branches | 100% statements, 24 of 24 branches |

The missing lines were all error and interval branches: the `HTTPError` path, the "warned too recently" return, the "channel not in file" return, and the `developer_mode` passthrough.

## Leon: daemons.py

### Mocking strategy

This file cannot be tested for real inside pytest. A real `os.fork()` would clone the test runner, `os._exit()` would kill it, and `Popen` would actually launch `python -m httpie`. So every OS interaction is replaced:

- `os.fork` is a `Mock` with a `side_effect` list of return values. Returning a pid means "you are the parent", returning 0 means "you are the child", so `[0, 0]` walks the code all the way down to the grandchild and `[0, 5678]` stops at the intermediate process. `side_effect=OSError` tests the failure path.
- `os._exit` is replaced with a function that raises a custom `Exit(code)` exception. The test catches it with `pytest.raises(Exit)` and checks the exit code. This is the only way to see that `_exit` was called and the function did not continue past it.
- `os.setsid` is a plain `Mock` so we can assert it was called once in the child.
- `Popen` is patched on the `daemons` module and returns a `Mock` process so `communicate()` can be asserted on the macOS branch.
- `platform.system` is replaced with a lambda returning `'Linux'` or `'Darwin'` to pick the branch, and `is_windows` / `is_frozen` are set directly on the module.
- `httpie.core.main` is patched because the Linux grandchild runs the daemon task in process by calling it.
- The module's reference to `sys` is swapped for a `Mock` with mock stdin/stdout/stderr. First attempt patched `sys.stdin` etc. globally and that broke pytest's output capture, so the fixture replaces `daemons.sys` instead and keeps `executable` so `_start_process` still builds a correct command line.
- The Windows only `subprocess` constants (`CREATE_NO_WINDOW`, `STARTUPINFO`, ...) do not exist on macOS or Linux, so they are injected with `monkeypatch.setattr(..., raising=False)`. That is what makes `_spawn_windows` testable on any OS.

### New test cases and rationale

| Group | Tests | What they pin down |
|---|---|---|
| `_start_process` | 2 | Command line is `[python, httpie/__main__.py, task, --daemon]` with `close_fds`, `shell=False` and stdout/stderr to `DEVNULL`. When frozen, the `__main__.py` is left out. |
| `_spawn_windows` | 1 | `creationflags` is `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW` and `STARTF_USESHOWWINDOW` is set on the startupinfo. |
| `_spawn_posix` | 6 | Parent returns after first fork. First fork failing exits 1. Intermediate child exits 0 after second fork. Grandchild on Linux closes the std streams, applies the process context to `os.environ`, runs `main(['http', task, '--daemon'])` in process and exits 0. Grandchild on macOS uses `Popen` and waits with `communicate()`. An exception from `main` is swallowed and it still exits 0. |
| `_spawn` / `spawn_daemon` | 4 | Dispatches to the Windows or POSIX spawner based on `is_windows`. `spawn_daemon` builds `[task, '--daemon']`, copies the environment and sets `PYTHONPATH` to the repo root so the child can import httpie. Frozen builds leave `PYTHONPATH` alone. |

13 tests, all pass.

### Coverage

| File | Before (Week 5) | After |
|---|---|---|
| `httpie/internal/daemons.py` | 48.3% statements, 3 of 12 branches | 98.3% statements, 12 of 12 branches |

The one remaining miss is the `from subprocess import ...` line inside `_spawn_windows`, which only resolves on a real Windows interpreter.

## Coverage improvement analysis (project wide)

Run on macOS, Python 3.13.7, full suite with everything merged so far plus both Week 6 files:

| | After Week 5 | After Week 6 |
|---|---|---|
| Tests run | 1,056 | 1,088 |
| Passed / failed / skipped / xfail | 1,044 / 3 / 5 / 4 | 1,075 / 4 / 5 / 4 |
| Statements | 3,817 / 4,187 (91.2%) | 3,852 / 4,187 (92.0%) |
| Branches | 925 / 1,126 (82.1%) | 940 / 1,126 (83.5%) |

All 32 new tests pass. The failures are the same 2 Big5 charset tests and the Python 3.13 argparse message test from Week 5, plus `test_uploads.py::test_chunked_form` which POSTs to `http://pie.dev`, a real server on the internet, and got a network error on this run. None of them touch the code or tests in this PR.

Project wide it is a small bump because these two files are small. The point was less about the total and more that `daemons.py` was the single worst covered non UI file in the project and is now basically fully covered without any test ever forking a real process.

## What we learned

- Mock at the boundary you own. Patching `update_warnings.requests.get` (the name the module looks up) works, patching `requests.get` globally would too but is wider than needed.
- Replace `os._exit` with something that raises. A plain `Mock` would let the function keep running past the exit and the later asserts would be meaningless.
- Do not swap the real `sys.stdout` / `sys.stderr` in a pytest test. Patch the module's reference to `sys` instead.
- `side_effect` as a list is the cleanest way to script a sequence like fork, fork.
- The parts that did not need mocking (temp config dir, real JSON file, real lockfile) we left real so the tests still exercise that code.