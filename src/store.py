"""Deck persistence, picked by CARD_STORE the same way backends/__init__.py
picks an LLM backend via CARD_BACKEND. Defaults to `memory` (local dev and
tests, no credentials needed); the deploy workflow sets CARD_STORE=firestore.
See AGENTS.md."""

import json
import os
from datetime import datetime, timezone

# Firestore's hard document size limit is 1 MiB; this leaves headroom for
# field overhead. About 5,000 cards' worth -- far past what a person
# building an Anki deck by hand will ever accumulate, so this guards
# against a client bug looping the export, not a real ceiling.
MAX_DECK_BYTES = 500_000


class DeckTooLargeError(ValueError):
    pass


def _deck_size(cards: list[dict]) -> int:
    return len(json.dumps(cards, ensure_ascii=False).encode("utf-8"))


def _check_deck_size(cards: list[dict]) -> None:
    if _deck_size(cards) > MAX_DECK_BYTES:
        raise DeckTooLargeError("deck is too large to save")


class MemoryStore:
    """Process-local dict. Used for local dev (CARD_STORE unset) and tests
    -- decks don't survive a restart, same as decks never left the browser
    before this."""

    def __init__(self):
        self._decks: dict[str, dict] = {}

    def load(self, user_id: str) -> dict | None:
        return self._decks.get(user_id)

    def save(self, user_id: str, *, cards: list[dict], notetype: str, deck: str, email: str) -> None:
        _check_deck_size(cards)
        self._decks[user_id] = {"cards": cards, "notetype": notetype, "deck": deck}


class FirestoreStore:
    """One document per user in the `decks` collection, keyed by the
    ZITADEL `sub` (stable even if the user's email changes).

    Lives in a named database (`phrase-cards`), not `(default)` -- the GCP
    project this runs in is shared with other organisatrix apps, and a
    named database keeps this app's data in its own clearly-labeled
    Firestore instance rather than mixed into one shared `(default)`. The
    tradeoff: only one database per project ever gets the Always Free
    quota (normally `(default)`), so this one is billed from the first
    read/write -- at this app's scale, a fraction of a cent per month. The
    runtime service account's `roles/datastore.user` grant is restricted
    to this specific database via an IAM Condition, see AGENTS.md."""

    _DATABASE = "phrase-cards"
    _COLLECTION = "decks"

    def __init__(self):
        # Imported lazily so selecting CARD_STORE=memory (local dev, tests)
        # never needs google-cloud-firestore to touch credentials.
        from google.cloud import firestore

        self._client = firestore.Client(database=self._DATABASE)

    def load(self, user_id: str) -> dict | None:
        snapshot = self._client.collection(self._COLLECTION).document(user_id).get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        return {
            "cards": data.get("cards", []),
            "notetype": data.get("notetype", ""),
            "deck": data.get("deck", ""),
        }

    def save(self, user_id: str, *, cards: list[dict], notetype: str, deck: str, email: str) -> None:
        _check_deck_size(cards)
        self._client.collection(self._COLLECTION).document(user_id).set(
            {
                "cards": cards,
                "notetype": notetype,
                "deck": deck,
                "email": email,
                "updated_at": datetime.now(timezone.utc),
            }
        )


_STORE = os.environ.get("CARD_STORE", "memory")

if _STORE == "memory":
    store = MemoryStore()
elif _STORE == "firestore":
    store = FirestoreStore()
else:
    raise ValueError(f"Unknown CARD_STORE: {_STORE!r} (expected 'memory' or 'firestore')")

__all__ = ["store", "DeckTooLargeError", "MAX_DECK_BYTES"]
