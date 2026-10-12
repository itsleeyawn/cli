"""
Unit Testing II (Mocking & Stubbing) - SWEN-777 - Tenzin

Component: httpie/internal/update_warnings.py

This module hits a real external API (https://packages.httpie.io/latest.json) and
spawns a background daemon process to do it. The existing tests in
test_update_warnings.py go through the full CLI and actually spawn the daemon,
so the HTTP call, the interval logic and the "already warned recently" logic
are hard to pin down. Here the network call and the daemon spawn are mocked
so every branch can be tested directly and deterministically.
"""
import json
from datetime import datetime, timedelta
from unittest import mock

import pytest
import requests

import httpie
from httpie.context import LogLevel
from httpie.internal import update_warnings
from httpie.internal.update_warnings import (
    ALREADY_UP_TO_DATE_MESSAGE,
    FETCH_INTERVAL,
    PACKAGE_INDEX_LINK,
    WARN_INTERVAL,
    _fetch_updates,
    _get_update_status,
    check_updates,
    fetch_updates,
    get_update_status,
    maybe_fetch_updates,
)
from .utils import MockEnvironment


CHANNEL = update_warnings.BUILD_CHANNEL  # 'unknown' in a dev checkout
CURRENT = httpie.__version__


@pytest.fixture
def env():
    env = MockEnvironment()
    env.config['disable_update_warnings'] = False
    yield env
    env.cleanup()


def write_version_info(env, released=None, last_warned=None, last_fetched=None):
    data = {
        'last_released_versions': released if released is not None else {CHANNEL: CURRENT},
        'last_warned_date': last_warned,
        'last_fetched_date': last_fetched or datetime.now().isoformat(),
    }
    env.config.version_info_file.write_text(json.dumps(data))
    return data


def fake_response(payload, status_ok=True):
    resp = mock.Mock(spec=requests.Response)
    resp.json.return_value = payload
    if status_ok:
        resp.raise_for_status.return_value = None
    else:
        resp.raise_for_status.side_effect = requests.HTTPError('503 Service Unavailable')
    return resp


# 1. _fetch_updates: the actual API call, with requests.get stubbed out

def test_fetch_updates_calls_package_index_and_writes_file(env):
    payload = {CHANNEL: '99.0.0', 'pip': '99.0.0'}
    with mock.patch.object(update_warnings.requests, 'get', return_value=fake_response(payload)) as get:
        _fetch_updates(env)

    get.assert_called_once_with(PACKAGE_INDEX_LINK, verify=False)
    saved = json.loads(env.config.version_info_file.read_text())
    assert saved['last_released_versions'] == payload
    assert saved['last_warned_date'] is None
    # should be a parseable timestamp from "now"
    assert datetime.now() - datetime.fromisoformat(saved['last_fetched_date']) < timedelta(seconds=5)


def test_fetch_updates_preserves_existing_last_warned_date(env):
    write_version_info(env, last_warned='2026-01-01T00:00:00')
    with mock.patch.object(update_warnings.requests, 'get', return_value=fake_response({CHANNEL: '1.0.0'})):
        _fetch_updates(env)
    saved = json.loads(env.config.version_info_file.read_text())
    assert saved['last_warned_date'] == '2026-01-01T00:00:00'


def test_fetch_updates_raises_on_http_error_and_does_not_write(env):
    with mock.patch.object(update_warnings.requests, 'get', return_value=fake_response({}, status_ok=False)):
        with pytest.raises(requests.HTTPError):
            _fetch_updates(env)
    assert not env.config.version_info_file.exists()


# 2. fetch_updates: lazy path spawns a daemon, non lazy path does the fetch inline

def test_fetch_updates_lazy_spawns_daemon_instead_of_fetching(env):
    with mock.patch.object(update_warnings, 'spawn_daemon') as spawn, \
            mock.patch.object(update_warnings, '_fetch_updates') as inline:
        fetch_updates(env, lazy=True)
    spawn.assert_called_once_with('fetch_updates')
    inline.assert_not_called()


def test_fetch_updates_not_lazy_fetches_inline(env):
    with mock.patch.object(update_warnings, 'spawn_daemon') as spawn, \
            mock.patch.object(update_warnings, '_fetch_updates') as inline:
        fetch_updates(env, lazy=False)
    spawn.assert_not_called()
    inline.assert_called_once_with(env)


