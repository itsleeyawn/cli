"""
Mutation Testing (Week 7) - SWEN-777 - Leon

Component: httpie/cli/argtypes.py
Tool: mutmut (config in setup.cfg under [mutmut])

parse_format_options had 41 surviving mutants in the initial run. It is only
exercised through its doctest, and doctests do not run under mutmut, so every
branch in it was effectively untested. The other functions here were reported
as "no tests". Each test notes what it kills.
"""
import argparse

import pytest

from httpie.cli.argtypes import (
    Escaped,
    KeyValueArg,
    KeyValueArgType,
    PromptMixin,
    parse_format_options,
    readable_file_arg,
    response_charset_type,
    response_mime_type,
)


# parse_format_options

DEFAULTS = {'json': {'indent': 4, 'sort_keys': True, 'format': True}, 'xml': {'indent': 2}}


def test_parse_format_options_does_not_mutate_defaults():
    before = {'json': {'indent': 4}}
    parse_format_options('json.indent:2', before)
    assert before == {'json': {'indent': 4}}          # kills removal of deepcopy


@pytest.mark.parametrize('s, expected', [
    ('json.indent:2', {'json': {'indent': 2, 'sort_keys': True, 'format': True}, 'xml': {'indent': 2}}),
    ('json.sort_keys:false', {'json': {'indent': 4, 'sort_keys': False, 'format': True}, 'xml': {'indent': 2}}),
    ('JSON.Sort_Keys:FALSE', {'json': {'indent': 4, 'sort_keys': False, 'format': True}, 'xml': {'indent': 2}}),  # lowercased
    ('json.indent:0,xml.indent:8', {'json': {'indent': 0, 'sort_keys': True, 'format': True}, 'xml': {'indent': 8}}),  # comma split
])
def test_parse_format_options_updates_the_right_key(s, expected):
    assert parse_format_options(s, DEFAULTS) == expected


def test_parse_format_options_true_and_false_map_to_bools():
    out = parse_format_options('json.sort_keys:true,json.format:false', DEFAULTS)
    assert out['json']['sort_keys'] is True
    assert out['json']['format'] is False            # kills value_map swaps / 'XXtrueXX'


def test_parse_format_options_numeric_strings_become_ints():
    out = parse_format_options('json.indent:12', DEFAULTS)
    assert out['json']['indent'] == 12 and isinstance(out['json']['indent'], int)   # kills isnumeric removal


@pytest.mark.parametrize('bad', ['json.indent', 'jsonindent:2', 'json.indent:2:3', 'a.b.c:1', ''])
def test_parse_format_options_rejects_malformed_option(bad):
    with pytest.raises(argparse.ArgumentTypeError) as exc:
        parse_format_options(bad, DEFAULTS)
    assert 'invalid option' in str(exc.value)
    assert repr(bad.lower()) in str(exc.value)       # message includes the offending option


def test_parse_format_options_rejects_unknown_key():
    with pytest.raises(argparse.ArgumentTypeError) as exc:
        parse_format_options('json.nope:1', DEFAULTS)
    assert "invalid key 'json.nope'" in str(exc.value)
    with pytest.raises(argparse.ArgumentTypeError):
        parse_format_options('yaml.indent:1', DEFAULTS)   # unknown section


def test_parse_format_options_rejects_wrong_type_with_details():
    with pytest.raises(argparse.ArgumentTypeError) as exc:
        parse_format_options('json.indent:true', DEFAULTS)
    msg = str(exc.value)
    assert "invalid value 'true' in 'json.indent:true'" in msg
    assert 'expected int' in msg and 'got bool' in msg    # kills message / type-check mutations


def test_parse_format_options_with_no_defaults_accepts_anything():
    out = parse_format_options('a.b:1,a.c:x,d.e:true', defaults=None)
    assert out == {'a': {'b': 1, 'c': 'x'}, 'd': {'e': True}}   # kills setdefault branch mutations


# KeyValueArg / KeyValueArgType.__init__

def test_key_value_arg_stores_all_fields():
    arg = KeyValueArg(key='k', value='v', sep='==', orig='k==v')
    assert (arg.key, arg.value, arg.sep, arg.orig) == ('k', 'v', '==', 'k==v')   # kills field swaps


