"""
Unit Testing I (Extend Coverage) - SWEN-777

Targets picked from the baseline coverage report (courseProjectDocs/Setup/testCoverage):
uncovered helper/edge-case logic that the existing integration-heavy suite never hits.
No httpbin server needed; these are pure unit tests.
"""
import argparse
import io
import json
import sys

import pytest
import requests

from httpie.cli.argtypes import Escaped, KeyValueArg, PromptMixin, SessionNameValidator
from httpie.cli.exceptions import ParseError
from httpie.cli.nested_json.tokens import Path as NestedPath, PathAction
from httpie.cli.requestitems import load_json, load_text_file
from httpie.config import ConfigFileError, get_default_config_dir, read_raw_config
from httpie.downloads import filename_from_url, trim_filename
from httpie.models import HTTPMessage, infer_requests_message_kind, RequestsMessageKind
from httpie.output.writer import write_stream_with_colors_win
from httpie.uploads import is_stdin
from httpie.utils import humanize_bytes, is_version_greater, parse_content_type_header


# 1. httpie/utils.py::humanize_bytes -- whole body uncovered (lines 104-121)

@pytest.mark.parametrize('n, precision, expected', [
    (0, 2, '0.00 B'),            # smallest input, hits the (1, 'B') fallback
    (1, 2, '1 B'),               # special-cased singular branch
    (1023, 2, '1023.00 B'),      # just under the first threshold
    (1024, 2, '1.00 kB'),        # exactly on a threshold
    (1 << 40, 1, '1.0 TB'),
    (1 << 50, 0, '1 PB'),        # largest unit, precision 0
])
def test_humanize_bytes_boundaries(n, precision, expected):
    assert humanize_bytes(n, precision=precision) == expected


# 2. httpie/utils.py::is_version_greater -- non-numeric part branch (283-284)

@pytest.mark.parametrize('v1, v2, expected', [
    ('3.2.0', '3.1.9', True),
    ('3.2.0', '3.2.0', False),          # equal -> not greater
    ('3.2.0rc1', '3.2.0', False),       # 'rc1' breaks parsing -> (3, 2) vs (3, 2, 0)
    ('3.2.1', '3.2.0rc1', True),
    ('4.0.0.dev0', '3.9.9', True),      # only first 3 parts are compared
    ('3.2', '3.2.0', False),
])
def test_is_version_greater_edge_cases(v1, v2, expected):
    assert is_version_greater(v1, v2) is expected


# 3. httpie/cli/argtypes.py::SessionNameValidator -- error branch (line 37)

def test_session_name_validator_rejects_invalid_name():
    validator = SessionNameValidator('bad session name')
    with pytest.raises(argparse.ArgumentError) as exc:
        validator('bad name!')
    assert 'bad session name' in str(exc.value)


@pytest.mark.parametrize('value', [
    'my-session_1',          # allowed chars
    './path/to/session.json'  # anything containing a path separator is accepted as a path
])
def test_session_name_validator_accepts_names_and_paths(value):
    assert SessionNameValidator('x')(value) == value


# 4. httpie/cli/requestitems.py::load_text_file / load_json -- error paths (217-223, 229-230)

def test_load_text_file_missing_file_raises_parse_error(tmp_path):
    missing = tmp_path / 'nope.txt'
    arg = KeyValueArg(key='k', value=str(missing), sep='=@', orig=f'k=@{missing}')
    with pytest.raises(ParseError) as exc:
        load_text_file(arg)
    assert arg.orig in str(exc.value)


def test_load_text_file_non_utf8_raises_parse_error(tmp_path):
    binary = tmp_path / 'blob.bin'
    binary.write_bytes(b'\xff\xfe\x00\x80')
    arg = KeyValueArg(key='k', value=str(binary), sep='=@', orig=f'k=@{binary}')
    with pytest.raises(ParseError) as exc:
        load_text_file(arg)
    assert 'not a UTF-8 or ASCII-encoded text file' in str(exc.value)


def test_load_json_invalid_json_raises_parse_error():
    arg = KeyValueArg(key='k', value='{not json', sep=':=', orig='k:={not json')
    with pytest.raises(ParseError) as exc:
        load_json(arg, arg.value)
    assert "'k:={not json'" in str(exc.value)


# 5. httpie/config.py::read_raw_config / get_default_config_dir -- error + env branches

