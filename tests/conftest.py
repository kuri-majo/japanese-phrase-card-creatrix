import pytest

import auth as auth_module
import main as main_module


@pytest.fixture
def client():
    main_module.app.config["TESTING"] = True
    with main_module.app.test_client() as client:
        yield client


@pytest.fixture
def auth_enabled(monkeypatch):
    # AUTH_ENABLED/AUTH_MISCONFIGURED are computed once at import time from
    # env vars that aren't set in the test environment (no real ZITADEL
    # instance to talk to) -- patched directly here instead, same as this
    # suite patches main_module.generate elsewhere. The decorator in
    # auth.py reads these as globals on every call, so patching takes
    # effect immediately without reloading either module.
    monkeypatch.setattr(auth_module, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth_module, "AUTH_MISCONFIGURED", False)


@pytest.fixture
def sign_in():
    def _sign_in(client, sub, approved=True):
        with client.session_transaction() as sess:
            sess["sub"] = sub
            sess["approved"] = approved

    return _sign_in