def test_key_value_arg_type_collects_special_characters_from_every_separator():
    t = KeyValueArgType(':', '==', ':=', '=@')
    assert t.separators == (':', '==', ':=', '=@')
    assert t.special_characters == {':', '=', '@'}     # kills update() removal / set() changes
    assert t('a:b') == KeyValueArg(key='a', value='b', sep=':', orig='a:b')
    assert t('a==b') == KeyValueArg(key='a', value='b', sep='==', orig='a==b')  # longest match wins


# PromptMixin._prompt_password: exact prompt text and exit code

class _Prompt(PromptMixin):
    def __init__(self, result):
        self.result = result
        self.seen = None

    def _getpass(self, prompt):
        self.seen = prompt
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def test_prompt_password_formats_prompt_exactly():
    p = _Prompt('pw')
    assert p._prompt_password('password for alice') == 'pw'
    assert p.seen == 'http: password for alice: '     # kills f-string / prefix mutations


def test_prompt_password_exit_code_is_zero(capsys):
    p = _Prompt(EOFError())
    with pytest.raises(SystemExit) as e:
        p._prompt_password('x')
    assert e.value.code == 0                          # kills sys.exit(1)
    assert capsys.readouterr().err == '\n'


# Functions mutmut reported as "no tests"

def test_readable_file_arg(tmp_path):
    f = tmp_path / 'ok.txt'
    f.write_text('x')
    assert readable_file_arg(str(f)) == str(f)
    missing = tmp_path / 'missing.txt'
    with pytest.raises(argparse.ArgumentTypeError) as exc:
        readable_file_arg(str(missing))
    assert str(missing) in str(exc.value)
    assert 'No such file' in str(exc.value)


def test_response_charset_type():
    assert response_charset_type('utf-8') == 'utf-8'
    assert response_charset_type('latin-1') == 'latin-1'
    with pytest.raises(argparse.ArgumentTypeError) as exc:
        response_charset_type('not-a-codec')
    assert "'not-a-codec' is not a supported encoding" in str(exc.value)


@pytest.mark.parametrize('ok', ['text/plain', 'application/json', 'image/svg+xml'])
def test_response_mime_type_accepts_type_slash_subtype(ok):
    assert response_mime_type(ok) == ok


@pytest.mark.parametrize('bad', ['text', 'text/plain/extra', '', '/'])
def test_response_mime_type_rejects_wrong_slash_count(bad):
    if bad == '/':
        assert response_mime_type(bad) == '/'   # exactly one slash, so it passes
        return
    with pytest.raises(argparse.ArgumentTypeError) as exc:
        response_mime_type(bad)
    assert 'use type/subtype' in str(exc.value)


# KeyValueArgType.__call__ / tokenize: escape handling. These survived the second run
# because the only coverage was through integration tests that mutmut does not run.

def test_key_value_arg_type_tokenize_escapes():
    t = KeyValueArgType('=', ':')
    assert t.tokenize(r'foo\=bar\\baz') == ['foo', Escaped('='), 'bar\\\\baz']
    assert t.tokenize(r'a\:b') == ['a', Escaped(':'), 'b']
    assert t.tokenize(r'a\xb') == ['a\\xb']              # backslash kept when next char is not special
    assert t.tokenize('plain') == ['plain']
    assert t.tokenize('trail\\') == ['trail\\']           # dangling backslash at end


def test_key_value_arg_type_escaped_separator_is_not_a_separator():
    t = KeyValueArgType(':', '==')
    assert t(r'a\:b:c') == KeyValueArg(key='a:b', value='c', sep=':', orig=r'a\:b:c')
    assert t(r'k:v\:w') == KeyValueArg(key='k', value='v:w', sep=':', orig=r'k:v\:w')
    assert t(r'x\==y==z') == KeyValueArg(key='x==y', value='z', sep='==', orig=r'x\==y==z')


def test_key_value_arg_type_longest_separator_at_same_position_wins():
    # ':' and ':=' both match at the same position; the longer one must win regardless of
    # the order they were given in. Kills the sorted(key=len) mutations.
    assert KeyValueArgType(':=', ':')('a:=b').sep == ':='
    assert KeyValueArgType(':', ':=')('a:=b').sep == ':='
    # first position wins over longer later one
    assert KeyValueArgType('=', '==')('a=b==c') == KeyValueArg(key='a', value='b==c', sep='=', orig='a=b==c')


def test_key_value_arg_type_rejects_value_without_separator():
    with pytest.raises(argparse.ArgumentTypeError) as exc:
        KeyValueArgType(':')('nosep')
    assert "'nosep' is not a valid value" in str(exc.value)
