# japanese-phrase-card-creatrix

One of several independent apps linked from the organisatrix hub
(https://github.com/<you>/organisatrix) — see that repo's AGENTS.md for the
shared conventions (single GCP project, Cloud Run + Artifact Registry +
Workload Identity Federation, scale-to-zero only, budget alerts).

## What this app does

Builds Anki flashcards for Japanese vocabulary. You type in a word, phrase,
or grammar pattern (e.g. `Xになる`, `だが`); an LLM writes a short, natural
example — a collocation, phrase, or (for sentence-initial connectives) two
short connected sentences — using vocabulary up to roughly JLPT N3, so you
learn the word in the context it's actually used in, not in isolation.

Each card has four fields, matching the `JapaneseFurigana`-addon Anki note
type this was built for:

- **Front** — a Swiss Standard German translation of the expression (`ss`,
  never `ß`)
- **Expression** — the generated Japanese, no furigana
- **Reading** — the expression with furigana (`冬[ふゆ]`); generated twice,
  once by the LLM and once deterministically via `fugashi` (see
  `src/furigana.py`) — the two are cross-checked, and a disagreement (e.g.
  明日 read as あした vs. あす) is flagged in the UI for you to check by hand.
  `fugashi`'s reading wins as the default, editable, value
- **Bemerkungen** — a short German usage/grammar note, left empty unless
  there's genuinely something worth saying

Cards accumulate in the browser (`localStorage`, so nothing is lost on
reload) and export as a tab-separated `.txt` file for Anki's
File → Import — not `.apkg`, so you review and edit every card before it
ever reaches your collection.

Two interchangeable LLM backends (see `src/backends/`), picked by
`CARD_BACKEND`:

- **`claude`** (default, local dev) — Claude via the Claude Agent SDK,
  authenticated through your local Claude Code login. No API key; billed
  against your subscription/org, not a separate metered key.
- **`gemini`** (set by the deploy workflow) — Gemini on Vertex AI,
  authenticated via the Cloud Run service account's Application Default
  Credentials. Also no API key.

Both backends share one system prompt and JSON schema
(`src/prompt.py:CardFields`), so the two stay as close in behavior as
possible despite being different models.

## GCP APIs used

- Vertex AI (`roles/aiplatform.user`) — see organisatrix's `infra/README.md`
  step 5. Deployed backend calls Gemini (`gemini-3.7-flash`) via Vertex AI,
  authenticated through the Cloud Run service account's Application Default
  Credentials (no API key). Local dev uses the Claude Agent SDK against your
  Claude Code login instead — see `CARD_BACKEND` in `main.py`.

## Running locally

```bash
uv sync
uv run python src/main.py
```

Serves on `http://localhost:8080`.

## Deploying

Push to `main` — GitHub Actions builds the container and deploys it to
Cloud Run automatically (`.github/workflows/deploy.yml`). Before the first
push, set up the service account per organisatrix's `infra/README.md` step 4
(plus step 5 for any APIs declared above), then add `GCP_PROJECT_ID`,
`GCP_WORKLOAD_IDENTITY_PROVIDER`, and `GCP_SERVICE_ACCOUNT` as GitHub Actions
repository variables (Settings → Secrets and variables → Actions →
Variables) — the workflow reads them from there, not from the file.

Once deployed, add this app's URL to `apps.json` in the organisatrix hub
repo so it shows up on the landing page.
