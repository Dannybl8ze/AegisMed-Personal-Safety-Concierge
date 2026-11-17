"""Access control and rate limits for the dashboard API."""
import pytest

from dashboard_api import auth

CODE = "correct horse battery"


@pytest.fixture
def secured(client, monkeypatch):
    """The client with an access code configured, like a hosted deployment."""
    monkeypatch.setenv("AEGISMED_ACCESS_CODE", CODE)
    return client


def sign_in(client, code=CODE):
    return client.post("/api/login", data={"code": code})


# -- Open mode (local development) -----------------------------------------------

def test_without_a_code_the_local_api_is_open(client):
    assert client.get("/api/state").status_code == 200
    assert client.get("/api/session").json() == {"required": False, "authenticated": True, "configured": True}


# -- Sign-in ---------------------------------------------------------------------

def test_data_endpoints_refuse_anonymous_requests(secured):
    for method, path in [("get", "/api/state"), ("get", "/api/pending"), ("post", "/api/reset"),
                         ("post", "/api/chat"), ("post", "/api/resolve"), ("post", "/api/patients/add")]:
        r = getattr(secured, method)(path)
        assert r.status_code == 401, path
        assert r.json() == {"status": "error", "message": "Sign in required."}


def test_session_reports_the_sign_in_state(secured):
    assert secured.get("/api/session").json() == {"required": True, "authenticated": False, "configured": True}
    assert sign_in(secured).status_code == 200
    assert secured.get("/api/session").json()["authenticated"] is True


def test_a_wrong_code_is_rejected_and_sets_no_cookie(secured):
    r = sign_in(secured, "not the code")
    assert r.status_code == 401
    assert r.json()["message"] == "That access code is not correct."
    assert auth.COOKIE_NAME not in r.cookies
    assert secured.get("/api/state").status_code == 401


def test_the_right_code_opens_the_api_with_a_safe_cookie(secured):
    r = sign_in(secured)
    assert r.status_code == 200 and r.json() == {"status": "success"}

    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    assert CODE not in r.headers["set-cookie"], "the code itself must never be stored in the cookie"
    assert secured.get("/api/state").status_code == 200


def test_the_cookie_is_marked_secure_behind_https(secured):
    r = secured.post("/api/login", data={"code": CODE}, headers={"x-forwarded-proto": "https"})
    assert "secure" in r.headers["set-cookie"].lower()


def test_sign_out_ends_the_session(secured):
    sign_in(secured)
    assert secured.post("/api/logout").status_code == 200
    assert secured.get("/api/state").status_code == 401


def test_a_forged_or_expired_cookie_is_refused(secured):
    for bad in ["garbage", "9999999999.deadbeef", auth.make_token("another code"), auth.make_token(CODE, now=0)]:
        secured.cookies.set(auth.COOKIE_NAME, bad)
        assert secured.get("/api/state").status_code == 401, bad


def test_changing_the_code_signs_everyone_out(secured, monkeypatch):
    sign_in(secured)
    monkeypatch.setenv("AEGISMED_ACCESS_CODE", "a new code")
    assert secured.get("/api/state").status_code == 401


def test_token_validation_helpers():
    token = auth.make_token(CODE, now=1000)
    assert auth.token_is_valid(token, CODE, now=1000 + auth.SESSION_SECONDS - 1)
    assert not auth.token_is_valid(token, CODE, now=1000 + auth.SESSION_SECONDS)
    assert not auth.token_is_valid(token, None) and not auth.token_is_valid(None, CODE)
    assert auth.code_matches(CODE, CODE) and not auth.code_matches("x", CODE)


# -- Hosted deployments fail closed ----------------------------------------------

def test_a_hosted_deployment_without_a_code_serves_no_data(client, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("AEGISMED_ACCESS_CODE", raising=False)

    r = client.get("/api/state")
    assert r.status_code == 503 and "AEGISMED_ACCESS_CODE" in r.json()["message"]
    assert client.post("/api/login", data={"code": "anything"}).status_code == 503
    assert client.get("/api/session").json() == {"required": True, "authenticated": False, "configured": False}


def test_a_hosted_deployment_with_a_code_requires_sign_in(client, monkeypatch):
    monkeypatch.setenv("K_SERVICE", "aegismed")
    monkeypatch.setenv("AEGISMED_ACCESS_CODE", CODE)
    assert client.get("/api/state").status_code == 401


# -- Rate limits -----------------------------------------------------------------

def test_repeated_wrong_codes_are_throttled(secured):
    for _ in range(auth.LOGIN_ATTEMPTS):
        assert sign_in(secured, "wrong").status_code == 401

    r = sign_in(secured, "wrong")
    assert r.status_code == 429 and "Retry-After" in r.headers
    assert sign_in(secured).status_code == 429, "even the right code waits out the lockout"


def test_chat_is_limited_per_client(secured, monkeypatch):
    monkeypatch.setenv("AEGISMED_CHAT_LIMIT", "2")
    sign_in(secured)
    ask = lambda n: secured.post("/api/chat", data={"message": "Add Lisinopril 10mg for patient-104", "session_id": n})

    assert ask("a").status_code == 200 and ask("b").status_code == 200
    r = ask("c")
    assert r.status_code == 429 and "Too many requests" in r.json()["message"]
    assert "Retry-After" in r.headers


def test_chat_has_a_daily_cap_for_the_whole_deployment(secured, monkeypatch):
    monkeypatch.setenv("AEGISMED_DAILY_CHAT_LIMIT", "1")
    sign_in(secured)
    ask = lambda n: secured.post("/api/chat", data={"message": "Add Lisinopril 10mg for patient-104", "session_id": n})

    assert ask("a").status_code == 200
    r = ask("b")
    assert r.status_code == 429 and "daily request limit" in r.json()["message"]


def test_a_demo_reset_does_not_clear_the_limits(secured, monkeypatch):
    monkeypatch.setenv("AEGISMED_CHAT_LIMIT", "1")
    sign_in(secured)
    ask = lambda n: secured.post("/api/chat", data={"message": "Add Lisinopril 10mg for patient-104", "session_id": n})

    assert ask("a").status_code == 200
    secured.post("/api/reset")
    assert ask("b").status_code == 429


def test_the_counter_contract_holds_for_both_stores(storage):
    assert [storage.hit("k", 60) for _ in range(3)] == [1, 2, 3]
    assert storage.hit("other", 60) == 1
    storage.reset_demo_state()
    assert storage.hit("k", 60) == 4
