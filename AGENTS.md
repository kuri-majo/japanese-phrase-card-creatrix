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

Cards accumulate in a per-user deck — synced to Firestore once you're
signed in (see Storage below), mirrored into the browser's `localStorage`
so a flaky connection doesn't lose anything — and export as a
tab-separated `.txt` file for Anki's File → Import — not `.apkg`, so you
review and edit every card before it ever reaches your collection.

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
- Firestore (`roles/datastore.user`), Native mode, named database
  `phrase-cards` in the same region as Cloud Run — stores each user's deck.
  See Storage below.

## Authentication

User accounts are [ZITADEL Cloud](https://zitadel.cloud), not something this
app implements itself — plain OIDC (Authorization Code + PKCE via Authlib,
`src/auth.py`), MFA/passkeys handled entirely on ZITADEL's side. Chosen over
self-hosting ZITADEL because self-hosted ZITADEL needs an always-on
container plus a 4–6 GB PostgreSQL instance, which breaks the
scale-to-zero/no-idle-cost rule this project follows; ZITADEL Cloud's free
tier (100 daily active users, unlimited accounts, MFA, EU/CH hosting) covers
a handful of users at no cost.

Users self-register through ZITADEL's hosted login. That alone doesn't let
them generate cards or see a deck — until you grant their account the
`card-creator` role on the project (ZITADEL console → project → **Role
Assignments** — formerly *Authorizations* — → New → pick the user → role
`card-creator`), they're stuck on a "pending approval" page. That grant *is*
the approval step, and it's what keeps a stranger who finds the URL from
spending your Vertex AI budget.

Auth has three states, controlled entirely by env vars (see the top of
`src/auth.py`):

- **Off** — `ZITADEL_DOMAIN` unset and not running on Cloud Run (`K_SERVICE`
  unset). Local dev's default: `uv run python src/main.py` needs no ZITADEL
  instance.
- **On** — `ZITADEL_DOMAIN`, `ZITADEL_CLIENT_ID`, `ZITADEL_CLIENT_SECRET`,
  `ZITADEL_PROJECT_ID`, and `APP_BASE_URL` all set.
- **Fail closed** — anything in between (deployed without full config, or a
  half-set local `.env`). Every request is refused rather than silently
  running open.

`FLASK_SECRET_KEY` signs the session cookie and is required whenever
`K_SERVICE` is set — the container refuses to start without it, since an
auto-generated per-instance key would break sessions across Cloud Run's
multiple instances.

One-time setup in the ZITADEL console, before the first deploy (console
labels current as of September 2026 — ZITADEL has renamed several of these
toggles over time, so if a label doesn't match, look for the setting by its
description instead):

1. Create a free instance at zitadel.cloud (EU/CH region).
2. Default org → Settings → Default Settings → Login Behavior and Security:
   enable the self-registration toggle (shows the register button on the
   login screen; labeled *Register allowed* as of this writing). Optionally
   enable *Force MFA*.
3. Create project `japanese-phrase-card-creatrix`, add role `card-creator`,
   enable **Assign user roles during authentication** (formerly *Assert
   Roles on Authentication*). Leave **Only authorized users can
   authenticate** (formerly *Check authorization on Authentication*) off —
   the app does that check itself so unapproved users see the pending page
   instead of a ZITADEL error.
4. In that project, add a Web application, authentication method **Code**
   (issues both a client ID and client secret) — not *PKCE*, which issues
   no secret at all and is meant for public clients that can't store one;
   this app is a server-side Flask backend that can. Redirect URIs:
   `<app-url>/auth/callback` and `http://localhost:8080/auth/callback` (for
   local testing against the real IdP — also turn on that application's
   **Dev Mode** toggle, or ZITADEL rejects the plain-`http://` localhost
   redirect). Post-logout redirect URIs: `<app-url>/auth/logout/callback`
   **and** `http://localhost:8080/auth/logout/callback` — the full path,
   not just the bare domain; `src/auth.py`'s `/auth/logout` route sends
   users to exactly that path, and ZITADEL rejects anything not registered
   verbatim (`post_logout_redirect_uri invalid`). Copy the client ID and
   secret into the GitHub Actions variables/secrets below.

To approve a new signup: project → Role Assignments (formerly Authorizations)
→ New → pick the user → role `card-creator`. This can also be done from the
organization page or the Users page instead of the project page.

## Storage

Each user's deck (cards plus their Anki note-type/deck-name settings) is one
document in Firestore (Native mode), collection `decks`, keyed by the
ZITADEL `sub` (stable even if the user's email changes later) — see
`src/store.py`. The browser keeps a `localStorage` mirror so the app
degrades gracefully if a save fails, but the server document is the source
of truth once it exists; there's no merge across devices, last write wins.

Picked by `CARD_STORE`, mirroring how `CARD_BACKEND` picks the LLM backend:

- **`memory`** (default) — a process-local dict, no credentials touched.
  Used for local dev and tests.
- **`firestore`** (set by the deploy workflow) — real persistence via the
  Cloud Run service account's Application Default Credentials.

Firestore over Cloud SQL or Cloud Storage: it scales to zero (no idle cost,
unlike a Postgres instance), and — for the shared GCP project's `(default)`
database — its Always Free quota (1 GiB stored, 50,000 reads / 20,000
writes / 20,000 deletes per day, per project) has no region restriction,
unlike Cloud Storage's Always Free tier (US regions only).

This app deliberately does **not** use `(default)`, though. The GCP project
is shared across organisatrix apps (see the top of this file), and Firestore
now supports multiple independently-named databases per project, each with
its own collections and its own IAM. So this app gets its own database,
named **`phrase-cards`** — matching the `run-phrase-cards`/
`deploy-phrase-cards` service-account naming already used in this project —
with the runtime service account's `roles/datastore.user` grant restricted
to just that database via an IAM Condition. The cost: only one database per
project ever carries the Always Free flag (normally `(default)`), so a named
database is billed from the first read. At this app's scale (a handful of
users, occasional reads/writes, well under a MB of decks) that's a fraction
of a cent a month — the isolation is worth more than the accounting label.
Any future organisatrix app added to this same project should follow the
same pattern: its own named database, its own IAM Condition.

One-time setup:

```bash
gcloud services enable firestore.googleapis.com --project=<PROJECT_ID>

gcloud firestore databases create \
  --database=phrase-cards \
  --location=<cloud-run-region> \
  --type=firestore-native \
  --project=<PROJECT_ID>

gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member="serviceAccount:<GCP_RUNTIME_SERVICE_ACCOUNT>" \
  --role="roles/datastore.user" \
  --condition='expression=resource.name=="projects/<PROJECT_ID>/databases/phrase-cards",title=phrase-cards-db-only,description=Restrict to the phrase-cards Firestore database only'
```

The IAM Condition isn't shown or enforced in the Cloud Console's own
database browser, only on real API/client-library calls — which is all this
app ever makes.

## Running locally

```bash
uv sync
uv run python src/main.py
```

Serves on `http://localhost:8080`.

## Deploying

Push to `main` — GitHub Actions builds the container and deploys it to
Cloud Run automatically (`.github/workflows/deploy.yml`). Before the first
push:

1. Set up the service account per organisatrix's `infra/README.md` step 4
   (plus step 5 for any APIs declared above).
2. Complete the one-time ZITADEL Cloud setup (Authentication, above) and the
   one-time Firestore setup (Storage, above).
3. Add these as GitHub Actions repository variables (Settings → Secrets and
   variables → Actions → Variables): `GCP_PROJECT_ID`,
   `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`,
   `GCP_RUNTIME_SERVICE_ACCOUNT`, `ZITADEL_DOMAIN`, `ZITADEL_CLIENT_ID`,
   `ZITADEL_PROJECT_ID`, `APP_BASE_URL` (the deployed Cloud Run URL).
4. Add these as repository secrets (same page → Secrets):
   `ZITADEL_CLIENT_SECRET`, `FLASK_SECRET_KEY` (any long random string, e.g.
   `openssl rand -hex 32`).

The workflow reads all of these from there, not from the file.

Once deployed, add this app's URL to `apps.json` in the organisatrix hub
repo so it shows up on the landing page.
