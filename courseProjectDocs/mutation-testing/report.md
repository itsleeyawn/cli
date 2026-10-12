# Mutation Testing: HTTPie CLI

## Existing setup

None. HTTPie does not have mutation testing configured. There is no mutmut, cosmic-ray or similar in `setup.cfg`, `Makefile`, or the GitHub workflows. We added one.

## Setup we added

- Tool: mutmut 3.8 (`pip install mutmut`).
- Config: `[mutmut]` section in `setup.cfg`. `source_paths=httpie`, `only_mutate` limited to our two files, and `pytest_add_cli_args_test_selection` limited to the fast unit test files from Weeks 5 and 6 plus the two new files from this week.
- Report location: `courseProjectDocs/mutation-testing/initial-results.txt` and `final-results.txt`. Both are the `mutmut results` output with totals at the top. The raw per mutant data is in `mutants/` which is gitignored since it is regenerated every run.

Why only two files and only the unit tests: mutmut runs the selected tests once per mutant. Mutating the two files alone produced 350 mutants. The full HTTPie suite takes about 90 seconds and needs a local httpbin, so 350 runs of that is not something we could iterate on. The unit test files run in under a second, so a full mutation pass is about a minute.

Components, one per student:

| Student | File | Why this file |
|---|---|---|
| Tenzin | `httpie/utils.py` | Small pure helpers (byte formatting, version compare, cookie parsing, content type parsing). Already had Week 5 tests from both of us, so a good check of whether those tests actually constrain behavior or just execute lines. |
| Leon | `httpie/cli/argtypes.py` | The `argparse` type functions that validate CLI input. `parse_format_options` in particular is only covered by a doctest and doctests do not run under mutmut. |

## Initial mutation score

Run on macOS with the Week 5 and 6 unit test files only (`initial-results.txt`):

| | Count |
|---|---|
| Total mutants | 350 |
| Killed | 51 |
| Survived | 63 |
| No tests | 236 |
| Score (killed / total) | 14.6% |
| Score (killed / mutants that had a test) | 44.7% |

Where the survivors were:

| Function | Survived | What survived |
|---|---|---|
| `argtypes.parse_format_options` | 41 | Everything. Only a doctest covered it. |
| `utils.humanize_bytes` | 9 | Default precision 2 changed to 3. `1<<20` doubled to `2<<20`, same for GB. `'MB'` lowercased. Our Week 5 test always passed `precision` explicitly and only tested B, kB, TB and PB, so the MB and GB rows were free to change. |
| `utils.url_as_host` | 5 | No test at all touched it. |
| `utils.load_json_preserve_order_and_dupe_keys` | 2 | `object_pairs_hook` removed. No test had duplicate keys. |
| `utils.is_version_greater` | 1 | `[:3]` changed to `[:4]`. No test had a 4 part version that would change the answer. |
| `argtypes.KeyValueArg.__init__`, `KeyValueArgType.__init__` | 5 | Field assignment swaps, `special_characters` not populated. |

The 236 "no tests" were whole functions nothing in the unit test selection called: the cookie expiry code in `utils` (`get_expired_cookies`, `_max_age_to_expires`, `split_cookies`), `parse_content_type_header`, `url_as_host`, `as_site` / `get_site_paths`, `split_iterable`, `unwrap_context`, and in `argtypes` the `readable_file_arg`, `response_charset_type`, `response_mime_type` validators, `PromptMixin`, `KeyValueArgType.tokenize` and the `AuthCredentials` / `SSLCredentials` classes.

The thing that stood out: 95% line coverage on `utils.py` after Week 5 and still 9 of humanize_bytes' mutants survived. Line coverage says the line ran, it does not say the assertion would notice if the line changed.

## New tests

Tenzin, `tests/test_mutation_utils.py` (17 test functions, 27 cases with parametrization):

| Test | Kills |
|---|---|
| `test_humanize_bytes_default_precision_is_two` | precision default 2 to 3 |
| `test_humanize_bytes_each_unit_boundary_and_suffix` | MB and GB factor and suffix mutations, one case per unit |
| `test_is_version_greater_ignores_fourth_component` | `[:3]` to `[:4]` |
| `test_load_json_keeps_duplicate_keys_and_order` | `object_pairs_hook` removed |
| `test_parse_content_type_header_strips_quotes_and_spaces_from_key_and_value`, `test_parse_content_type_header_param_edge_cases` | strip character set changes, quotes, params with no `=`, trailing empty params, key lowercasing |
| `test_parse_content_type_header_splits_on_first_equals` | `find` to `rfind` |
| `test_url_as_host` | all 5 (split char, index) |
| `test_split_cookies`, `test_max_age_to_expires_*`, `test_get_expired_cookies*` | the cookie code that had no tests (53 mutants) |
| `test_split_iterable`, `test_unwrap_context_*`, `test_get_content_type_and_repr_dict` | the remaining "no tests" helpers |

