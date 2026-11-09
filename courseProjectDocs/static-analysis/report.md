# Static Analysis & Code Smell Detection: HTTPie CLI

## Tool used

HTTPie is a Python project, so we used the Python equivalents of SonarQube/PMD/ESLint. All three were run over the `httpie/` package (7,548 lines of code) on Python 3.13.

| Tool | Version | What it looks for | Config |
|---|---|---|---|
| **bandit** | 1.9.4 | Security issues: insecure TLS, missing timeouts, subprocess use, unsafe XML parsing, `assert` in production code | defaults |
| **pylint** | 4.1.3 | Bugs (`E`), warnings (`W`), code smells / refactor hints (`R`, `C`) | defaults |
| **flake8** | 7.5.0 (pycodestyle 2.15, pyflakes 4.1) | PEP 8 style and pyflakes errors | the project's own `[flake8]` section in `setup.cfg` (ignores E501, W503) |

How to reproduce:

```bash
pip install bandit pylint flake8
bandit -r httpie            # security
pylint httpie               # bugs + code smells
flake8 httpie               # style (uses setup.cfg)
```

Full output, before and after our fixes, is in [`results/`](results/):
`bandit-before.txt`, `bandit-after.txt`, `pylint-before.txt`, `pylint-after.txt`, `flake8-before.txt`, `flake8-after.txt`.

## Key findings

### Summary

| Tool | Before | After |
|---|---|---|
| bandit | 35 issues: **1 High**, **1 Medium**, 33 Low | 33 issues: 0 High, 0 Medium, 33 Low |
| pylint | 611 messages, score 8.44/10 | 608 messages, score 8.46/10 |
| flake8 | 0 (with project config) | 0 |

flake8 is clean because HTTPie already runs it in CI (`make codestyle`). The interesting findings came from bandit and pylint, which the project does not run.

### bandit

| Severity | ID | Location | Finding |
|---|---|---|---|
| **High** | B501 | `httpie/internal/update_warnings.py:44` | `requests.get(..., verify=False)`: TLS certificate checks turned off |
| **Medium** | B113 | `httpie/internal/update_warnings.py:44` | Same call has no `timeout` |
| Low (x20) | B101 | `downloads.py`, `sessions.py`, `cli/`, `output/`, ... | `assert` used for runtime checks; stripped under `python -O` |
| Low (x9) | B404 / B603 | `internal/daemons.py`, `manager/compat.py`, `output/ui/man_pages.py` | `subprocess` use. All calls pass fixed argument lists (no `shell=True`, no user input), so these are false positives for us. |
| Low (x2) | B105 | `sessions.py:144`, `sessions.py:280` | "Hardcoded password" `'None'`. False positive: it is the string compared against an auth type, not a password. |
| Low (x1) | B408 | `output/formatters/xml.py:7` | `xml.dom.minidom` import. HTTPie already parses with `defusedxml` and only uses `minidom` for the `Document` type, so not exploitable. |

### pylint

By count most of the 611 messages are documentation and style smells, not bugs:

| Count | Message | Kind |
|---|---|---|
| 207 / 62 / 61 | missing function / class / module docstring | smell |
| 37 | `import-outside-toplevel` | smell (mostly deliberate, to keep CLI startup fast) |
| 31 | `no-else-return` | smell |
| 22 | `inconsistent-return-statements` | smell |
| 15 | `unused-argument` | smell |
| 10 | `raise-missing-from` (W0707) | **smell that hides information** |
| 5 | `unused-variable` (W0612) | smell (dead code) |
| 4 | `unspecified-encoding` (W1514) | **portability bug** |
| 4 | `possibly-used-before-assignment` (E0606) | **possible bug** |

The ones we looked at closely:

- **E0606 `httpie/manager/tasks/plugins.py:237`**: `PluginInstaller.run` sets `status` in an `if/elif` chain with four branches (`install`, `upgrade`, `uninstall`, `list`) and no `else`, then `return status`. Any other action crashes with `UnboundLocalError` instead of a clean usage error. argparse limits the choices today, but `run()` is a public method and nothing inside it enforces that.
- **W0707 `httpie/cli/argtypes.py:223, 239, 266`**: `raise argparse.ArgumentTypeError(...)` inside `except` without `from exc`. The original `ValueError` / `KeyError` / `LookupError` becomes implicit context ("During handling of the above exception, another exception occurred"), which reads as a second bug in a traceback, and `__cause__` is `None`, so callers cannot get at the real reason.
- **W1514 `httpie/internal/update_warnings.py:34`**: `open(file)` with no encoding uses the platform locale (cp1252 on Windows) to read a JSON file that is written as UTF-8.
- E0606 in `cli/nested_json/parse.py:100-124`: false positive. Every branch of the `if/elif` chain either assigns the variables or calls `assert_cant_happen()`, which always raises, so they are always bound. pylint cannot see that the helper never returns.
- E0401 in `context.py`: `colorama` is a Windows-only dependency, not installed on Linux.
- E0202 in `compat.py`: intentional `cached_property` backport.

## Fix summary

| Student | Finding | Tool / ID | File | Fix |
|---|---|---|---|---|
| Tenzin | TLS verification disabled | bandit B501 (High) | `httpie/internal/update_warnings.py` | removed `verify=False` |
| Tenzin | HTTP request with no timeout | bandit B113 (Medium) | `httpie/internal/update_warnings.py` | added `timeout=FETCH_TIMEOUT` (10 s) |
| Tenzin | file opened with locale encoding | pylint W1514 | `httpie/internal/update_warnings.py` | `open(file, encoding='utf-8')` |
| Leon | status possibly unbound | pylint E0606 | `httpie/manager/tasks/plugins.py` | added an `else` branch that raises `ValueError` |

