"""
Integration Testing - SWEN-777 - Leon

Feature under test: `http --session` (named session file reused across runs).

Modules integrated:

    httpie/cli/argparser.py   parses --session and the request items
    httpie/client.py          merges the session into the request
    httpie/sessions.py        loads, updates and saves the session file
    httpie/config.py          reads and writes the JSON file on disk
"""
import json

from httpie.status import ExitStatus
from .utils import http, MockEnvironment


def test_session_persists_header_auth_and_cookie_to_next_request(httpbin, tmp_path):
    session = tmp_path / 'session.json'

    http(f'--session={session}', '--auth=user:pass',
         httpbin + '/cookies/set?token=abc', 'X-Team:swen777')
    r = http(f'--session={session}', httpbin + '/headers')

    sent = r.json['headers']
    assert sent['X-Team'] == 'swen777'
    assert sent['Authorization'].startswith('Basic ')
    assert 'token=abc' in sent['Cookie']
    assert json.loads(session.read_text())['cookies'][0]['name'] == 'token'


def test_session_corrupt_file_reports_error(httpbin, tmp_path):
    session = tmp_path / 'session.json'
    session.write_text('{not json')

    r = http(f'--session={session}', httpbin + '/get',
             env=MockEnvironment(), tolerate_error_exit_status=True)

    assert r.exit_status == ExitStatus.ERROR
    assert 'invalid session file' in r.stderr
    assert session.read_text() == '{not json'  # not overwritten
