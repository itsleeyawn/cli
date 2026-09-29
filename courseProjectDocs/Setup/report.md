# Baseline Build & Test Report HTTPie CLI

## Environment
Windows 10, Python 3.11.15, `venv` + `pip install -e ".[dev]" pytest-html`, pytest 9.1.1, pytest-cov 7.1.0.

## Test Suite
1,028 pytest cases (37 modules + doctests). Mostly integration tests against a local httpbin server; unit tests for parsers/formatters; 33 system tests (installed CLI / subprocesses); 4 UI (`--help`) tests.

## Results
| Run | Passed | Failed | Skipped | xfail |
|---|---|---|---|---|
| 1,028 | 1,003 | 2 | 19 | 4 |

Failures: 2 Big5 charset-detection tests in `test_encoding.py`. Skips: mostly Unix-only tests on Windows.

## Coverage
Statement 90.7% (3,797/4,187), branch 80.9% (911/1,126).

## Observations
- UI code barely covered: `man_pages.py`, `rich_utils.py` 0%, `rich_help.py` 53%.
- Platform-specific code (`compat.py`, `daemons.py`) only partly covered on one OS.
- Branch coverage ~10 points below statement: error paths not tested.
