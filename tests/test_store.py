import pytest

import main as main_module
import store as store_module
from store import DeckTooLargeError, MemoryStore

# --- MemoryStore directly ---------------------------------------------


def test_memory_store_returns_none_before_first_save():
    assert MemoryStore().load("someone") is None


def test_memory_store_round_trips_a_saved_deck():
    memory_store = MemoryStore()

    memory_store.save("someone", cards=[{"front": "x"}], notetype="t", deck="d", email="a@b.test")

    assert memory_store.load("someone") == {"cards": [{"front": "x"}], "notetype": "t", "deck": "d"}


def test_memory_store_keeps_different_users_separate():
    memory_store = MemoryStore()
    memory_store.save("user-a", cards=[{"front": "a"}], notetype="", deck="", email="")
    memory_store.save("user-b", cards=[{"front": "b"}], notetype="", deck="", email="")

    assert memory_store.load("user-a")["cards"] == [{"front": "a"}]
    assert memory_store.load("user-b")["cards"] == [{"front": "b"}]


def test_memory_store_rejects_oversized_deck(monkeypatch):
    monkeypatch.setattr(store_module, "MAX_DECK_BYTES", 10)

    with pytest.raises(DeckTooLargeError):
        MemoryStore().save(
            "someone", cards=[{"front": "way more than ten bytes of json"}], notetype="", deck="", email=""
        )


# --- via /api/deck (also exercises _current_user_id + the routes) -----


def test_deck_round_trips_cards_and_settings(client, auth_enabled, sign_in):
    sign_in(client, "user-1")

    put_resp = client.put(
        "/api/deck",
        json={
            "cards": [{"front": "x", "expression": "x", "reading": "x", "bemerkungen": ""}],
            "notetype": "MyType",
            "deck": "MyDeck",
        },
    )
    assert put_resp.status_code == 200

    get_resp = client.get("/api/deck")
    body = get_resp.get_json()

    assert body == {
        "cards": [{"front": "x", "expression": "x", "reading": "x", "bemerkungen": ""}],
        "notetype": "MyType",
        "deck": "MyDeck",
        "exists": True,
    }


def test_deck_reports_not_exists_before_any_save(client, auth_enabled, sign_in):
    sign_in(client, "user-never-saved")

    resp = client.get("/api/deck")

    assert resp.get_json() == {"cards": [], "notetype": "", "deck": "", "exists": False}


def test_deck_is_isolated_per_user(auth_enabled, sign_in):
    # Two separate (non-context-manager) clients, since two test_client()
    # `with` blocks nested in one `with` statement fight over Flask's
    # request-context stack on teardown.
    main_module.app.config["TESTING"] = True
    client_a = main_module.app.test_client()
    client_b = main_module.app.test_client()

    sign_in(client_a, "user-a")
    sign_in(client_b, "user-b")

    client_a.put("/api/deck", json={"cards": [{"front": "a"}], "notetype": "", "deck": ""})
    client_b.put("/api/deck", json={"cards": [{"front": "b"}], "notetype": "", "deck": ""})

    assert client_a.get("/api/deck").get_json()["cards"] == [{"front": "a"}]
    assert client_b.get("/api/deck").get_json()["cards"] == [{"front": "b"}]


def test_deck_put_rejects_non_list_cards(client, auth_enabled, sign_in):
    sign_in(client, "user-1")

    resp = client.put("/api/deck", json={"cards": "not a list"})

    assert resp.status_code == 400


def test_deck_put_rejects_non_object_card_elements(client, auth_enabled, sign_in):
    sign_in(client, "user-1")

    resp = client.put("/api/deck", json={"cards": ["not-a-card"]})

    assert resp.status_code == 400


def test_deck_put_rejects_oversized_payload(client, auth_enabled, sign_in, monkeypatch):
    monkeypatch.setattr(store_module, "MAX_DECK_BYTES", 10)
    sign_in(client, "user-huge")

    resp = client.put(
        "/api/deck",
        json={"cards": [{"front": "way more than ten bytes of json"}], "notetype": "", "deck": ""},
    )

    assert resp.status_code == 413
