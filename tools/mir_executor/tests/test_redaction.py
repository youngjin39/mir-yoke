"""Credential shapes the common redactor must not leave in executor artifacts."""

from __future__ import annotations

import json

import pytest

from tools.mir_executor.redaction import redact_secret_like_content, redact_structured_value


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ('{"api_key": "plain-private-value"}', "plain-private-value"),
        ("'password': 'hunter2-private'", "hunter2-private"),
        ('"password": "two word secret"', "word secret"),
        ("SECRET_KEY=django-private-value", "django-private-value"),
        ("AWS_SECRET_ACCESS_KEY=aws-private-value", "aws-private-value"),
        ("Authorization: Basic dXNlcjpwcml2YXRl", "dXNlcjpwcml2YXRl"),
    ],
)
def test_should_redact_value_when_secret_assignment_is_quoted_suffixed_or_basic(text, secret):
    assert secret not in redact_secret_like_content(text)


def test_should_redact_string_value_when_dict_key_names_a_secret():
    payload = {
        "api_key": "plain-private-value",
        "nested": [{"client_secret": "nested-private-value", "token_count": 3}],
        "summary": "no credential here",
    }
    redacted = redact_structured_value(payload)
    serialized = json.dumps(redacted)
    assert "plain-private-value" not in serialized
    assert "nested-private-value" not in serialized
    assert redacted["nested"][0]["token_count"] == 3
    assert redacted["summary"] == "no credential here"


@pytest.mark.parametrize(
    "text",
    ["max_tokens: 4096", "basic setup complete", "the secret ingredient is time"],
)
def test_should_keep_text_when_it_only_mentions_a_secret_word(text):
    assert redact_secret_like_content(text) == text


def test_should_keep_existing_assignment_format_when_value_is_unquoted():
    assert redact_secret_like_content("provider unavailable api_key=test-secret") == (
        "provider unavailable api_key=[REDACTED]"
    )
