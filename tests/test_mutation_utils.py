"""
Mutation Testing (Week 7) - SWEN-777 - Tenzin

Component: httpie/utils.py
Tool: mutmut (config in setup.cfg under [mutmut])

Every test here was written against a specific surviving mutant from the initial
mutmut run, or against a function mutmut reported as "no tests". The comment on
each test says which mutant(s) it kills. See courseProjectDocs/mutation-testing/report.md.
"""
import json
import time

import pytest

from httpie.utils import (
    JsonDictPreservingDuplicateKeys,
    _max_age_to_expires,
    get_content_type,
    get_expired_cookies,
    humanize_bytes,
    is_version_greater,
    load_json_preserve_order_and_dupe_keys,
    parse_content_type_header,
    repr_dict,
    split_cookies,
    split_iterable,
    unwrap_context,
    url_as_host,
)


# humanize_bytes
# survivors: default precision changed 2 -> 3; factor doubled (1<<30 -> 2<<30, 1<<20 -> 2<<20);
# suffix case changed ('GB' -> 'gb', 'MB' -> 'mb'). The Week 5 test always passed precision
# explicitly and never hit MB/GB, so none of those mutations could fail.

def test_humanize_bytes_default_precision_is_two():
    assert humanize_bytes(1536) == '1.50 kB'          # kills precision=3


@pytest.mark.parametrize('n, expected', [
    (1 << 20, '1.00 MB'),                              # kills 2<<20 and 'mb'
    ((1 << 20) * 1.5, '1.50 MB'),
    (1 << 30, '1.00 GB'),                              # kills 2<<30 and 'gb'
    ((1 << 30) * 2, '2.00 GB'),
    (1 << 40, '1.00 TB'),
    ((1 << 10) * 1023, '1023.00 kB'),                  # just under MB must still be kB
])
def test_humanize_bytes_each_unit_boundary_and_suffix(n, expected):
    assert humanize_bytes(n) == expected


# is_version_greater
# survivor: split('.')[:3] -> [:4]. Need a version where the 4th part flips the answer.

def test_is_version_greater_ignores_fourth_component():
    assert is_version_greater('3.2.0.9', '3.2.0.1') is False     # kills [:4]
    assert is_version_greater('3.2.0.1', '3.2.0') is False


# load_json_preserve_order_and_dupe_keys
# survivors: object_pairs_hook removed / None. Duplicate keys must survive a round trip.

def test_load_json_keeps_duplicate_keys_and_order():
    obj = load_json_preserve_order_and_dupe_keys('{"b": 1, "a": 2, "b": 3}')
    assert isinstance(obj, JsonDictPreservingDuplicateKeys)
    assert list(obj.items()) == [('b', 1), ('a', 2), ('b', 3)]
    assert json.dumps(obj) == '{"b": 1, "a": 2, "b": 3}'


# parse_content_type_header
# survivors: items_to_strip changed (strip(None) / 'XX"\' XX'), find -> rfind.

def test_parse_content_type_header_strips_quotes_and_spaces_from_key_and_value():
    ct, params = parse_content_type_header("text/plain; 'charset' = \"utf-8\" ")
    assert ct == 'text/plain'
    assert params == {'charset': 'utf-8'}                        # kills strip(None) and 'XX...' variants


@pytest.mark.parametrize('header, expected_params', [
    ('text/html; charset="UTF-8"', {'charset': 'UTF-8'}),            # quotes stripped
    ('text/plain; flag', {'flag': True}),                            # param with no '=' becomes True
    ('multipart/form-data; boundary=abc; ', {'boundary': 'abc'}),    # trailing empty param ignored
    ('application/json; Charset=utf-8', {'charset': 'utf-8'}),       # key lowercased
])
def test_parse_content_type_header_param_edge_cases(header, expected_params):
    assert parse_content_type_header(header)[1] == expected_params


def test_parse_content_type_header_splits_on_first_equals():
    # value containing '=' must stay intact, so it has to be find() not rfind()
    ct, params = parse_content_type_header('application/x-foo; token=abc=def')
    assert params == {'token': 'abc=def'}                        # kills rfind


