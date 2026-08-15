# japanese-phrase-card-creatrix

Turns a piece of Japanese vocabulary into an Anki flashcard, in context.

Type in a word, phrase, or grammar pattern (`Xになる`, `だが`, `一日中`, …), and
an LLM writes a short, natural example using it — a collocation, phrase, or
(for sentence-initial connectives) two short connected sentences, kept to
roughly JLPT N3-level vocabulary. Each card gets:

- **Front** — a Swiss Standard German translation
- **Expression** — the generated Japanese
- **Reading** — the expression with furigana, cross-checked against a
  deterministic reading from [fugashi](https://github.com/polm/fugashi) so
  genuine ambiguities (明日 as あした vs. あす) get flagged instead of silently
  trusted
- **Bemerkungen** — a short usage/grammar note, left empty unless there's
  something worth saying

Cards accumulate in the browser and export as a tab-separated `.txt` for
Anki's File → Import (built for the `JapaneseFurigana` add-on's field
format) — not `.apkg`, so every card gets reviewed before it reaches your
collection.

## Running locally

```bash
uv sync
uv run python src/main.py
```

Serves on `http://localhost:8080`. Uses the Claude Agent SDK against your
local Claude Code login — no API key needed, just `ant auth login` (or an
existing Claude Code session).

## Deploying

Push to `main` — GitHub Actions builds the container and deploys it to
Cloud Run automatically (`.github/workflows/deploy.yml`). The deployed
backend switches to Gemini on Vertex AI (`CARD_BACKEND=gemini`),
authenticated via the Cloud Run service account's Application Default
Credentials — see [AGENTS.md](AGENTS.md) for the full backend/auth setup
and the organisatrix `infra/README.md` steps this depends on.

See the [organisatrix](../../) repo root for the overall architecture this
app fits into.
