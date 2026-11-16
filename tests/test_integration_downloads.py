"""
Integration Testing - SWEN-777 - Tenzin

Feature under test: `http --download` (with `--output` and `--continue`).

These tests run the real CLI against the local pytest-httpbin server, so a
single command exercises several modules working together:

    httpie/core.py            program(): wires the download flow together
    httpie/cli/argparser.py   parses --download / --output / --continue
    httpie/client.py          builds and sends the request (incl. Range header)
    httpie/downloads.py       Downloader: picks the filename, resumes, truncates
    httpie/output/streams.py  RawStream: writes the body chunks to the file
    filesystem                the file that ends up on disk

The expected bytes are fetched separately with urllib (not through HTTPie),
so the oracle does not depend on the code being tested.
"""
import os
from urllib.request import urlopen

import pytest

from httpie.status import ExitStatus
from .utils import http, MockEnvironment


def download(*args):
    # stdout_isatty=True: with a redirected stdout HTTPie streams the body
    # to stdout instead of creating a file, which is not what we test here.
    env = MockEnvironment(stdin_isatty=True, stdout_isatty=True)
    return http('--download', *args, env=env, tolerate_error_exit_status=True)


def fetch(url):
    with urlopen(url) as response:
        return response.read()


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    # Downloads without --output land in the current directory.
    monkeypatch.chdir(tmp_path)
    return tmp_path


# Normal scenarios

def test_download_saves_exact_body_with_name_from_url(httpbin, workdir):
    url = httpbin + '/bytes/1024?seed=777'
    expected = fetch(url)

    r = download(url)

    assert r.exit_status == ExitStatus.SUCCESS
    # downloads.filename_from_url: last path segment + extension guessed
    # from Content-Type (application/octet-stream -> .bin)
    assert os.listdir(workdir) == ['1024.bin']
    assert (workdir / '1024.bin').read_bytes() == expected


def test_download_uses_filename_from_content_disposition(httpbin, workdir):
    url = httpbin + '/response-headers?Content-Disposition=attachment;%20filename=%22report.txt%22'

    r = download(url)

    assert r.exit_status == ExitStatus.SUCCESS
    assert os.listdir(workdir) == ['report.txt']


def test_download_continue_appends_only_the_missing_bytes(httpbin, workdir):
    # /range/N supports Range requests and answers 206 Partial Content.
    url = httpbin + '/range/2000'
    expected = fetch(url)
    partial = workdir / 'partial.bin'
    partial.write_bytes(expected[:700])

    r = download('--continue', '--output', str(partial), url)

    assert r.exit_status == ExitStatus.SUCCESS
    assert partial.read_bytes() == expected


# Edge and failure scenarios

def test_download_strips_path_traversal_from_server_filename(httpbin, workdir):
    # A malicious server suggests a filename outside the current directory.
    url = httpbin + '/response-headers?Content-Disposition=attachment;%20filename=%22../../evil.txt%22'

    r = download(url)

    assert r.exit_status == ExitStatus.SUCCESS
    assert os.listdir(workdir) == ['evil.txt']
    assert not (workdir.parent / 'evil.txt').exists()
    assert not (workdir.parent.parent / 'evil.txt').exists()


def test_download_never_overwrites_an_existing_file(httpbin, workdir):
    url = httpbin + '/bytes/64?seed=1'
    (workdir / '64.bin').write_bytes(b'keep me')

    r = download(url)

    assert r.exit_status == ExitStatus.SUCCESS
    assert (workdir / '64.bin').read_bytes() == b'keep me'
    # downloads.get_unique_filename appends -1 after the extension
    assert (workdir / '64.bin-1').read_bytes() == fetch(url)


def test_download_continue_restarts_when_server_ignores_range(httpbin, workdir):
    # /bytes/N ignores the Range header and answers 200 with the full body.
    # The stale partial data must be replaced, not appended to.
    url = httpbin + '/bytes/1000?seed=2'
    expected = fetch(url)
    partial = workdir / 'partial.bin'
    partial.write_bytes(b'x' * 300)

    r = download('--continue', '--output', str(partial), url)

    assert r.exit_status == ExitStatus.SUCCESS
    assert partial.read_bytes() == expected


def test_download_http_error_reports_status_and_creates_no_file(httpbin, workdir):
    r = download(httpbin + '/status/404')

    assert r.exit_status == ExitStatus.ERROR_HTTP_4XX
    assert '404' in r.stderr
    assert os.listdir(workdir) == []


@pytest.mark.xfail(
    strict=True,
    reason='Defect found by integration testing: resuming a download that is '
           'already complete exits with status 4 (HTTP 416) instead of '
           'treating the file as done. See courseProjectDocs/integration-testing/report.md.',
)
def test_download_continue_on_already_complete_file_succeeds(httpbin, workdir):
    url = httpbin + '/range/2000'
    expected = fetch(url)
    done = workdir / 'done.bin'
    done.write_bytes(expected)

    r = download('--continue', '--output', str(done), url)

    assert done.read_bytes() == expected  # file is left intact either way
    assert r.exit_status == ExitStatus.SUCCESS
