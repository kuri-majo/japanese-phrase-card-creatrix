import pytest
from authlib.integrations.base_client.errors import MismatchingStateError

import auth as auth_module
import main as main_module
from prompt import CardFields


def test_generate_requires_login_when_auth_enabled(client, auth_enabled):
    resp = client.post("/api/generate", json={"vocab": "だが", "research": False})
    assert resp.status_code == 401


def test_index_redirects_to_login_when_signed_out(client, auth_enabled):
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/auth/login")


def test_generate_forbidden_without_approval(client, auth_enabled, sign_in):
    sign_in(client, "user-1", approved=False)

    resp = client.post("/api/generate", json={"vocab": "だが", "research": False})

    assert resp.status_code == 403


def test_index_renders_pending_page_without_approval(client, auth_enabled, sign_in):
    sign_in(client, "user-1", approved=False)

    resp = client.get("/")

    assert resp.status_code == 200
    assert b"pending approval" in resp.data.lower()


def test_generate_allowed_when_approved(client, auth_enabled, sign_in, monkeypatch):
    monkeypatch.setattr(
        main_module,
        "generate",
        lambda vocab, research, guidance="": CardFields(front="x", expression="x", reading="x"),
    )
    sign_in(client, "user-1")

    resp = client.post("/api/generate", json={"vocab": "だが", "research": False})

    assert resp.status_code == 200


@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("get", "/", None),
        ("post", "/api/generate", {"vocab": "だが", "research": False}),
        ("post", "/api/export", {"cards": [{"front": "x", "expression": "x", "reading": "x"}]}),
        ("get", "/api/deck", None),
        ("put", "/api/deck", {"cards": []}),
        ("get", "/auth/login", None),
    ],
)
def test_every_route_fails_closed_when_misconfigured(client, monkeypatch, method, path, json_body):
    # The state a real Cloud Run deployment would be in if ZITADEL_DOMAIN
    # (or any of its companion vars) never got set -- every request must be
    # refused, never silently served as if auth were off. Enforced once in
    # auth.init_app's app-wide before_request, so it applies even to a
    # route that forgets @auth.approved_required (and to the auth
    # blueprint's own routes, which have no such decorator at all).
    monkeypatch.setattr(auth_module, "AUTH_ENABLED", False)
    monkeypatch.setattr(auth_module, "AUTH_MISCONFIGURED", True)

    resp = getattr(client, method)(path, json=json_body)

    assert resp.status_code == 503


@pytest.mark.parametrize("path", ["/auth/login", "/auth/callback", "/auth/logout"])
def test_auth_routes_redirect_home_when_auth_disabled(client, path):
    # Regression: these used to reach for oauth.zitadel, which is never
    # registered when auth is off (e.g. local dev) -- an unguarded stray
    # or bookmarked hit on one of these crashed with an unhandled
    # AttributeError (500) instead of failing gracefully.
    resp = client.get(path)

    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"


def test_callback_recovers_from_stale_state_by_restarting_login(client, auth_enabled, monkeypatch):
    # A reloaded or resumed login page can complete against a session
    # cookie whose stored state no longer matches -- previously an
    # unhandled MismatchingStateError crashed this into a 500.
    class FakeZitadel:
        def authorize_access_token(self):
            raise MismatchingStateError()

    monkeypatch.setattr(auth_module.oauth, "zitadel", FakeZitadel(), raising=False)

    resp = client.get("/auth/callback")

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/auth/login")


def test_role_claim_reads_project_scoped_key(monkeypatch):
    monkeypatch.setattr(auth_module, "ZITADEL_PROJECT_ID", "12345")
    userinfo = {"urn:zitadel:iam:org:project:12345:roles": {auth_module.ROLE: {}}}

    assert auth_module.ROLE in auth_module._role_claim(userinfo)


def test_role_claim_falls_back_to_legacy_key(monkeypatch):
    monkeypatch.setattr(auth_module, "ZITADEL_PROJECT_ID", "12345")
    userinfo = {"urn:zitadel:iam:org:project:roles": {auth_module.ROLE: {}}}

    assert auth_module.ROLE in auth_module._role_claim(userinfo)


def test_role_claim_empty_when_no_roles_present():
    assert auth_module._role_claim({}) == {}
