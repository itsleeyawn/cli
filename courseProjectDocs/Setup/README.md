# Reproduce

Python 3.11, from repo root:

```bash
python -m venv venv
venv/Scripts/pip install -e ".[dev]" pytest-html
venv/Scripts/python -m pytest --cov=httpie --cov-branch \
  --cov-report=html:courseProjectDocs/Setup/testCoverage \
  --html=courseProjectDocs/Setup/testResults/report.html --self-contained-html
```

Open `testResults/report.html` and `testCoverage/index.html`.
