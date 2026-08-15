"""Picks which LLM backend generates cards, via CARD_BACKEND. Defaults to
`claude` (local dev, your Claude Code subscription); the deploy workflow
sets CARD_BACKEND=gemini (Cloud Run, Vertex AI + Application Default
Credentials). See AGENTS.md."""

import os

_BACKEND = os.environ.get("CARD_BACKEND", "claude")

if _BACKEND == "claude":
    from .claude_local import generate
elif _BACKEND == "gemini":
    from .gemini import generate
else:
    raise ValueError(f"Unknown CARD_BACKEND: {_BACKEND!r} (expected 'claude' or 'gemini')")

__all__ = ["generate"]