# url_as_host
# survivors: split on None / 'XX@XX', index -2. No test existed for this function at all.

@pytest.mark.parametrize('url, expected', [
    ('https://example.org/path', 'example.org'),
    ('https://user:pass@example.org:8080/x', 'example.org:8080'),   # kills [-2] and the split variants
    ('http://a@b@example.org', 'example.org'),
])
def test_url_as_host(url, expected):
    assert url_as_host(url) == expected


# The rest of utils.py had no tests at all ("no tests" in mutmut). These give
# mutmut something to run so those mutants can actually be killed.

def test_split_cookies():
    assert split_cookies('') == []
    assert split_cookies(None) == []
    assert split_cookies('a=1; Path=/') == ['a=1; Path=/']
    # the ', ' inside an expires date must not split the cookie
    raw = 'a=1; Expires=Wed, 21 Oct 2026 07:28:00 GMT, b=2; Path=/'
    assert split_cookies(raw) == ['a=1; Expires=Wed, 21 Oct 2026 07:28:00 GMT', 'b=2; Path=/']


def test_max_age_to_expires_only_fills_missing_expires():
    now = 1000.0
    cookies = [
        {'name': 'a', 'max-age': '60'},
        {'name': 'b', 'max-age': '60', 'expires': 5.0},
        {'name': 'c', 'max-age': 'nope'},
        {'name': 'd'},
    ]
    _max_age_to_expires(cookies, now=now)
    assert cookies[0]['expires'] == 1060.0
    assert cookies[1]['expires'] == 5.0            # existing expires untouched
    assert 'expires' not in cookies[2]             # non numeric max-age ignored
    assert 'expires' not in cookies[3]


def test_get_expired_cookies():
    now = 1000.0
    raw = (
        'dead=1; Max-Age=0; Path=/x, '
        'alive=2; Max-Age=600, '
        'nodate=3; Path=/'
    )
    expired = get_expired_cookies(raw, now=now)
    assert expired == [{'name': 'dead', 'path': '/x'}]


def test_get_expired_cookies_defaults_now_to_current_time():
    past = time.time() - 10
    raw = f'old=1; expires={time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(past))}'
    assert get_expired_cookies(raw) == [{'name': 'old', 'path': '/'}]


def test_split_iterable():
    evens, odds = split_iterable(range(6), key=lambda n: n % 2 == 0)
    assert evens == [0, 2, 4]
    assert odds == [1, 3, 5]
    assert split_iterable([], key=bool) == ([], [])


def test_unwrap_context_walks_to_the_root_cause():
    try:
        try:
            raise ValueError('root')
        except ValueError:
            raise KeyError('middle')
    except KeyError as exc:
        wrapped = exc
    assert str(unwrap_context(wrapped)) == "'middle'" or isinstance(unwrap_context(wrapped), ValueError)
    assert isinstance(unwrap_context(wrapped), ValueError)
    plain = RuntimeError('no context')
    assert unwrap_context(plain) is plain


def test_get_content_type_and_repr_dict():
    assert get_content_type('report.json') == 'application/json'
    assert get_content_type('photo.jpeg') == 'image/jpeg'
    assert get_content_type('file.unknownext') is None
    assert repr_dict({'b': 1, 'a': 2}) == "{'a': 2, 'b': 1}"   # pformat sorts keys


def test_max_age_to_expires_keeps_going_after_a_cookie_that_already_has_expires():
    # a cookie with expires must be skipped, not end the loop (continue vs break)
    cookies = [{'name': 'a', 'expires': 1.0}, {'name': 'b', 'max-age': '5'}]
    _max_age_to_expires(cookies, now=10.0)
    assert cookies[1]['expires'] == 15.0


def test_get_content_type_uses_non_strict_mime_table():
    # '.pict' only exists in mimetypes' non strict table, so strict=False matters
    assert get_content_type('drawing.pict') == 'image/pict'
