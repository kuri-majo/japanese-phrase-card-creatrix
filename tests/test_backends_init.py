import importlib

import pytest

import backends


def _restore_default():
    """backends/__init__.py branches at import time, so switching
    CARD_BACKEND requires a real reload -- and that's a process-global
    side effect, not something monkeypatch undoes on its own. Every test
    that changes it must put the module back afterward."""
    import os

    os.environ.pop("CARD_BACKEND", None)
    importlib.reload(backends)


def test_defaults_to_claude_backend(monkeypatch):
    monkeypatch.delenv("CARD_BACKEND", raising=False)
    importlib.reload(backends)
    from backends import claude_local

    assert backends.generate is claude_local.generate


def test_card_backend_gemini_selects_gemini(monkeypatch):
    monkeypatch.setenv("CARD_BACKEND", "gemini")
    try:
        importlib.reload(backends)
        from backends import gemini

        assert backends.generate is gemini.generate
    finally:
        _restore_default()


def test_unknown_card_backend_raises(monkeypatch):
    monkeypatch.setenv("CARD_BACKEND", "bogus")
    try:
        with pytest.raises(ValueError, match="Unknown CARD_BACKEND"):
            importlib.reload(backends)
    finally:
        _restore_default()
