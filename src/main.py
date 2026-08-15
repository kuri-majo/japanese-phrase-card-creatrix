from flask import Flask, Response, jsonify, render_template, request
from pydantic import ValidationError

from backends import generate
from export import build_tsv
from furigana import readings_agree, to_furigana

app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/generate")
def api_generate():
    data = request.get_json(silent=True) or {}
    vocab = (data.get("vocab") or "").strip()
    research = bool(data.get("research", False))

    if not vocab:
        return jsonify({"error": "vocab is required"}), 400

    try:
        card = generate(vocab, research)
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
def api_export():
    data = request.get_json(silent=True) or {}
    cards = data.get("cards")
    notetype = data.get("notetype") or ""
    deck = data.get("deck") or ""

    if not isinstance(cards, list) or not cards:
        return jsonify({"error": "cards must be a non-empty list"}), 400

    tsv = build_tsv(cards, notetype=notetype, deck=deck)

    return Response(
        tsv,
        mimetype="text/tab-separated-values",
        headers={"Content-Disposition": 'attachment; filename="japanese-phrase-cards.txt"'},
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
