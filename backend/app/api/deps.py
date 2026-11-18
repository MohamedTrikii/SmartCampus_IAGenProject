"""Dépendances communes : utilisateur courant, contrôle des rôles, session visiteur."""
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Header, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import decode_token
from app.db.models import User, UserRole, VisitorSession
from app.db.session import get_db

DbDep = Annotated[Session, Depends(get_db)]
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def as_aware(dt: datetime) -> datetime:
    """SQLite renvoie des dates naïves : on les considère en UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def get_optional_user(db: DbDep, token: Annotated[str | None, Depends(oauth2_scheme)]) -> User | None:
    if not token:
        return None
    try:
        payload = decode_token(token)
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (JWTError, KeyError, ValueError):
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "Jeton invalide ou expiré", "INVALID_TOKEN",
                       headers={"WWW-Authenticate": "Bearer"})
    if user is None or not user.is_active:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "Utilisateur introuvable ou désactivé", "INVALID_TOKEN",
                       headers={"WWW-Authenticate": "Bearer"})
    return user


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def get_current_user(user: OptionalUser) -> User:
    if user is None:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "Authentification requise", "NOT_AUTHENTICATED",
                       headers={"WWW-Authenticate": "Bearer"})
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole):
    def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise ApiError(status.HTTP_403_FORBIDDEN, "Droits insuffisants pour cette action", "FORBIDDEN")
        return user

    return checker


def get_visitor_session(
    db: DbDep, x_session_id: Annotated[str | None, Header()] = None
) -> VisitorSession | None:
    """Session visiteur facultative (en-tête X-Session-Id) : 400 si invalide, 401 si inconnue ou expirée."""
    if not x_session_id:
        return None
    try:
        sid = uuid.UUID(x_session_id)
    except ValueError:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "X-Session-Id invalide", "SESSION_ID_INVALID")
    session = db.get(VisitorSession, sid)
    if session is None or as_aware(session.expires_at) < datetime.now(timezone.utc):
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "Session visiteur expirée, créez-en une nouvelle",
                       "SESSION_EXPIRED")
    session.last_seen_at = datetime.now(timezone.utc)
    return session


OptionalVisitor = Annotated[VisitorSession | None, Depends(get_visitor_session)]
