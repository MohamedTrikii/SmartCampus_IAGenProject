import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["LLM_PROVIDER"] = "fake"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.models import Base  # noqa: E402
import app.db.models_workflow  # noqa: E402,F401
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from pathlib import Path  # noqa: E402

from scripts.seed import seed  # noqa: E402

TEST_CATALOGUE = Path(__file__).parent / "fixtures" / "catalogue_test.json"

engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)


# pysqlite ne gère pas correctement BEGIN/SAVEPOINT par défaut : correctif officiel SQLAlchemy
# (https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#serializable-isolation-savepoints-transactional-ddl)
@event.listens_for(engine, "connect")
def _sqlite_connect(dbapi_connection, _record):
    dbapi_connection.isolation_level = None


@event.listens_for(engine, "begin")
def _sqlite_begin(conn):
    conn.exec_driver_sql("BEGIN")
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client():
    Base.metadata.create_all(engine)
    with TestingSession() as db:
        seed(db, TEST_CATALOGUE)

    def override():
        with TestingSession() as db:
            yield db

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def session_id(client):
    return client.post("/api/v1/sessions").json()["session_id"]


ADMIN = ("admin@smartcampus.local", "Admin123!")  # compte de démo créé par scripts/seed.py


def register(client, email, password="motdepasse1", full_name="Utilisateur Test", headers=None):
    r = client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": full_name},
                    headers=headers or {})
    assert r.status_code == 201, r.text
    return r.json()


def user_with_role(client, email, role):
    """Crée un compte puis lui donne un rôle via l'API admin ; renvoie l'en-tête Authorization."""
    user = register(client, email)
    r = client.patch(f"/api/v1/users/{user['id']}/role", json={"role": role}, headers=login(client, *ADMIN))
    assert r.status_code == 200, r.text
    return login(client, email, "motdepasse1")


def login(client, email, password):
    r = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def db(client):  # `client` crée le schéma et les données de référence
    with TestingSession() as session:
        yield session


# --- fixtures des workflows métier (tests/test_workflow.py) ---
@pytest.fixture()
def candidate(db):
    from app.core.security import hash_password
    from app.db.models import User, UserRole

    user = User(email="candidat@test.tn", password_hash=hash_password("motdepasse1"),
                full_name="Candidat Test", role=UserRole.candidate)
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def application(db, candidate):
    from sqlalchemy import select

    from app.db.models import Program
    from app.db.models_workflow import Application
    from app.domain.workflow import make_reference

    program = db.scalar(select(Program).where(Program.code == "IIT-LIC-INFO"))
    app_ = Application(reference=make_reference("PRE", 1, 2026), candidate_id=candidate.id, program_id=program.id)
    db.add(app_)
    db.flush()
    return app_


@pytest.fixture()
def equivalence(db, candidate):
    from app.db.models_workflow import EquivalenceRequest
    from app.domain.workflow import make_reference

    req = EquivalenceRequest(reference=make_reference("EQV", 1, 2026), candidate_id=candidate.id,
                             previous_institution="Université X", previous_diploma="Licence")
    db.add(req)
    db.flush()
    return req
