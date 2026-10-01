"""
Unit Testing I (Extend Coverage) - SWEN-777

Targets picked from the baseline coverage report (courseProjectDocs/Setup/testCoverage):
uncovered helper/edge-case logic that the existing integration-heavy suite never hits.
No httpbin server needed; these are pure unit tests.
"""
import argparse
import json

import pytest
import requests

from httpie.cli.argtypes import KeyValueArg, SessionNameValidator
from httpie.cli.exceptions import ParseError
from httpie.cli.nested_json.tokens import Path as NestedPath, PathAction
from httpie.cli.requestitems import load_json, load_text_file
from httpie.config import ConfigFileError, get_default_config_dir, read_raw_config
from httpie.models import infer_requests_message_kind, RequestsMessageKind
from httpie.utils import humanize_bytes, is_version_greater


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