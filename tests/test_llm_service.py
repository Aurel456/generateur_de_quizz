"""Tests pour core/llm_service.py — Parsing JSON et utilitaires."""

import pytest
from core.llm_service import _parse_json_response, count_tokens, estimate_available_tokens


class TestParseJsonResponse:
    def test_direct_json(self):
        result = _parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_in_markdown_block(self):
        raw = '```json\n{"key": "value"}\n```'
        result = _parse_json_response(raw)
        assert result == {"key": "value"}

    def test_json_in_generic_code_block(self):
        raw = '```\n{"key": "value"}\n```'
        result = _parse_json_response(raw)
        assert result == {"key": "value"}

    def test_json_with_surrounding_text(self):
        raw = 'Voici le résultat : {"key": "value"} fin.'
        result = _parse_json_response(raw)
        assert result == {"key": "value"}

    def test_json_array(self):
        result = _parse_json_response('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_invalid_json_returns_none(self):
        assert _parse_json_response("pas du json du tout") is None

    def test_empty_string(self):
        assert _parse_json_response("") is None

    def test_nested_json(self):
        raw = '{"questions": [{"q": "test", "choices": {"A": "a"}}]}'
        result = _parse_json_response(raw)
        assert len(result["questions"]) == 1

    def test_json_with_thinking_block(self):
        raw = '<think>Je réfléchis...</think>\n```json\n{"answer": 42}\n```'
        result = _parse_json_response(raw)
        assert result == {"answer": 42}


class TestCountTokens:
    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_simple_text(self):
        tokens = count_tokens("Hello world")
        assert tokens > 0
        assert tokens < 10

    def test_longer_text(self):
        short = count_tokens("test")
        long = count_tokens("test " * 100)
        assert long > short


class TestEstimateAvailableTokens:
    def test_short_prompts(self):
        available = estimate_available_tokens("system", "user")
        assert available > 0

    def test_very_long_prompt(self):
        huge = "x " * 100000
        available = estimate_available_tokens(huge, huge)
        assert available == -1
