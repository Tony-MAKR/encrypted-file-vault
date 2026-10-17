"""Configuration guards must reject weak or placeholder secrets."""

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.security import MIN_SECRET_KEY_LENGTH, validate_secret_key


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        "short",
        "replace-with-a-long-random-value",
        "django-insecure-example-key-with-enough-length-123",
        "changeme-" + "x" * 50,
    ],
)
def test_weak_secret_keys_are_rejected(value):
    with pytest.raises(ImproperlyConfigured):
        validate_secret_key(value)


def test_valid_secret_key_is_returned_stripped():
    value = "x" * MIN_SECRET_KEY_LENGTH
    assert validate_secret_key(f"  {value}  ") == value
