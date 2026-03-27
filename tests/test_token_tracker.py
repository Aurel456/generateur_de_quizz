"""Tests pour core/token_tracker.py."""

import pytest
from core.token_tracker import log_token_usage, get_token_summary, reset_token_log


@pytest.fixture(autouse=True)
def clean_log():
    reset_token_log()
    yield
    reset_token_log()


def test_log_and_summary():
    log_token_usage("test_func", "model-a", input_tokens=100, output_tokens=50)
    summary = get_token_summary()
    assert summary["total_calls"] == 1
    assert summary["total_input"] == 100
    assert summary["total_output"] == 50
    assert summary["total_tokens"] == 150


def test_multiple_logs():
    log_token_usage("f1", "m1", 100, 50)
    log_token_usage("f2", "m1", 200, 100)
    summary = get_token_summary()
    assert summary["total_calls"] == 2
    assert summary["total_input"] == 300
    assert summary["total_output"] == 150


def test_empty_summary():
    summary = get_token_summary()
    assert summary["total_calls"] == 0
    assert summary["total_tokens"] == 0


def test_reset():
    log_token_usage("f1", "m1", 100, 50)
    reset_token_log()
    assert get_token_summary()["total_calls"] == 0
