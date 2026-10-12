# Mutation Testing: Reproduce

Tool: [mutmut](https://mutmut.readthedocs.io/) 3.x. Config lives in `setup.cfg` under `[mutmut]`. HTTPie had no mutation testing set up before this, we added it.

Two components, one per student:

| Student | Mutated file | Killing tests |
|---|---|---|
| Tenzin | `httpie/utils.py` | `tests/test_mutation_utils.py` |
| Leon | `httpie/cli/argtypes.py` | `tests/test_mutation_argtypes.py` |

## Setup

Same venv as the other weeks, plus mutmut:

```bash
# macOS / Linux
venv/bin/pip install -e ".[dev]" mutmut

# Windows
venv\Scripts\pip install -e ".[dev]" mutmut
```

## Run the killing tests on their own

```bash
python -m pytest tests/test_mutation_utils.py tests/test_mutation_argtypes.py -v
```

Should be 59 passed in well under a second.

## Run mutation testing

From the repo root:

```bash
mutmut run
```

mutmut copies `httpie/` and `tests/` into a `mutants/` folder (gitignored), generates mutants for the two files listed in `only_mutate`, and runs the test files listed in `pytest_add_cli_args_test_selection` against each one. Takes about a minute. We deliberately only run the fast unit test files, not the whole suite, because the full suite needs httpbin and takes 90 seconds per run.

Then:

```bash
mutmut results            # one line per mutant with killed / survived / no tests
mutmut show <mutant id>   # the diff for one mutant, e.g. mutmut show httpie.utils.x_url_as_host__mutmut_3
mutmut browse             # interactive TUI
```

`initial-results.txt` and `final-results.txt` in this folder are the `mutmut results` output before and after we added the killing tests, with the totals at the top. To reproduce the initial numbers, temporarily remove the two `test_mutation_*.py` entries from `pytest_add_cli_args_test_selection` in `setup.cfg`, delete `mutants/`, and run again.

## Notes

- `mutmut run` must be re-run from scratch (delete `mutants/`) after changing the test selection in `setup.cfg`, otherwise it reuses cached results.
- Mutant status meanings: **killed** = at least one test failed, **survived** = all tests passed (the mutant was not detected), **no tests** = mutmut found no test that executes that function at all.
- Windows: mutmut 3 uses `fork` for process isolation by default, which is not available on Windows. Add `process_isolation=spawn` under `[mutmut]` in `setup.cfg` if running there.
