# Requirements and Test Oracles

Project: HTTPie CLI (`httpie/cli`)

HTTPie is a command-line HTTP client. The requirements below were pulled from `docs/README.md`, code comments in `httpie/`, and the existing test suite under `tests/`. Each row lists where we found it.

## Functional Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| FR-1 | The system shall send an HTTP request from a single command specifying method, URL, headers, and body. | `docs/README.md` → "Main features", "Request items" |
| FR-2 | The system shall parse request items by separator: `:` for headers, `==` for query params, `=` for JSON string fields, `:=` for raw JSON values. | `docs/README.md` → "Request items", "Raw JSON" |
| FR-3 | The system shall send JSON by default and shall send form-encoded data when `--form` is given. | `docs/README.md` → "Forms" |
| FR-4 | The system shall support file uploads via multipart form data. | `docs/README.md` → "File upload forms" |
| FR-5 | The system shall print colorized, formatted output when writing to a terminal. | `docs/README.md` → "Colors and formatting" |
| FR-6 | The system shall support HTTPS, proxies, and custom certificates. | `docs/README.md` → "HTTPS", "Proxies" |
| FR-7 | The system shall support basic and digest authentication and allow auth plugins to add more schemes. | `docs/README.md` → "Authentication", "Auth plugins" |
| FR-8 | The system shall persist cookies and auth between runs when `--session` is used. | `docs/README.md` → "Sessions" |
| FR-9 | The system shall save the response body to a file with `--download` and shall be able to resume an interrupted download. | `docs/README.md` → "Download mode", "Resuming downloads"; `tests/test_downloads.py` (`test_download_resumed` covers resume at the `Downloader` level, not end-to-end via the CLI) |
| FR-10 | The system shall follow redirects when `--follow` is given, up to `--max-redirects`. | `docs/README.md` → "HTTP redirects" |
| FR-11 | The system shall return a distinct process exit code for each error category. | `httpie/status.py`: `ExitStatus` members (`ERROR_TIMEOUT = 2`, `ERROR_HTTP_3XX = 3`, `ERROR_HTTP_4XX = 4`, `ERROR_HTTP_5XX = 5`, `ERROR_TOO_MANY_REDIRECTS = 6`, `PLUGIN_ERROR = 7`) and `http_status_to_exit_status()`, which maps 3xx/4xx/5xx to those codes |
| FR-12 | The system shall build and print the request without sending it when `--offline` is given. | `docs/README.md` → "Offline mode"; `tests/test_offline.py` |
| FR-13 | The system shall provide a plugin manager (`httpie cli plugins`) to install, list, and uninstall plugins. | `docs/README.md` → "Plugin manager"; `httpie/manager/` |

## Non-Functional Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| NFR-1 | Usability: the command syntax shall be human-friendly. This is the project's stated main goal. | `docs/README.md` intro |
| NFR-2 | Performance: the system shall stream large responses incrementally with `--stream`. | `docs/README.md` → "Streamed responses" |
| NFR-3 | Portability: the system shall run on Windows, macOS, and Linux. | `docs/README.md` → "Main features"; `tests/test_windows.py` |
| NFR-4 | Compatibility: the system shall handle terminals without color or Unicode support. | `tests/test_encoding.py` |
| NFR-5 | Reliability: errors shall produce a readable error message and a non-zero exit code by default, with tracebacks available only via `--traceback`. | `tests/test_errors.py` (`test_error` vs. `test_error_traceback`); `docs/README.md` → "Scripting" |
| NFR-6 | Extensibility: plugins shall extend the system without changing core code. | `docs/README.md` → "Plugins" |

## Test Oracles

| Requirement ID | Requirement Description | Test Oracle (Expected Behavior) | Source |
|----------------|-------------------------|---------------------------------|--------|
| FR-11, NFR-5 | Distinct exit code per error; readable error by default | Running against an unreachable host exits with exit status 1 (`ExitStatus.ERROR`) and prints an error line; the traceback only appears with `--traceback`. Example: `assert r.exit_status == ExitStatus.ERROR` | `tests/test_errors.py` |
| FR-7, FR-1 | Auth and request sending | The local fake server echoes back what it received and the test checks it. Example: `assert r.json == {'authenticated': True, 'user': 'user'}` | `tests/test_auth.py` |
| FR-2, FR-3 | Separator parsing, JSON by default | JSON field check on the echoed body: `foo=bar` shows up under `json`. Example: `assert r.json['json']['foo'] == 'bar'` | `tests/test_httpie.py` |
| FR-5, FR-10 | Output formatting, redirects | Expected text appears in the output. Example: `assert HTTP_OK in r` (i.e., `'HTTP/1.1 200 OK'` is in the output) | `tests/test_httpie.py` |
| FR-9, FR-8 | Downloads, sessions | File on disk is correct. Downloaded content equals what the server serves; a session file written by run 1 is applied on run 2. Examples: `assert body == r` (`test_downloads.py`); `assert r2.json['headers']['Foo'] == 'Bar'` (`test_sessions.py`) | `tests/test_downloads.py`, `tests/test_sessions.py` |

## Assumptions

- The fake local server (`pytest-httpbin`) is correct.
- No real internet, DNS, or network delay is tested.
- HTTP correctness is trusted to the `requests` library.
- NFR-1 (human-friendly syntax) has no automated oracle. It is verified only indirectly, through the FR-2 parsing tests passing on the documented examples.