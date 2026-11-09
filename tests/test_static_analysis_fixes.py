"""
Static Analysis & Code Smell Detection - SWEN-777

Regression tests for the findings we fixed this week. Each test fails on the
code before the fix and passes after it. See
courseProjectDocs/static-analysis/report.md for the tool output.
"""
from unittest import mock

import pytest
import requests

from httpie.internal import update_warnings
from .utils import MockEnvironment


@pytest.fixture
def env():
    env = MockEnvironment()
    yield env
    env.cleanup()


# Tenzin: bandit B501 (verify=False) and B113 (no timeout) in update_warnings

def _ok_response():
    resp = mock.Mock(spec=requests.Response)
    resp.json.return_value = {}
    resp.raise_for_status.return_value = None
    return resp


def test_fetch_updates_keeps_tls_certificate_verification_on(env):
    with mock.patch.object(update_warnings.requests, 'get', return_value=_ok_response()) as get:
        update_warnings._fetch_updates(env)
    _, kwargs = get.call_args
    # requests verifies certificates unless verify is falsy
    assert kwargs.get('verify', True) is not False


def test_fetch_updates_sets_a_timeout(env):
    with mock.patch.object(update_warnings.requests, 'get', return_value=_ok_response()) as get:
        update_warnings._fetch_updates(env)
    _, kwargs = get.call_args
    assert kwargs.get('timeout') == update_warnings.FETCH_TIMEOUT
    assert 0 < update_warnings.FETCH_TIMEOUT <= 30


def test_fetch_updates_propagates_timeout_instead_of_hanging(env):
    with mock.patch.object(update_warnings.requests, 'get', side_effect=requests.Timeout):
        with pytest.raises(requests.Timeout):
            update_warnings._fetch_updates(env)
    assert not env.config.version_info_file.exists()


def test_read_data_error_free_reads_utf8(tmp_path):
    f = tmp_path / 'version_info.json'
    f.write_text('{"note": "café"}', encoding='utf-8')
    assert update_warnings._read_data_error_free(f) == {'note': 'café'}


# Leon: add regression tests for your fix below.
