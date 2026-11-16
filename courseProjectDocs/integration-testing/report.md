# Integration Testing: HTTPie CLI

How to run the tests: see [`README.md`](README.md).

## Test design summary

### Tenzin: `http --download`

One `http --download` command goes through several modules and ends with a file on disk, so it is a good fit for integration testing. The tests run the real CLI against a local httpbin server and check the file and the exit status.

Modules integrated:

- `cli/argparser.py`: reads `--download`, `--output`, `--continue`
- `core.py`: creates the `Downloader` and sets the exit status
- `downloads.py`: adds the `Range` header for resume, picks the filename, appends or overwrites
- `client.py`: sends the request
- `output/streams.py`: writes the body to the file

Tests:

1. Normal download saves the exact bytes, named from the URL (normal)
2. Filename taken from the server's `Content-Disposition` header (normal)
3. `--continue` sends `Range`, gets a 206, and appends only the missing bytes (normal)
4. Server filename `../../evil.txt` stays in the current folder (edge, security)
5. Existing file is not overwritten; the new one is `64.bin-1` (edge)
6. `--continue` when the server ignores `Range`: the partial file is replaced, not appended to (failure)
7. 404 gives exit status 4 and creates no file (failure)
8. `--continue` on a file that is already complete (edge, fails: see BUG-1)

## Test data preparation

- Local httpbin server from `pytest-httpbin`, so no internet is needed.
- `/bytes/N?seed=S` returns the same bytes every time, `/range/N` supports resume, and `/response-headers` lets us set the filename header.
- Expected bytes are fetched with Python's `urllib`, not HTTPie, so the expected result doesn't depend on the code being tested.
- Resume tests start from a partial file (the first 700 bytes, or 300 junk bytes).
- Each test runs in its own temp folder.

## Execution and results

Command: `python -m pytest tests/test_integration_downloads.py -v`

- Tests 1 to 7: pass
- Test 8: xfail (known defect, BUG-1)
- Total: **7 passed, 1 xfailed**. The full suite has no new failures.

Observations:

- The duplicate file is named `64.bin-1`, not `64-1.bin`. This is by design in HTTPie, but the OS no longer recognizes the file type.
- pytest warns about an unclosed file for auto-named downloads, a minor resource leak in `downloads.py`.

## Bug reports

### BUG-1: `--continue` on an already complete file exits with an error

- **Severity:** Low
- **Version:** HTTPie 3.2.4
- **Steps:** download a file fully, then run the same command again with `--continue --output <file>`.
- **Expected:** exit 0, since the file is already complete (`wget -c` does this).
- **Actual:** exit 4 with `HTTP 416 REQUESTED RANGE NOT SATISFIABLE`. The file itself is fine.
- **Cause:** `Downloader.pre_request` always asks for the bytes after the end of the file, the server answers 416, and `core.py` treats that like any other 4xx error.

## Group contributions

**Tenzin**

- `http --download` integration tests (8 tests) in `tests/test_integration_downloads.py`
- Found BUG-1
- README and report

**Leon**

-
