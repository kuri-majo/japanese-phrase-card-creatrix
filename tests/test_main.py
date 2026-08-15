import pytest

import main as main_module
from prompt import CardFields


@pytest.fixture
def client():
    main_module.app.config["TESTING"] = True
    with main_module.app.test_client() as client:
        yield client


def test_index_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_generate_returns_card_plus_fugashi_reading_and_agreement(client, monkeypatch):
    fake_card = CardFields(
        front="es wird bald Winter",
        expression="もうすぐ冬になる",
        reading="もうすぐ 冬[ふゆ]になる",
        bemerkungen="",
    )
    monkeypatch.setattr(main_module, "generate", lambda vocab, research, guidance="": fake_card)

    resp = client.post("/api/generate", json={"vocab": "Xになる", "research": False})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {
        "front": "es wird bald Winter",
        "expression": "もうすぐ冬になる",
        "reading": "もうすぐ 冬[ふゆ]になる",
        "bemerkungen": "",
        "reading_fugashi": "もうすぐ 冬[ふゆ]になる",
        "furigana_agrees": True,
    }


def test_generate_flags_disagreement_on_ambiguous_reading(client, monkeypatch):
    # 明日 as あした (what the fake LLM wrote) vs fugashi's dictionary
    # default あす -- the real ambiguous-kanji scenario from furigana.py's
    # own tests, now exercised through the route.
    fake_card = CardFields(
        front="morgen regnet es",
        expression="明日は雨だ",
        reading="明日[あした]は 雨[あめ]だ",
        bemerkungen="",
    )
    monkeypatch.setattr(main_module, "generate", lambda vocab, research, guidance="": fake_card)

    resp = client.post("/api/generate", json={"vocab": "明日", "research": False})

    body = resp.get_json()
    assert body["reading_fugashi"] == "明日[あす]は 雨[あめ]だ"
    assert body["furigana_agrees"] is False


def test_generate_rejects_blank_vocab(client):
    resp = client.post("/api/generate", json={"vocab": "   ", "research": False})
    assert resp.status_code == 400


def test_generate_rejects_missing_vocab(client):
    resp = client.post("/api/generate", json={})
    assert resp.status_code == 400


def test_generate_passes_vocab_and_research_flag_through(client, monkeypatch):
    seen = {}

    def fake_generate(vocab, research, guidance=""):
        seen["vocab"] = vocab
        seen["research"] = research
        return CardFields(front="x", expression="x", reading="x", bemerkungen="")

    monkeypatch.setattr(main_module, "generate", fake_generate)

    client.post("/api/generate", json={"vocab": "だが", "research": True})

    assert seen == {"vocab": "だが", "research": True}


def test_generate_passes_guidance_through(client, monkeypatch):
    seen = {}

    def fake_generate(vocab, research, guidance=""):
        seen["guidance"] = guidance
        return CardFields(front="x", expression="x", reading="x", bemerkungen="")

    monkeypatch.setattr(main_module, "generate", fake_generate)

    client.post(
        "/api/generate",
        json={"vocab": "だが", "research": False, "guidance": "make it shorter"},
    )

    assert seen["guidance"] == "make it shorter"


def test_generate_defaults_guidance_to_empty_string_when_omitted(client, monkeypatch):
    seen = {}

    def fake_generate(vocab, research, guidance=""):
        seen["guidance"] = guidance
        return CardFields(front="x", expression="x", reading="x", bemerkungen="")

    monkeypatch.setattr(main_module, "generate", fake_generate)

    client.post("/api/generate", json={"vocab": "だが"})

    assert seen["guidance"] == ""


def test_generate_defaults_research_to_false_when_omitted(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        main_module,
        "generate",
        lambda vocab, research, guidance="": seen.update(research=research)
        or CardFields(front="x", expression="x", reading="x", bemerkungen=""),
    )

    client.post("/api/generate", json={"vocab": "だが"})

    assert seen["research"] is False


def test_generate_surfaces_backend_runtime_error_as_502(client, monkeypatch):
    def boom(vocab, research, guidance=""):
        raise RuntimeError("backend exploded")

    monkeypatch.setattr(main_module, "generate", boom)

    resp = client.post("/api/generate", json={"vocab": "Xになる", "research": False})

    assert resp.status_code == 502
    assert "backend exploded" in resp.get_json()["error"]