def test_read_raw_config_invalid_json_raises_config_file_error(tmp_path):
    cfg = tmp_path / 'config.json'
    cfg.write_text('{"default_options": [', encoding='utf-8')
    with pytest.raises(ConfigFileError) as exc:
        read_raw_config('config', cfg)
    assert 'invalid config file' in str(exc.value)
    assert str(cfg) in str(exc.value)


def test_read_raw_config_missing_file_returns_none(tmp_path):
    assert read_raw_config('config', tmp_path / 'missing.json') is None


def test_read_raw_config_unreadable_path_raises_config_file_error(tmp_path):
    # A directory opens with an OSError that is not FileNotFoundError.
    with pytest.raises(ConfigFileError) as exc:
        read_raw_config('config', tmp_path)
    assert 'cannot read config file' in str(exc.value)


def test_default_config_dir_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv('HTTPIE_CONFIG_DIR', str(tmp_path))
    assert get_default_config_dir() == tmp_path


def test_default_config_dir_uses_xdg_when_set(monkeypatch, tmp_path):
    monkeypatch.delenv('HTTPIE_CONFIG_DIR', raising=False)
    monkeypatch.setattr('httpie.config.is_windows', False)
    monkeypatch.setattr('httpie.config.Path.home', lambda: tmp_path)  # no legacy ~/.httpie
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    assert get_default_config_dir() == tmp_path / 'xdg' / 'httpie'


# 6. httpie/models.py::infer_requests_message_kind -- TypeError branch (line 186)

def test_infer_requests_message_kind():
    assert infer_requests_message_kind(requests.PreparedRequest()) is RequestsMessageKind.REQUEST
    assert infer_requests_message_kind(requests.Response()) is RequestsMessageKind.RESPONSE
    with pytest.raises(TypeError, match='Unexpected message type: dict'):
        infer_requests_message_kind({})


# 7. httpie/cli/nested_json/tokens.py::Path.reconstruct -- all three kinds (69-76)

@pytest.mark.parametrize('path, expected', [
    (NestedPath(PathAction.KEY, 'root', is_root=True), 'root'),
    (NestedPath(PathAction.KEY, 'child'), '[child]'),
    (NestedPath(PathAction.INDEX, 3), '[3]'),
    (NestedPath(PathAction.APPEND), '[]'),
])
def test_nested_json_path_reconstruct(path, expected):
    assert path.reconstruct() == expected


# ---- Leon's tests (8 to 13): modules not touched above ----

# 8. httpie/downloads.py: filename_from_url .htm fix (line 118) and trim_filename (line 140)

@pytest.mark.parametrize('url, content_type, expected', [
    ('http://example.org/page', 'text/html', 'page.html'),          # mimetypes gives .htm, we want .html
    ('http://example.org/readme', 'text/plain; charset=utf-8', 'readme.txt'),
    ('http://example.org/', 'application/json', 'index.json'),       # empty path falls back to index
    ('http://example.org/data.bin', 'application/octet-stream', 'data.bin'),  # already has an ext
    ('http://example.org/thing', 'application/x-made-up', 'thing'),  # unknown type, no ext added
])
def test_filename_from_url_extension_handling(url, content_type, expected):
    assert filename_from_url(url, content_type) == expected


@pytest.mark.parametrize('filename, max_len, expected', [
    ('short.txt', 255, 'short.txt'),           # nothing to trim
    ('abcdefghij.txt', 8, 'abcd.txt'),         # trim the name, keep the extension
    ('ab.verylongextension', 5, 'ab.ve'),      # trim amount >= name length, so just cut the whole thing
])
def test_trim_filename_keeps_extension_when_it_can(filename, max_len, expected):
    result = trim_filename(filename, max_len)
    assert result == expected
    assert len(result) <= max_len


# 9. httpie/uploads.py: is_stdin fallback when fileno() is missing (line 93)

def test_is_stdin_handles_objects_without_fileno():
    # BytesIO raises UnsupportedOperation on fileno(), function should swallow it and return False
    assert is_stdin(io.BytesIO(b'data')) is False


