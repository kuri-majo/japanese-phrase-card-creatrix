"""ZITADEL login (OIDC, Authorization Code + PKCE via Authlib) and the
route decorator that gates access to the app.

Enablement has three states, controlled entirely by env vars:

- Nothing set, not on Cloud Run (K_SERVICE unset): auth is off. This is
  local dev's default -- `uv run python src/main.py` needs no ZITADEL
  instance to work.
- All of ZITADEL_DOMAIN/CLIENT_ID/CLIENT_SECRET/PROJECT_ID/APP_BASE_URL
  set: auth is on, normal login flow.
- Anything in between (a real Cloud Run deployment, or a partial local
  config) -- fail closed. Every request is refused rather than silently
  running with auth half-configured or disabled. This is enforced once,
  in init_app's before_request hook, rather than per-route -- a route
  that forgets to decorate itself still gets refused.
"""

import functools
import os

from authlib.integrations.flask_client import OAuth
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

ZITADEL_DOMAIN = os.environ.get("ZITADEL_DOMAIN", "")
ZITADEL_CLIENT_ID = os.environ.get("ZITADEL_CLIENT_ID", "")
ZITADEL_CLIENT_SECRET = os.environ.get("ZITADEL_CLIENT_SECRET", "")
ZITADEL_PROJECT_ID = os.environ.get("ZITADEL_PROJECT_ID", "")
APP_BASE_URL = os.environ.get("APP_BASE_URL", "").rstrip("/")

# Cloud Run sets this on every revision; main.py also reads this (imported
# from here) to require a real FLASK_SECRET_KEY and a secure session
# cookie on any real deployment, while still letting local dev run with
# neither.
ON_CLOUD_RUN = bool(os.environ.get("K_SERVICE", ""))

_REQUIRED_VARS = (ZITADEL_DOMAIN, ZITADEL_CLIENT_ID, ZITADEL_CLIENT_SECRET, ZITADEL_PROJECT_ID, APP_BASE_URL)

AUTH_ENABLED = all(_REQUIRED_VARS)
AUTH_MISCONFIGURED = (ON_CLOUD_RUN or any(_REQUIRED_VARS)) and not AUTH_ENABLED

# The project role that marks a user as approved -- granted by hand in the
# ZITADEL console (project -> Role Assignments -> New), see AGENTS.md.
ROLE = "card-creator"

_SCOPE = "openid profile email urn:zitadel:iam:org:projects:roles"

oauth = OAuth()
bp = Blueprint("auth", __name__, url_prefix="/auth")


def init_app(app):
    app.register_blueprint(bp)

    @app.before_request
    def _reject_if_misconfigured():
        if AUTH_MISCONFIGURED:
            return jsonify({"error": "authentication is misconfigured"}), 503

    if not AUTH_ENABLED:
        return
    oauth.init_app(app)
    oauth.register(
        name="zitadel",
        client_id=ZITADEL_CLIENT_ID,
        client_secret=ZITADEL_CLIENT_SECRET,
        server_metadata_url=f"{ZITADEL_DOMAIN}/.well-known/openid-configuration",
        client_kwargs={"scope": _SCOPE},
    )


@bp.before_request
def _redirect_if_auth_disabled():
    # AUTH_MISCONFIGURED is already refused above, by the app-wide
    # before_request. This covers the other case where these routes can't
    # work: auth genuinely off (local dev) -- there's no oauth.zitadel
    # client registered, so send browsers home instead of letting
    # oauth.zitadel.* raise AttributeError on a stray/bookmarked hit.
    if not AUTH_ENABLED:
        return redirect("/")


def _role_claim(userinfo: dict) -> dict:
    # ZITADEL asserts project roles under a project-scoped claim key; a
    # legacy unprefixed key also exists for older/simpler project setups,
    # and ZITADEL's own console labels/behavior have shifted under us
    # during this project already -- cheap enough to keep both.
    return (
        userinfo.get(f"urn:zitadel:iam:org:project:{ZITADEL_PROJECT_ID}:roles")
        or userinfo.get("urn:zitadel:iam:org:project:roles")
        or {}
    )


@bp.get("/login")
def login():
    return oauth.zitadel.authorize_redirect(f"{APP_BASE_URL}/auth/callback")


@bp.get("/callback")
def callback():
    token = oauth.zitadel.authorize_access_token()
    # Fetched explicitly rather than relying on token["userinfo"] -- the
    # project-roles claim only reliably lands in the userinfo response,
    # regardless of whether "assert roles in ID token" is turned on.
    userinfo = oauth.zitadel.userinfo(token=token)

    session.clear()
    session.permanent = True
    session["sub"] = userinfo["sub"]
    session["email"] = userinfo.get("email", "")
    session["approved"] = ROLE in _role_claim(userinfo)
    return redirect("/")


@bp.get("/logout")
def logout():
    session.clear()
    metadata = oauth.zitadel.load_server_metadata()
    end_session_endpoint = metadata.get("end_session_endpoint")
    if not end_session_endpoint:
        return redirect("/")
    # client_id stands in for id_token_hint, which we'd otherwise need to
    # have kept a copy of the ID token to supply -- ZITADEL accepts either
    # to identify the client and validate post_logout_redirect_uri.
    return redirect(
        f"{end_session_endpoint}?client_id={ZITADEL_CLIENT_ID}"
        f"&post_logout_redirect_uri={APP_BASE_URL}/auth/logout/callback"
    )


@bp.get("/logout/callback")
def logout_callback():
    return redirect("/")


def approved_required(view):
    """Gates a route on login + approval. Implies login: an unauthenticated
    request is redirected/401'd the same as an unapproved one would be
    403'd, so a route needs only this one decorator, not a separate
    login-only one -- there's no route in this app that wants "logged in
    but not necessarily approved"."""

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not AUTH_ENABLED:
            return view(*args, **kwargs)
        if "sub" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "sign-in required"}), 401
            return redirect(url_for("auth.login"))
        if not session.get("approved"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "account pending approval"}), 403
            return render_template("pending.html")
        return view(*args, **kwargs)

    return wrapped