def test_generate_surfaces_malformed_backend_output_as_502(client, monkeypatch):
    def boom(vocab, research, guidance=""):
        raise ValueError("no JSON object found in Claude's response: 'oops'")

    monkeypatch.setattr(main_module, "generate", boom)

    resp = client.post("/api/generate", json={"vocab": "Xになる", "research": False})

    assert resp.status_code == 502


def test_export_builds_tsv_with_attachment_headers(client):
    cards = [
        {
            "front": "es wird bald Winter",
            "expression": "もうすぐ冬になる",
            "reading": "もうすぐ 冬[ふゆ]になる",
            "bemerkungen": "",
        }
    ]

    resp = client.post("/api/export", json={"cards": cards, "notetype": "MyType", "deck": "MyDeck"})

    assert resp.status_code == 200
    assert resp.headers["Content-Disposition"] == 'attachment; filename="japanese-phrase-cards.txt"'
    assert resp.mimetype == "text/tab-separated-values"
    body = resp.get_data(as_text=True)
    assert "#notetype:MyType" in body
    assert "#deck:MyDeck" in body
    assert "es wird bald Winter\tもうすぐ冬になる\tもうすぐ 冬[ふゆ]になる\t" in body


def test_export_rejects_empty_cards_list(client):
    resp = client.post("/api/export", json={"cards": []})
    assert resp.status_code == 400


def test_export_rejects_missing_cards(client):
    resp = client.post("/api/export", json={})
    assert resp.status_code == 400


def test_export_rejects_non_list_cards(client):
    resp = client.post("/api/export", json={"cards": "not a list"})
    assert resp.status_code == 400


def test_generate_allows_request_without_header_when_access_code_unset(client, monkeypatch):
    # The default (local dev, and any deployment that never set
    # APP_ACCESS_CODE): no gate at all.
    monkeypatch.setattr(main_module, "ACCESS_CODE", "")
    monkeypatch.setattr(
        main_module,
        "generate",
        lambda vocab, research, guidance="": CardFields(front="x", expression="x", reading="x"),
    )

    resp = client.post("/api/generate", json={"vocab": "だが", "research": False})

    assert resp.status_code == 200


def test_generate_rejects_missing_access_code_header(client, monkeypatch):
    monkeypatch.setattr(main_module, "ACCESS_CODE", "s3cr3t")

    resp = client.post("/api/generate", json={"vocab": "だが", "research": False})

    assert resp.status_code == 401


def test_generate_rejects_wrong_access_code_header(client, monkeypatch):
    monkeypatch.setattr(main_module, "ACCESS_CODE", "s3cr3t")

    resp = client.post(
        "/api/generate",
        json={"vocab": "だが", "research": False},
        headers={"X-Access-Code": "wrong"},
    )

    assert resp.status_code == 401


def test_generate_allows_correct_access_code_header(client, monkeypatch):
    monkeypatch.setattr(main_module, "ACCESS_CODE", "s3cr3t")
    monkeypatch.setattr(
        main_module,
        "generate",
        lambda vocab, research, guidance="": CardFields(front="x", expression="x", reading="x"),
    )

    resp = client.post(
        "/api/generate",
        json={"vocab": "だが", "research": False},
        headers={"X-Access-Code": "s3cr3t"},
    )

    assert resp.status_code == 200


def test_export_rejects_missing_access_code_header(client, monkeypatch):
    monkeypatch.setattr(main_module, "ACCESS_CODE", "s3cr3t")

    resp = client.post("/api/export", json={"cards": [{"front": "x", "expression": "x", "reading": "x"}]})

    assert resp.status_code == 401


def test_export_allows_correct_access_code_header(client, monkeypatch):
    monkeypatch.setattr(main_module, "ACCESS_CODE", "s3cr3t")

    resp = client.post(
        "/api/export",
        json={"cards": [{"front": "x", "expression": "x", "reading": "x"}]},
        headers={"X-Access-Code": "s3cr3t"},
    )

    assert resp.status_code == 200
