# Unit Testing I: Reproduce

New tests live in `tests/test_unit_coverage_extension.py`. They are pure unit tests (no httpbin server needed).

Python 3.11, from repo root, same venv as the Setup step:

```bash
# Windows
python -m venv venv
venv\Scripts\pip install -e ".[dev]" pytest-html

# macOS / Linux
python -m venv venv
venv/bin/pip install -e ".[dev]" pytest-html
```

Run just the new tests (fast, ~0.1s):

```bash
python -m pytest tests/test_unit_coverage_extension.py -v
```

Full suite with updated coverage + results (what `report.md` numbers come from):

```bash
python -m pytest --cov=httpie --cov-branch \
  --cov-report=html:courseProjectDocs/Unit-Testing/testCoverage \
  --html=courseProjectDocs/Unit-Testing/testResults/report.html --self-contained-html
```

Open `testResults/report.html` and `testCoverage/index.html`. Compare against `courseProjectDocs/Setup/testCoverage/index.html` for the baseline.


## Week 6: mocking tests

Two more files, same venv as above:

```bash
python -m pytest tests/test_mocking_update_warnings.py tests/test_mocking_daemons.py -v
```

No network or subprocesses, everything external is mocked with `unittest.mock` and `monkeypatch`. See `mocking.md` for what gets mocked and why. Rerun the full coverage command above to refresh `testCoverage/` and `testResults/`.