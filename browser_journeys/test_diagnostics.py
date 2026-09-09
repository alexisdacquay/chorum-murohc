"""Proofs that a journey report cannot carry a credential out of the browser."""

from browser_journeys.diagnostics import (
    REDACTED,
    leaked_secrets,
    maskable,
    redact,
    secret_values,
)


def test_a_secret_is_replaced_wherever_it_appears():
    text = redact('typed hunter2000 then hunter2000 again', ['hunter2000'])

    assert 'hunter2000' not in text
    assert text.count(REDACTED) == 2


def test_a_secret_containing_another_is_replaced_whole():
    """Shortest-first would cut the longer value in half and leave a remainder."""
    text = redact('the value 1234567 and the value 1234', ['1234', '1234567'])

    assert leaked_secrets(text, ['1234', '1234567']) == []


def test_maskable_puts_the_longest_first():
    assert maskable(['abcd', 'abcdefgh']) == ['abcdefgh', 'abcd']


def test_a_value_too_short_to_mask_is_left_alone():
    assert redact('score 42 out of 99', ['42']) == 'score 42 out of 99'


def test_leaked_secrets_reports_a_short_value_it_did_not_mask():
    """A reader must learn the report is unsafe even when masking declined."""
    assert leaked_secrets('score 42', ['42']) == ['42']


def test_a_redacted_report_leaks_nothing():
    secrets = ['journey-abcdefgh', '481625']
    report = 'filled Password with journey-abcdefgh and PIN 481625'

    assert leaked_secrets(redact(report, secrets), secrets) == []


def test_secret_values_walks_a_nested_dataset():
    dataset = {
        'token': 'abc',
        'journeys': {
            'one': {
                'parent': {'username': 'p', 'password': 'pw-one', 'pin': '481625'},
                'children': [{'username': 'c', 'password': 'pw-two'}],
            }
        },
    }

    assert secret_values(dataset) == ['pw-one', '481625', 'pw-two']


def test_secret_values_ignores_everything_that_is_not_a_credential():
    assert secret_values({'username': 'child', 'household': 'home', 'points': 40}) == []
