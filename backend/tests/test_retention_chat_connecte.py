"""SA-24 / SA-27 : rétention temporaire des visiteurs, chat connecté (JWT), séparation des historiques."""
import uuid
from datetime import datetime, timedelta, timezone

from app.db.models import Conversation, Message, VisitorSession
from scripts.purge_sessions import purge_expired_sessions
from scripts.scheduler import run_forever
from tests.conftest import login, register

API = "/api/v1"


def chat(client, headers, text="bonjour", conversation_id=None):
    body = {"message": text, **({"conversation_id": conversation_id} if conversation_id else {})}
    r = client.post(f"{API}/chat/messages", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["conversation_id"]


def new_session(client):
    return client.post(f"{API}/sessions").json()["session_id"]


def expire(db, session_id):
    db.get(VisitorSession, uuid.UUID(session_id)).expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()


# ---------------------------------------------------------------- rétention
def test_purge_removes_expired_anonymous_sessions_with_history(client, db):
    old = new_session(client)
    chat(client, {"X-Session-Id": old})
    fresh = new_session(client)
    chat(client, {"X-Session-Id": fresh})
    expire(db, old)

    report = purge_expired_sessions(db)
    assert (report.sessions, report.conversations, report.messages) == (1, 1, 2)
    db.expire_all()
    assert db.get(VisitorSession, uuid.UUID(old)) is None
    assert db.get(VisitorSession, uuid.UUID(fresh)) is not None
    assert db.query(Conversation).count() == 1 and db.query(Message).count() == 2


def test_purge_never_touches_sessions_linked_to_an_account(client, db):
    sid = new_session(client)
    chat(client, {"X-Session-Id": sid})
    register(client, "garde@test.tn", headers={"X-Session-Id": sid})
    expire(db, sid)
    assert purge_expired_sessions(db).sessions == 0
    assert db.query(Message).count() == 2


def test_purge_dry_run_deletes_nothing(client, db):
    sid = new_session(client)
    chat(client, {"X-Session-Id": sid})
    expire(db, sid)
    report = purge_expired_sessions(db, dry_run=True)
    assert report.sessions == 1 and "seraient supprimés" in str(report)
    db.rollback()
    assert db.query(Message).count() == 2


def test_scheduler_survives_job_errors():
    calls = []
    clock = iter(range(0, 10_000, 100))

    def failing():
        calls.append("purge")
        raise RuntimeError("base indisponible")

    run_forever([("purge", 0, failing)], sleep=lambda s: None, clock=lambda: next(clock), max_ticks=3)
    assert calls == ["purge", "purge", "purge"]


# ---------------------------------------------------------------- chat connecté
def test_candidate_finds_history_on_new_device(client):
    laptop = {"X-Session-Id": new_session(client)}
    conv = chat(client, laptop, "je veux faire informatique")
    register(client, "sara@test.tn", headers=laptop)
    auth = login(client, "sara@test.tn", "motdepasse1")

    phone = {"X-Session-Id": new_session(client), **auth}  # nouvel appareil
    ids = [c["id"] for c in client.get(f"{API}/chat/conversations", headers=phone).json()]
    assert conv in ids
    msgs = client.get(f"{API}/chat/conversations/{conv}/messages", headers=auth).json()  # JWT seul suffit
    assert msgs[0]["content"] == "je veux faire informatique"
    chat(client, phone, "et la prépa ?", conversation_id=conv)  # il continue la même conversation


def test_jwt_links_unlinked_session(client, db):
    register(client, "karim@test.tn")
    auth = login(client, "karim@test.tn", "motdepasse1")
    sid = new_session(client)
    conv = chat(client, {"X-Session-Id": sid})  # anonyme d'abord
    client.get(f"{API}/chat/conversations", headers={"X-Session-Id": sid, **auth})  # puis connecté
    db.expire_all()
    session = db.get(VisitorSession, uuid.UUID(sid))
    assert session.user_id is not None
    db.rollback()  # libère la connexion SQLite partagée
    assert conv in [c["id"] for c in client.get(f"{API}/chat/conversations", headers=auth).json()]


def test_jwt_without_session_creates_linked_session(client, db):
    register(client, "nour@test.tn")
    auth = login(client, "nour@test.tn", "motdepasse1")
    conv = chat(client, auth, "salut")
    owner = db.get(Conversation, uuid.UUID(conv)).session.user_id
    assert owner is not None


# ---------------------------------------------------------------- séparation
def test_anonymous_never_sees_account_conversations(client):
    sid = new_session(client)
    h = {"X-Session-Id": sid}
    conv = chat(client, h)
    register(client, "lina@test.tn", headers=h)
    # la session est maintenant rattachée : sans JWT, plus aucun accès (ex. poste partagé après déconnexion)
    r = client.get(f"{API}/chat/conversations", headers=h)
    assert r.status_code == 401 and r.json()["code"] == "LOGIN_REQUIRED"
    assert client.get(f"{API}/chat/conversations/{conv}/messages", headers=h).status_code == 401
    # un autre visiteur anonyme ne voit rien non plus
    other = {"X-Session-Id": new_session(client)}
    assert client.get(f"{API}/chat/conversations", headers=other).json() == []
    assert client.get(f"{API}/chat/conversations/{conv}/messages", headers=other).status_code == 404


def test_accounts_are_separated(client):
    a = {"X-Session-Id": new_session(client)}
    conv_a = chat(client, a)
    register(client, "a@test.tn", headers=a)
    register(client, "b@test.tn")
    auth_b = login(client, "b@test.tn", "motdepasse1")
    assert client.get(f"{API}/chat/conversations", headers=auth_b).json() == []
    assert client.get(f"{API}/chat/conversations/{conv_a}/messages", headers=auth_b).status_code == 404
    # B ne peut pas s'approprier la session de A
    r = client.get(f"{API}/chat/conversations", headers={**a, **auth_b})
    assert r.status_code == 403
