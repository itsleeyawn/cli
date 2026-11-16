# Integration Testing: Reproduce

- **Tenzin:** `http --download` (`core`, `cli/argparser`, `client`, `downloads`, `output/streams`, filesystem), test file `tests/test_integration_downloads.py`
- **Leon:** `http --session` (`cli/argparser`, `client`, `sessions`, `config`), test file `tests/test_integration_sessions.py`

## Setup

Same venv as the other weeks. The test extras include `pytest-httpbin`, which starts a local httpbin server automatically, so no internet or separate server is needed.

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'

# Windows
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[test]"
```

## Run the integration tests

From the repo root:

```bash
python -m pytest tests/test_integration_downloads.py tests/test_integration_sessions.py -v
```

Expected result: `9 passed, 1 xfailed`. The xfail is the defect described in `report.md` (resuming an already complete download exits with status 4). It is marked `xfail` so the suite stays green while the bug is open; if it is ever fixed the test will start passing and pytest will report `XPASS(strict)` as a failure, because the marker uses `strict=True`. That is the signal to remove the marker.

## Run the whole suite

```bash
python -m pytest tests httpie
```

To check our tests did not break anything else. On our machine three existing tests fail independently of our changes (`test_config_file_inaccessible` and two `big5` cases in `test_encoding.py`); they fail the same way on `master` without our test file.