### Tenzin: insecure update check (`update_warnings.py`)

HTTPie checks `https://packages.httpie.io/latest.json` in a background daemon to warn about new releases. The request turned off certificate checking and had no timeout.

Before:

```python
def _fetch_updates(env: Environment) -> str:
    ...
    response = requests.get(PACKAGE_INDEX_LINK, verify=False)
```

After:

```python
FETCH_TIMEOUT = 10  # seconds (connect, read)

def _fetch_updates(env: Environment) -> str:
    ...
    response = requests.get(PACKAGE_INDEX_LINK, timeout=FETCH_TIMEOUT)
```

Why it matters:

- **B501**: with `verify=False` anyone on the network path (public Wi-Fi, a compromised proxy) can answer for `packages.httpie.io` with any certificate. The response decides which version number HTTPie tells the user to upgrade to, and the message points them at install instructions, so a spoofed answer can push users toward a fake "update". With verification on, `requests` checks the certificate against `certifi`'s CA bundle.
- **B113**: `requests` has no default timeout. A server that accepts the connection and never answers keeps the daemon process alive forever, and one is spawned per HTTPie invocation once the two-week interval passes. A `requests.Timeout` is now raised after 10 s, which the daemon runner already swallows like any other fetch error.
- **W1514** (same file): `_read_data_error_free` now reads the version file as UTF-8, matching how it is written.

Our Week 6 mocking test asserted the old insecure call (`assert_called_once_with(PACKAGE_INDEX_LINK, verify=False)`). It now asserts the timeout instead, so the test pins the secure behavior.

### Leon: unbound variable in `plugins.py`

`PluginInstaller.run` sets `status` in an `if/elif` chain with one branch for each known action. The chain had no `else`, and the method returns `status` after the chain.

Before:

```python
with enable_plugins(self.dir):
    if action == 'install':
        status = self.install(args.targets)
    elif action == 'upgrade':
        status = self.upgrade(args.targets)
    elif action == 'uninstall':
        status = self.uninstall(args.targets)
    elif action == 'list':
        status = self.list()

return status or ExitStatus.SUCCESS
```

After:

```python
    elif action == 'list':
        status = self.list()
    else:
        raise ValueError(f'unknown plugins action: {action!r}')

return status or ExitStatus.SUCCESS
```

Why it matters:

- An action that is not one of the four gave `UnboundLocalError: cannot access local variable 'status'`. That error points at the `return` line, not at the real cause, which is the bad action name.
- argparse limits the choices on the command line today. But `run()` is a public method, and a new subcommand or a direct call can send it a different value. The `else` makes the method safe without help from its callers.
- The new error names the bad action, so the traceback shows the cause.

We tried `parser.error(...)` first, because the method uses it for a missing subcommand. pylint still reported E0606, because it cannot see that `parser.error()` never returns. A wrong action at this point is a programming error, not a user error, so a `ValueError` is the correct signal. pylint accepts it.

### Verification

New file `tests/test_static_analysis_fixes.py`. Run against the old code, 3 of them fail (the other 2 are the timeout-propagation and UTF-8 read tests, which guard behavior rather than reproduce a bug). Against the fixed code all 5 pass.

| Test | Before fix | After fix |
|---|---|---|
| `test_fetch_updates_keeps_tls_certificate_verification_on` | fail | pass |
| `test_fetch_updates_sets_a_timeout` | fail | pass |
| `test_fetch_updates_propagates_timeout_instead_of_hanging` | pass | pass |
| `test_read_data_error_free_reads_utf8` | pass | pass |
| `test_plugins_run_rejects_unknown_action` | fail (`UnboundLocalError`) | pass |

```bash
pytest tests/test_static_analysis_fixes.py tests/test_mocking_update_warnings.py \
       tests/test_update_warnings.py tests/test_plugins_cli.py
```

Full suite (`pytest -n 4 tests httpie`): 1147 passed, 24 skipped, 4 xfailed, 3 failed. The 3 failures (`test_config_file_inaccessible` and two `big5` charset-detection cases in `test_encoding.py`) fail the same way on the code before our changes, so they are environment-related and not caused by these fixes.

Re-running the tools after the fixes: bandit has no High or Medium issues left, the targeted pylint W1514 in `update_warnings.py` and E0606 in `plugins.py` are gone (611 to 608 messages, score 8.44 to 8.46), and flake8 is still clean on `httpie/` and on the new test file.

### Not fixed, on purpose

- The 20 `assert` statements (B101) are internal invariants, not input validation, so `python -O` stripping them does not open a hole. Converting them all would be a large diff to upstream code for no behavior change.
- The remaining pylint messages are mostly missing docstrings and style preferences HTTPie has chosen not to follow. We did not want a style-only diff across the whole codebase.

## Group contributions

| | Tenzin | Leon |
|---|---|---|
| Ran bandit, pylint, flake8 and saved before/after output | yes | re-ran pylint after the E0606 fix |
| Triage of bandit findings (real vs false positive) | yes | |
| Triage of pylint findings | | yes |
| Fix | `update_warnings.py`: B501, B113, W1514 | `plugins.py`: E0606 |
| Regression tests in `tests/test_static_analysis_fixes.py` | update_warnings tests (4) | plugins unknown-action test (1) |
| Updated Week 6 mock test that asserted `verify=False` | yes | |
| This report | both | both |
