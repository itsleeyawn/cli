# Unit Testing I (Extend Coverage): HTTPie CLI

Author: Tenzin. New tests are in `tests/test_unit_coverage_extension.py` (7 test functions, 28 cases once parametrization is counted).

## How I picked targets

I went through the baseline coverage HTML from the Setup step and looked for red and yellow lines in modules that are not UI code. Most of the existing suite is integration tests that go through httpbin, so a lot of small helper functions and especially their error branches never get called directly. Everything I added is a plain unit test. No server, no subprocess, runs in well under a second.

## New test cases and rationale

| # | Target (uncovered lines in baseline) | Test | Why |
|---|---|---|---|
| 1 | `utils.humanize_bytes` (104 to 121, the whole body) | `test_humanize_bytes_boundaries` | Only the doctests touched this and those don't count toward coverage. I check 0, the `n == 1` special case, 1023 vs 1024 at the first threshold, TB, and PB with precision 0. |
| 2 | `utils.is_version_greater` (283, 284) | `test_is_version_greater_edge_cases` | The `except ValueError: break` branch for non numeric parts like `3.2.0rc1` was never hit. Also checks equal versions and 4 part versions where only the first 3 parts matter. |
| 3 | `cli/argtypes.SessionNameValidator` (37) | `test_session_name_validator_*` | The reject path that raises `argparse.ArgumentError` was uncovered. Also confirms that anything with a path separator skips the name regex entirely. |
| 4 | `cli/requestitems.load_text_file` and `load_json` (217 to 223, 229, 230) | `test_load_text_file_*`, `test_load_json_invalid_json_*` | All three error paths for `=@`, `:=@` and `:=` items were uncovered: missing file, non UTF-8 file, and invalid JSON. Each one should come back as a `ParseError` that still includes the original argument text. |
| 5 | `config.read_raw_config` and `get_default_config_dir` (43 to 55, 77) | `test_read_raw_config_*`, `test_default_config_dir_*` | Invalid JSON raises `ConfigFileError`, missing file returns `None`, and a directory (OSError but not FileNotFoundError) raises `ConfigFileError`. The `HTTPIE_CONFIG_DIR` and `XDG_CONFIG_HOME` branches are tested with `monkeypatch`. |
| 6 | `models.infer_requests_message_kind` (186) | `test_infer_requests_message_kind` | The `TypeError` branch for an unknown message type was uncovered. |
| 7 | `cli/nested_json/tokens.Path.reconstruct` (69 to 76) | `test_nested_json_path_reconstruct` | Root KEY, nested KEY, INDEX and APPEND were all uncovered. This is the string users see in error messages for nested `--form` keys, so it is worth pinning down. |

## Test results

| Run | Total | Passed | Failed | Skipped | xfail |
|---|---|---|---|---|---|
| Baseline (Setup, Windows) | 1,028 | 1,003 | 2 | 19 | 4 |
| After new tests (macOS, Python 3.13.7) | 1,056 | 1,044 | 3 | 5 | 4 |

New tests: 28 run, 28 passed, 0 failed. I did not change any existing tests.

The skip count is lower than baseline because Leon ran the baseline on Windows and I ran this on macOS, so the Unix only tests he skipped actually run here.

Three failures:

- The same 2 Big5 tests in `test_encoding.py` as baseline. The test sends Big5 encoded Chinese text and expects `charset_normalizer` to detect it, but it guesses a Korean encoding instead and the output comes back garbled. I also ran the suite on Linux and it fails there too, so at this point it has failed on Windows, Linux and macOS. It is a `charset_normalizer` version issue, not platform specific and not related to our changes.
- `test_cli_ui.py::test_naked_invocation[args3]` is new and is a Python version thing. My venv is on Python 3.13.7 and argparse changed how it prints the "invalid choice" message (the choices are no longer wrapped in quotes), so the expected string in the test no longer matches. On Python 3.11 like the baseline it passes. Not caused by anything in this PR.

## Coverage improvement vs. baseline

| Metric | Baseline | After | Change |
|---|---|---|---|
| Statements covered | 3,797 / 4,187 (90.7%) | 3,817 / 4,187 (91.2%) | +20 lines |
| Branches covered | 911 / 1,126 (80.9%) | 925 / 1,126 (82.1%) | +14 branches |

