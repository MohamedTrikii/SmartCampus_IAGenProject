"""SA-24 / SA-27 : sessions anonymes, authentification JWT et rôles."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db.models import VisitorSession
from tests.conftest import ADMIN, login, register

API = "/api/v1"


# --- sessions visiteurs ---
def test_create_session_collects_no_personal_data(client):
    r = client.post(f"{API}/sessions")
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"session_id", "expires_at", "user_id"} and body["user_id"] is None


def test_read_session_updates_last_seen(client, session_id, db):
    before = db.get(VisitorSession, uuid.UUID(session_id)).last_seen_at
    db.rollback()  # libère la connexion SQLite partagée avant la requête
    r = client.get(f"{API}/sessions/me", headers={"X-Session-Id": session_id})
    assert r.status_code == 200 and r.json()["session_id"] == session_id
    db.expire_all()
    assert db.get(VisitorSession, uuid.UUID(session_id)).last_seen_at >= before


def test_session_header_missing_or_invalid(client):
    r = client.get(f"{API}/sessions/me")
    assert r.status_code == 400 and r.json()["code"] == "SESSION_ID_MISSING"
    r = client.get(f"{API}/sessions/me", headers={"X-Session-Id": "pas-un-uuid"})
    assert r.status_code == 400 and r.json()["code"] == "SESSION_ID_INVALID"


def test_expired_or_unknown_session(client, session_id, db):
    s = db.get(VisitorSession, uuid.UUID(session_id))
    s.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    r = client.get(f"{API}/sessions/me", headers={"X-Session-Id": session_id})
    assert r.status_code == 401 and r.json()["code"] == "SESSION_EXPIRED"
    r = client.get(f"{API}/sessions/me", headers={"X-Session-Id": str(uuid.uuid4())})
    assert r.status_code == 401


# --- inscription / connexion ---
def test_register_links_anonymous_session(client, session_id):
    h = {"X-Session-Id": session_id}
    client.post(f"{API}/chat/messages", json={"message": "bonjour"}, headers=h)
    r = client.post(
        f"{API}/auth/register",
        json={"email": "Ali@test.tn", "password": "motdepasse1", "full_name": "Ali Ben Salah"},
        headers=h,
    )
    assert r.status_code == 201 and r.json()["role"] == "candidate"
    assert "password" not in r.json() and "password_hash" not in r.json()
    assert client.get(f"{API}/sessions/me", headers=h).json()["user_id"] == r.json()["id"]
    auth = login(client, "ali@test.tn", "motdepasse1")
    assert client.get(f"{API}/auth/me", headers=auth).json()["email"] == "ali@test.tn"


def test_register_cannot_choose_role(client):
    r = client.post(
        f"{API}/auth/register",
        json={"email": "pirate@test.tn", "password": "motdepasse1", "full_name": "Pirate", "role": "admin"},
    )
    assert r.status_code == 201 and r.json()["role"] == "candidate"


def test_duplicate_email_is_409(client):
    register(client, "x@test.tn")
    r = client.post(f"{API}/auth/register", json={"email": "X@test.tn", "password": "motdepasse1", "full_name": "X Y"})
    assert r.status_code == 409 and r.json()["code"] == "EMAIL_ALREADY_USED"


def test_bad_password_is_401(client):
    r = client.post(f"{API}/auth/login", data={"username": ADMIN[0], "password": "faux"})
    assert r.status_code == 401 and r.json()["code"] == "INVALID_CREDENTIALS"


def test_jwt_contains_sub_and_role(client):
    from app.core.security import decode_token

    token = login(client, *ADMIN)["Authorization"].split()[1]
    payload = decode_token(token)
    assert payload["role"] == "admin" and payload["sub"] and payload["exp"]


def test_invalid_token_is_401(client):
    r = client.get(f"{API}/auth/me", headers={"Authorization": "Bearer abc.def.ghi"})
    assert r.status_code == 401 and r.json()["code"] == "INVALID_TOKEN"


# --- rôles ---
def test_role_change_reserved_to_admin(client):
    user = register(client, "r@test.tn")
    cand = login(client, "r@test.tn", "motdepasse1")
    r = client.patch(f"{API}/users/{user['id']}/role", json={"role": "admin"}, headers=cand)
    assert r.status_code == 403 and r.json()["code"] == "FORBIDDEN"
    admin = login(client, *ADMIN)
    r = client.patch(f"{API}/users/{user['id']}/role", json={"role": "academic_iit"}, headers=admin)
    assert r.status_code == 200 and r.json()["role"] == "academic_iit"
    r = client.patch(f"{API}/users/00000000-0000-0000-0000-000000000000/role", json={"role": "admin"}, headers=admin)
    assert r.status_code == 404


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/auth/me"),
        ("patch", "/users/00000000-0000-0000-0000-000000000000/role"),
        ("post", "/programs"),
        ("put", "/programs/IIT-LIC-INFO"),
        ("get", "/admin/catalog/sources"),
        ("post", "/admin/catalog/sync"),
        ("get", "/admin/catalog/sync-runs"),
    ],
)
def test_anonymous_visitor_cannot_access_protected_routes(client, session_id, method, path):
    r = getattr(client, method)(f"{API}{path}", headers={"X-Session-Id": session_id}, **(
        {"json": {}} if method in ("post", "put", "patch") else {}
    ))
    assert r.status_code == 401


def test_password_longer_than_bcrypt_limit_is_rejected(client):
    r = client.post(f"{API}/auth/register", json={"email": "long@test.tn", "password": "a" * 73, "full_name": "Long"})
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"
