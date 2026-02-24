"""
Tests for the Maven backend API endpoints.

Covers auth (signup, login, /me), search history CRUD,
personalization, and the research endpoint.

Run:
    cd backend && python -m pytest test_api.py -v
"""

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Setup: override database before importing app
# ---------------------------------------------------------------------------
# Use a temp SQLite DB so tests never touch the production DB
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
TEST_DB_PATH = _tmp.name
_tmp.close()

TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH}"

# Patch env BEFORE importing app modules so database.py picks up the test URL
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from database import Base, get_db, engine, SessionLocal, SearchHistory  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def setup_database():
    """Create tables before each test and drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    """Use context-manager form so startup/shutdown events fire properly."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
TEST_USER = {"name": "Test User", "email": "test@example.com", "password": "password123"}


def _signup(client, user=None):
    """Sign up and return the response JSON."""
    user = user or TEST_USER
    return client.post("/api/auth/signup", json=user)


def _auth_header(token: str):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Auth: Signup
# ---------------------------------------------------------------------------
class TestSignup:
    def test_signup_success(self, client):
        resp = _signup(client)
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["email"] == TEST_USER["email"]
        assert data["user"]["name"] == TEST_USER["name"]
        assert "id" in data["user"]

    def test_signup_returns_valid_jwt(self, client):
        data = _signup(client).json()
        # Token should be a 3-part JWT
        parts = data["token"].split(".")
        assert len(parts) == 3

    def test_signup_duplicate_email(self, client):
        _signup(client)
        resp = _signup(client)
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"].lower()

    def test_signup_duplicate_email_case_insensitive(self, client):
        _signup(client)
        upper = {**TEST_USER, "email": TEST_USER["email"].upper()}
        resp = _signup(client, upper)
        assert resp.status_code == 400

    def test_signup_missing_name(self, client):
        resp = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "123456"})
        assert resp.status_code == 422

    def test_signup_short_password(self, client):
        resp = client.post("/api/auth/signup", json={"name": "X", "email": "a@b.com", "password": "12"})
        assert resp.status_code == 422

    def test_signup_missing_email(self, client):
        resp = client.post("/api/auth/signup", json={"name": "X", "password": "123456"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Auth: Login
# ---------------------------------------------------------------------------
class TestLogin:
    def test_login_success(self, client):
        _signup(client)
        resp = client.post("/api/auth/login", json={
            "email": TEST_USER["email"],
            "password": TEST_USER["password"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["email"] == TEST_USER["email"]

    def test_login_wrong_password(self, client):
        _signup(client)
        resp = client.post("/api/auth/login", json={
            "email": TEST_USER["email"],
            "password": "wrong_password",
        })
        assert resp.status_code == 401
        assert "invalid" in resp.json()["detail"].lower()

    def test_login_nonexistent_user(self, client):
        resp = client.post("/api/auth/login", json={
            "email": "nobody@example.com",
            "password": "password123",
        })
        assert resp.status_code == 401

    def test_login_missing_fields(self, client):
        resp = client.post("/api/auth/login", json={"email": "a@b.com"})
        assert resp.status_code == 422

    def test_login_case_insensitive_email(self, client):
        _signup(client)
        resp = client.post("/api/auth/login", json={
            "email": TEST_USER["email"].upper(),
            "password": TEST_USER["password"],
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Auth: /me
# ---------------------------------------------------------------------------
class TestMe:
    def test_me_authenticated(self, client):
        token = _signup(client).json()["token"]
        resp = client.get("/api/auth/me", headers=_auth_header(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == TEST_USER["email"]
        assert data["name"] == TEST_USER["name"]

    def test_me_no_token(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code in (401, 403)

    def test_me_invalid_token(self, client):
        resp = client.get("/api/auth/me", headers=_auth_header("bad.token.here"))
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Search History
# ---------------------------------------------------------------------------
class TestHistory:
    def _create_user(self, client):
        data = _signup(client).json()
        return data["token"], data["user"]["id"]

    def test_get_history_empty(self, client):
        token, _ = self._create_user(client)
        resp = client.get("/api/history", headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_history_unauthorized(self, client):
        resp = client.get("/api/history")
        assert resp.status_code in (401, 403)

    def test_delete_history_nonexistent(self, client):
        token, _ = self._create_user(client)
        resp = client.delete("/api/history/9999", headers=_auth_header(token))
        assert resp.status_code == 404

    def test_history_insert_and_retrieve(self, client):
        """Directly insert a history row and verify GET /api/history returns it."""
        token, user_id = self._create_user(client)

        # Insert via the database directly (the stream endpoint does this)
        db = SessionLocal()
        entry = SearchHistory(
            user_id=user_id,
            query="best headphones",
            products=[{"name": "Sony WH-1000XM5"}],
            recommendation="Buy the Sony.",
        )
        db.add(entry)
        db.commit()
        entry_id = entry.id
        db.close()

        resp = client.get("/api/history", headers=_auth_header(token))
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["query"] == "best headphones"
        assert items[0]["id"] == entry_id

        # Delete it
        resp = client.delete(f"/api/history/{entry_id}", headers=_auth_header(token))
        assert resp.status_code == 200

        # Verify gone
        resp = client.get("/api/history", headers=_auth_header(token))
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Personalization
# ---------------------------------------------------------------------------
class TestPersonalization:
    def test_init_empty_query(self, client):
        resp = client.post("/api/personalization/init", json={"query": ""})
        assert resp.status_code == 400

    def test_init_missing_query(self, client):
        resp = client.post("/api/personalization/init", json={})
        assert resp.status_code == 422

    def test_answers_unknown_session(self, client):
        resp = client.post("/api/personalization/answers", json={
            "session_id": "nonexistent",
            "answers": {"budget": "500"},
        })
        assert resp.status_code == 404

    def test_answers_missing_session_id(self, client):
        resp = client.post("/api/personalization/answers", json={
            "answers": {"budget": "500"},
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Research (non-streaming) – quick smoke test
# ---------------------------------------------------------------------------
class TestResearch:
    def test_research_missing_query_field(self, client):
        """Research with missing query field should return 422."""
        resp = client.post("/api/research", json={})
        assert resp.status_code == 422

    def test_research_requires_json(self, client):
        """Research without a JSON body should fail."""
        resp = client.post("/api/research")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Image proxy
# ---------------------------------------------------------------------------
class TestImageProxy:
    def test_image_proxy_no_url(self, client):
        resp = client.get("/api/image-proxy")
        assert resp.status_code in (400, 422)

    def test_image_proxy_bad_url(self, client):
        resp = client.get("/api/image-proxy", params={"url": "not-a-url"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# SSE stream endpoint – verify it starts and returns correct content type
# ---------------------------------------------------------------------------
class TestStream:
    def test_stream_endpoint_exists(self, client):
        """The stream endpoint should accept GET requests (returns event-stream)."""
        resp = client.get("/api/research/stream", params={"query": ""})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
def teardown_module():
    """Remove the temp DB after all tests."""
    try:
        os.unlink(TEST_DB_PATH)
    except OSError:
        pass