def test_is_stdin_matches_on_file_descriptor(monkeypatch):
    # pytest swaps sys.stdin for a capture object, so fake both sides with the same fd
    class FakeFile:
        def __init__(self, fd):
            self._fd = fd

        def fileno(self):
            return self._fd

    monkeypatch.setattr(sys, 'stdin', FakeFile(0))
    assert is_stdin(FakeFile(0)) is True
    assert is_stdin(FakeFile(7)) is False


# 10. httpie/utils.py: parse_content_type_header param parsing (partial branches 211, 214)

@pytest.mark.parametrize('header, expected_type, expected_params', [
    ('text/html', 'text/html', {}),
    ('text/html; charset=utf-8', 'text/html', {'charset': 'utf-8'}),
    ('text/html; charset="UTF-8"', 'text/html', {'charset': 'UTF-8'}),       # quotes stripped
    ('multipart/form-data; boundary=abc; ', 'multipart/form-data', {'boundary': 'abc'}),  # trailing empty param ignored
    ('application/json; Charset=utf-8', 'application/json', {'charset': 'utf-8'}),      # key lowercased
    ('text/plain; flag', 'text/plain', {'flag': True}),                      # param without = becomes True
])
def test_parse_content_type_header(header, expected_type, expected_params):
    assert parse_content_type_header(header) == (expected_type, expected_params)


# 11. httpie/output/writer.py: write_stream_with_colors_win (lines 89 to 97)
#     Windows only in real life but the function itself is plain Python so it can be
#     tested anywhere with a fake outfile.

class FakeOutfile:
    def __init__(self):
        self.encoding = 'utf-8'
        self.text_writes = []
        self.buffer = io.BytesIO()
        self.flush_count = 0

    def write(self, s):
        self.text_writes.append(s)

    def flush(self):
        self.flush_count += 1


def test_write_stream_with_colors_win_routes_colored_and_plain_chunks():
    out = FakeOutfile()
    chunks = [b'plain bytes\n', b'\x1b[31mred text\x1b[0m\n', b'more plain\n']
    write_stream_with_colors_win(stream=iter(chunks), outfile=out, flush=True)

    # chunks containing an ANSI escape go through .write() as str, the rest go to .buffer as bytes
    assert out.text_writes == ['\x1b[31mred text\x1b[0m\n']
    assert out.buffer.getvalue() == b'plain bytes\nmore plain\n'
    assert out.flush_count == 3


def test_write_stream_with_colors_win_no_flush():
    out = FakeOutfile()
    write_stream_with_colors_win(stream=iter([b'x']), outfile=out, flush=False)
    assert out.flush_count == 0
    assert out.buffer.getvalue() == b'x'


# 12. httpie/cli/argtypes.py: PromptMixin ctrl-C / EOF handling (lines 138 to 145) and reprs (25, 45)

class _Prompt(PromptMixin):
    def __init__(self, behaviour):
        self._behaviour = behaviour

    def _getpass(self, prompt):
        if isinstance(self._behaviour, BaseException):   # KeyboardInterrupt is not an Exception
            raise self._behaviour
        return self._behaviour


def test_prompt_password_returns_value_with_expected_prompt_text():
    p = _Prompt('secret')
    assert p._prompt_password('password for user') == 'secret'


@pytest.mark.parametrize('exc', [EOFError(), KeyboardInterrupt()])
def test_prompt_password_exits_cleanly_on_eof_or_ctrl_c(exc, capsys):
    p = _Prompt(exc)
    with pytest.raises(SystemExit) as info:
        p._prompt_password('password')
    assert info.value.code == 0
    assert capsys.readouterr().err == '\n'   # writes a newline so the shell prompt isn't glued to ours


def test_argtypes_reprs():
    arg = KeyValueArg(key='k', value='v', sep='=', orig='k=v')
    assert repr(arg) == repr(arg.__dict__)
    assert repr(Escaped('x')) == "Escaped('x')"
    assert KeyValueArg(key='k', value='v', sep='=', orig='k=v') == arg   # __eq__ compares dicts


# 13. httpie/models.py: HTTPMessage base class abstract methods (lines 31, 35, 40, 45)

def test_http_message_base_methods_are_abstract():
    msg = HTTPMessage(orig=object())
    with pytest.raises(NotImplementedError):
        msg.iter_body(1024)
    with pytest.raises(NotImplementedError):
        msg.iter_lines(1024)
    with pytest.raises(NotImplementedError):
        msg.headers
    with pytest.raises(NotImplementedError):
        msg.metadata