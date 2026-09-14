import os
from datetime import timedelta

from flask import Flask, Response, jsonify, render_template, request, session
from pydantic import ValidationError

import auth
from backends import generate
from export import build_tsv
from furigana import readings_agree, to_furigana
from store import DeckTooLargeError, store

app = Flask(__name__)

_secret_key = os.environ.get("FLASK_SECRET_KEY", "")
if not _secret_key:
    if auth.ON_CLOUD_RUN:
        raise RuntimeError("FLASK_SECRET_KEY must be set when running on Cloud Run")
    # Session contents (auth is off locally, so just the deck's local user
    # bucket) aren't sensitive, and a fixed key keeps sessions valid across
    # dev-server reloads.
    _secret_key = "local-dev-only-not-a-secret"
app.secret_key = _secret_key

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Cloud Run terminates TLS in front of the container, so the app itself
# sees plain HTTP -- SESSION_COOKIE_SECURE is keyed off auth.ON_CLOUD_RUN
# rather than request.is_secure, which would always be False there.
app.config["SESSION_COOKIE_SECURE"] = auth.ON_CLOUD_RUN

auth.init_app(app)


def _current_user_id() -> str:
    # Falls back to a fixed id when auth is off (local dev): every request
    # shares one deck, same as there only ever being one user of the app
    # on your own machine.
    return session.get("sub", "local")


@app.get("/")
@auth.approved_required
def index():
    return render_template(
        "index.html",
        auth_enabled=auth.AUTH_ENABLED,
        user_email=session.get("email", ""),
    )


@app.post("/api/generate")
@auth.approved_required
def api_generate():
    data = request.get_json(silent=True) or {}
    vocab = (data.get("vocab") or "").strip()
    research = bool(data.get("research", False))
    guidance = (data.get("guidance") or "").strip()

    if not vocab:
        return jsonify({"error": "vocab is required"}), 400

    try:
        card = generate(vocab, research, guidance)
    except (ValidationError, ValueError, RuntimeError) as exc:
        # ValidationError/ValueError: the backend's own output didn't
        # parse into CardFields. RuntimeError: the backend itself failed
        # (e.g. a non-"success" Claude query, or an empty Gemini
        # response). Both are upstream failures, not a bad request.
        return jsonify({"error": str(exc)}), 502

    reading_fugashi = to_furigana(card.expression)

    return jsonify(
        {
            "front": card.front,
            "expression": card.expression,
            "reading": card.reading,
            "bemerkungen": card.bemerkungen,
            "reading_fugashi": reading_fugashi,
            "furigana_agrees": readings_agree(reading_fugashi, card.reading),
        }
    )


@app.post("/api/export")
@auth.approved_required
def api_export():
    data = request.get_json(silent=True) or {}
    cards = data.get("cards")
    notetype = data.get("notetype") or ""
    deck = data.get("deck") or ""

    if not isinstance(cards, list) or not cards or not all(isinstance(c, dict) for c in cards):
        return jsonify({"error": "cards must be a non-empty list of objects"}), 400

    tsv = build_tsv(cards, notetype=notetype, deck=deck)

    return Response(
        tsv,
        mimetype="text/tab-separated-values",
        headers={"Content-Disposition": 'attachment; filename="japanese-phrase-cards.txt"'},
    )


@app.get("/api/deck")
@auth.approved_required
def api_get_deck():
    data = store.load(_current_user_id())
    if data is None:
        # No document yet -- distinct from an empty deck, so the frontend
        # knows to offer uploading its localStorage copy instead of
        # treating "nothing on the server" as "the deck is empty".
        return jsonify({"cards": [], "notetype": "", "deck": "", "exists": False})
    return jsonify({**data, "exists": True})


@app.put("/api/deck")
@auth.approved_required
def api_put_deck():
    data = request.get_json(silent=True) or {}
    cards = data.get("cards")
    notetype = data.get("notetype") or ""
    deck = data.get("deck") or ""

    if not isinstance(cards, list) or not all(isinstance(c, dict) for c in cards):
        return jsonify({"error": "cards must be a list of objects"}), 400

    try:
        store.save(_current_user_id(), cards=cards, notetype=notetype, deck=deck, email=session.get("email", ""))
    except DeckTooLargeError as exc:
        return jsonify({"error": str(exc)}), 413

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
