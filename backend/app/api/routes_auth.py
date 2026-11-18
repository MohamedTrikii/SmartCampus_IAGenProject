"""Sessions visiteurs (SA-24) et authentification / rôles (SA-27)."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep, OptionalVisitor, require_roles
from app.api.schemas import RegisterIn, RoleUpdateIn, SessionOut, TokenOut, UserOut
from app.core.config import settings
from app.core.errors import ApiError
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User, UserRole, VisitorSession

router = APIRouter()


def new_visitor_session(db, user_agent: str | None = None, user_id: uuid.UUID | None = None) -> VisitorSession:
    session = VisitorSession(
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.visitor_session_days),
        user_agent=(user_agent or "")[:300],
        user_id=user_id,
    )
    db.add(session)
    db.flush()
    return session


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED, tags=["sessions"])
def create_session(db: DbDep, request: Request):
    """Crée une session pour un visiteur sans compte (aucune donnée personnelle collectée)."""
    session = new_visitor_session(db, request.headers.get("user-agent"))
    db.commit()
    return session


@router.get("/sessions/me", response_model=SessionOut, tags=["sessions"])
def read_session(db: DbDep, session: OptionalVisitor):
    if session is None:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "En-tête X-Session-Id manquant", "SESSION_ID_MISSING")
    db.commit()  # enregistre last_seen_at
    return session


@router.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED, tags=["auth"])
def register(payload: RegisterIn, db: DbDep, session: OptionalVisitor):
    """Crée un compte candidat. Si X-Session-Id est fourni, la session anonyme (et son historique) est rattachée."""
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise ApiError(status.HTTP_409_CONFLICT, "Un compte existe déjà avec cet email", "EMAIL_ALREADY_USED")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=UserRole.candidate,
    )
    db.add(user)
    db.flush()
    if session is not None and session.user_id is None:
        session.user_id = user.id
    db.commit()
    return user


@router.post("/auth/login", response_model=TokenOut, tags=["auth"])
def login(db: DbDep, form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """Formulaire OAuth2 : `username` = email. Compatible avec le bouton Authorize de Swagger."""
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if user is None or not verify_password(form.password, user.password_hash) or not user.is_active:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "Email ou mot de passe incorrect", "INVALID_CREDENTIALS")
    return TokenOut(access_token=create_access_token(str(user.id), user.role.value))


@router.get("/auth/me", response_model=UserOut, tags=["auth"])
def me(user: CurrentUser):
    return user


@router.patch(
    "/users/{user_id}/role",
    response_model=UserOut,
    tags=["auth"],
    dependencies=[Depends(require_roles(UserRole.admin))],
)
def update_role(user_id: uuid.UUID, payload: RoleUpdateIn, db: DbDep):
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable", "USER_NOT_FOUND")
    user.role = payload.role
    db.commit()
    return user
