"""Tests pour core/llm_cache.py."""

import time
import pytest
from core.llm_cache import LLMCache


@pytest.fixture
def cache():
    return LLMCache(max_size=5, ttl=10, persist_path=None)


def test_put_and_get(cache):
    cache.put("sys", "user", "model", 0.7, "réponse")
    assert cache.get("sys", "user", "model", 0.7) == "réponse"


def test_cache_miss(cache):
    assert cache.get("sys", "user", "model", 0.7) is None


def test_different_params_different_keys(cache):
    cache.put("sys", "user", "model", 0.7, "r1")
    cache.put("sys", "user", "model", 0.5, "r2")
    assert cache.get("sys", "user", "model", 0.7) == "r1"
    assert cache.get("sys", "user", "model", 0.5) == "r2"


def test_lru_eviction(cache):
    """Le cache à max_size=5 doit évincer les plus anciennes entrées."""
    for i in range(6):
        cache.put("sys", f"user_{i}", "model", 0.7, f"r{i}")
    # La première entrée (user_0) doit être évincée
    assert cache.get("sys", "user_0", "model", 0.7) is None
    assert cache.get("sys", "user_5", "model", 0.7) == "r5"


def test_ttl_expiration(cache):
    """Entrées expirées doivent retourner None."""
    short_cache = LLMCache(max_size=5, ttl=1, persist_path=None)
    short_cache.put("sys", "user", "model", 0.7, "réponse")
    assert short_cache.get("sys", "user", "model", 0.7) == "réponse"
    time.sleep(1.1)
    assert short_cache.get("sys", "user", "model", 0.7) is None


def test_clear(cache):
    cache.put("sys", "user", "model", 0.7, "réponse")
    cache.clear()
    assert cache.get("sys", "user", "model", 0.7) is None


def test_stats(cache):
    cache.put("sys", "user", "model", 0.7, "réponse")
    stats = cache.stats()
    assert stats["size"] == 1
    assert stats["max_size"] == 5


def test_save_and_load(tmp_path):
    """Persistence JSON : sauvegarder puis recharger."""
    cache_file = str(tmp_path / "cache.json")
    c1 = LLMCache(max_size=5, ttl=3600, persist_path=cache_file)
    c1.put("sys", "user", "model", 0.7, "réponse")
    c1.save_to_file()

    c2 = LLMCache(max_size=5, ttl=3600, persist_path=cache_file)
    assert c2.get("sys", "user", "model", 0.7) == "réponse"


def test_update_existing_key(cache):
    cache.put("sys", "user", "model", 0.7, "v1")
    cache.put("sys", "user", "model", 0.7, "v2")
    assert cache.get("sys", "user", "model", 0.7) == "v2"
    assert cache.stats()["size"] == 1