Leon, `tests/test_mutation_argtypes.py` (20 test functions, 32 cases with parametrization):

| Test | Kills |
|---|---|
| `test_parse_format_options_does_not_mutate_defaults` | `deepcopy` removed |
| `test_parse_format_options_updates_the_right_key` (4 cases) | lowercasing removed, comma split changed, section/key swapped |
| `test_parse_format_options_true_and_false_map_to_bools` | `value_map` literal changes |
| `test_parse_format_options_numeric_strings_become_ints` | `isnumeric` branch removed |
| `test_parse_format_options_rejects_*` (3 tests) | every error message and type check mutation |
| `test_parse_format_options_with_no_defaults_accepts_anything` | `setdefault` branch |
| `test_key_value_arg_stores_all_fields`, `test_key_value_arg_type_collects_special_characters_from_every_separator` | the `__init__` field swaps |
| `test_key_value_arg_type_tokenize_escapes`, `test_key_value_arg_type_escaped_separator_is_not_a_separator`, `test_key_value_arg_type_longest_separator_at_same_position_wins` | 26 `tokenize` mutants and most of `__call__`. These were only covered by integration tests before. |
| `test_prompt_password_formats_prompt_exactly`, `test_prompt_password_exit_code_is_zero` | prompt string and `sys.exit(1)` |
| `test_readable_file_arg`, `test_response_charset_type`, `test_response_mime_type_*` | the three validators that had no tests |

## Final mutation score

Re-run with the new test files added to the selection (`final-results.txt`):

| | Initial | Final |
|---|---|---|
| Total mutants | 350 | 350 |
| Killed | 51 | 294 |
| Survived | 63 | 13 |
| No tests | 236 | 43 |
| Score (killed / total) | 14.6% | 84.0% |
| Score (killed / tested) | 44.7% | 95.8% |

Per file:

| File | Killed | Survived | No tests |
|---|---|---|---|
| `httpie/utils.py` | 148 | 9 | 24 |
| `httpie/cli/argtypes.py` | 146 | 4 | 19 |

## Mutants killed and survived, analysis

The 13 that still survive are all ones we looked at and decided were equivalent mutants (the change does not alter observable behavior) or not worth a test:

- `JsonDictPreservingDuplicateKeys._ensure_items_used` (5): this is a hack that inserts a dummy `__hack__` key so the C JSON encoder sees a non empty dict. The mutants change the dummy value or key. Any value works, so no test can tell the difference.
- `get_content_type` (3): `strict=False` changed to `strict=None` or dropped, and the `[0]` index tweaks. `None` is falsy so `mimetypes` treats it the same, and the one extension we test that differs between strict and non strict (`.pict`) still resolves the same way on this Python version.
- `parse_content_type_header`: strip set changed from `"' ` to `XX"' XX`. Only differs if a key or value starts or ends with the letter X, which does not happen in any realistic Content-Type.
- `readable_file_arg`: `open(filename, 'rb')` to `open(filename)`. Text vs binary mode, both succeed or fail the same way for the readability check.
- `response_charset_type`: `''.encode(encoding)` to `'XXXX'.encode(encoding)`. Both raise `LookupError` for an unknown codec and succeed otherwise.
- `KeyValueArgType.__call__` (2): the `sorted(..., key=len)` tweaks. Our longest-separator test kills some of these but with only two separators the sort order happens to come out the same for a couple of variants.

The 43 remaining "no tests" are `AuthCredentials` and `SSLCredentials` (interactive password prompting, covered by `test_auth.py` through the CLI, which we left out of the selection on purpose), `utils.as_site` / `get_site_paths` (frozen binary install paths, only meaningful in a PyInstaller build), and the `__repr__` / `_getpass` one liners.

Takeaways:

- Parametrized tests that only ever pass one value for an argument leave the default free to mutate. `humanize_bytes` had a default of 2 that nothing checked.
- Hitting every row of a lookup table matters. The MB and GB rows were never touched even though the function was "covered".
- Doctests are good documentation but mutmut does not run them, so `parse_format_options` looked tested and was not.
- Mutation score is a much harsher number than line coverage. The same `utils.py` was 95% line covered after Week 5 and only 14.6% of its mutants were killed.

## Group contributions

| | Tenzin | Leon |
|---|---|---|
| Set up mutmut config in `setup.cfg`, picked the test selection | yes | |
| Component | `httpie/utils.py` | `httpie/cli/argtypes.py` |
| New tests | `tests/test_mutation_utils.py`, 27 cases | `tests/test_mutation_argtypes.py`, 32 cases |
| Mutants killed by own tests | 41 to 148 on utils | 10 to 146 on argtypes |
| Initial and final runs, results files, README | yes | |
| Survivor analysis | utils survivors | argtypes survivors |
| This report | both | both |