# 3. maybe_fetch_updates: the FETCH_INTERVAL gate

@pytest.mark.parametrize('age, should_fetch', [
    (timedelta(days=1), False),                      # fetched yesterday, too soon
    (FETCH_INTERVAL - timedelta(hours=1), False),    # just under the interval
    (FETCH_INTERVAL + timedelta(hours=1), True),     # past the interval
])
def test_maybe_fetch_updates_respects_fetch_interval(env, age, should_fetch):
    write_version_info(env, last_fetched=(datetime.now() - age).isoformat())
    with mock.patch.object(update_warnings, 'fetch_updates') as fetch:
        maybe_fetch_updates(env)
    assert fetch.called is should_fetch


def test_maybe_fetch_updates_fetches_when_no_file_yet(env):
    with mock.patch.object(update_warnings, 'fetch_updates') as fetch:
        maybe_fetch_updates(env)
    fetch.assert_called_once_with(env)


def test_maybe_fetch_updates_skips_when_disabled(env):
    env.config['disable_update_warnings'] = True
    with mock.patch.object(update_warnings, 'fetch_updates') as fetch:
        maybe_fetch_updates(env)
    fetch.assert_not_called()


# 4. _get_update_status / get_update_status: version comparison against the cached file

def test_update_status_none_when_no_file(env):
    assert _get_update_status(env) is None
    assert get_update_status(env) == ALREADY_UP_TO_DATE_MESSAGE


def test_update_status_none_when_channel_missing(env):
    write_version_info(env, released={'some-other-channel': '99.0.0'})
    assert _get_update_status(env) is None


def test_update_status_none_when_up_to_date(env):
    write_version_info(env, released={CHANNEL: CURRENT})
    assert _get_update_status(env) is None
    assert get_update_status(env) == ALREADY_UP_TO_DATE_MESSAGE


def test_update_status_message_when_newer_version_available(env):
    write_version_info(env, released={CHANNEL: '99.0.0'})
    text = _get_update_status(env)
    assert '99.0.0' in text
    assert f'https://httpie.io/docs/cli/{CHANNEL}' in text
    assert get_update_status(env) == text


def test_update_status_swallows_broken_file_unless_developer_mode(env):
    env.config.version_info_file.write_text('{not json')
    assert _get_update_status(env) is None          # suppressed
    env.config['developer_mode'] = True
    with pytest.raises(json.JSONDecodeError):       # surfaced for debugging
        _get_update_status(env)


# 5. check_updates: warn once, then stay quiet for WARN_INTERVAL

def test_check_updates_logs_warning_and_records_date(env):
    write_version_info(env, released={CHANNEL: '99.0.0'})
    with mock.patch.object(env, 'log_error') as log, \
            mock.patch.object(update_warnings, 'maybe_fetch_updates'):
        check_updates(env)
    log.assert_called_once()
    msg, kwargs = log.call_args.args[0], log.call_args.kwargs
    assert '99.0.0' in msg
    assert kwargs['level'] is LogLevel.INFO
    saved = json.loads(env.config.version_info_file.read_text())
    assert saved['last_warned_date'] is not None


@pytest.mark.parametrize('warned_ago, should_warn', [
    (timedelta(days=1), False),
    (WARN_INTERVAL + timedelta(hours=1), True),
])
def test_check_updates_respects_warn_interval(env, warned_ago, should_warn):
    write_version_info(
        env,
        released={CHANNEL: '99.0.0'},
        last_warned=(datetime.now() - warned_ago).isoformat(),
    )
    with mock.patch.object(env, 'log_error') as log, \
            mock.patch.object(update_warnings, 'maybe_fetch_updates'):
        check_updates(env)
    assert log.called is should_warn


def test_check_updates_does_nothing_when_up_to_date(env):
    write_version_info(env, released={CHANNEL: CURRENT})
    with mock.patch.object(env, 'log_error') as log, \
            mock.patch.object(update_warnings, 'maybe_fetch_updates') as fetch:
        check_updates(env)
    log.assert_not_called()
    fetch.assert_called_once_with(env)   # the decorator still triggers the background fetch check