Per file, only the modules my tests touch:

| File | Baseline | After |
|---|---|---|
| `httpie/utils.py` | 88.5% | 95.4% |
| `httpie/config.py` | 91.6% | 97.9% |
| `httpie/cli/requestitems.py` | 92.0% | 98.0% |
| `httpie/cli/nested_json/tokens.py` | 91.8% | 100% |
| `httpie/cli/argtypes.py` | 94.9% | 95.6% |
| `httpie/models.py` | 95.6% | 96.5% |

That is 27 statements in these 6 files that were red before. The project wide gain is a bit less than that (+20) because a couple of platform dependent modules (`context.py`, `internal/daemons.py`, `compat.py`) cover differently on macOS than on the Windows baseline, so some lines moved the other way for reasons unrelated to the new tests.

## Observations

- Most of what is still red is UI (`man_pages.py` and `rich_utils.py` are both at 0%) and platform specific code. Plain unit tests won't get those, they need the terminal and OS mocked out, which is what Week 6 is for.
- The error path tests felt like the most useful ones. `load_text_file` and `read_raw_config` had zero coverage on every `except` branch, so if someone broke the error message the user sees, nothing would have caught it.
- Doctests in `utils.py` run as part of the suite but don't register with `--cov`, which is why `humanize_bytes` showed up as untested even though it has examples in the docstring.

## Leon's tests

Added to the same file, `tests/test_unit_coverage_extension.py`, as sections 8 to 13 (6 test functions, 23 cases with parametrization). Picked modules Tenzin's tests did not touch.

| # | Target (uncovered lines in baseline) | Test | Why |
|---|---|---|---|
| 8 | `downloads.filename_from_url` (118) and `trim_filename` (140) | `test_filename_from_url_extension_handling`, `test_trim_filename_keeps_extension_when_it_can` | The `.htm` to `.html` fix and the trim branch where the cut is longer than the name itself were never hit. Also checks the `index` fallback for an empty URL path and unknown content types. |
| 9 | `uploads.is_stdin` (93) | `test_is_stdin_*` | The `except` branch for file objects without `fileno()` (like `BytesIO`) was uncovered. The fd match is tested with a fake since pytest swaps out `sys.stdin`. |
| 10 | `utils.parse_content_type_header` (partial branches 211, 214) | `test_parse_content_type_header` | Quoted values, trailing empty params, mixed case keys and params with no `=` were not all covered. |
| 11 | `output/writer.write_stream_with_colors_win` (89 to 97) | `test_write_stream_with_colors_win_*` | Windows only code path that was 0% covered on every OS. It is plain Python so it can be tested with a fake outfile: chunks with ANSI escapes go to `.write()` as str, everything else to `.buffer` as bytes. |
| 12 | `cli/argtypes.PromptMixin` (138 to 145) and `KeyValueArg` / `Escaped` reprs (25, 45) | `test_prompt_password_*`, `test_argtypes_reprs` | Ctrl-C or EOF during a password prompt should write a newline to stderr and `sys.exit(0)` cleanly. That path was never tested. |
| 13 | `models.HTTPMessage` (31, 35, 40, 45) | `test_http_message_base_methods_are_abstract` | The base class `NotImplementedError` stubs were uncovered. |

Results: 23 run, 23 passed, 0 failed.

Full suite with all Unit Testing I tests (Windows, Python 3.11.15): 1,079 tests, 1,052 passed, 4 failed, 19 skipped, 4 xfail. Statements 3,842 / 4,187 (91.8%), branches 934 / 1,126 (82.9%). The 4 failures are the 2 Big5 tests from baseline plus 2 of Tenzin's tests (`test_session_name_validator_accepts_names_and_paths[./path/to/session.json]` and `test_load_text_file_missing_file_raises_parse_error`) that only fail on Windows because of backslash paths.

Per file after adding these:

| File | Before | After |
|---|---|---|
| `httpie/cli/argtypes.py` | 95.6% | 99.4% |
| `httpie/models.py` | 96.5% | 100% |
| `httpie/output/writer.py` | 82.9% | 92.5% |