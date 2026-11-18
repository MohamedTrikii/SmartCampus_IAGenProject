"""Conversation multi-tours avec mémoire (SA-35), accessible sans compte (SA-24) ou connecté (SA-27).

- Mémoire courte : les N derniers messages (CHAT_HISTORY_WINDOW) sont renvoyés au LLM à chaque tour.
- Mémoire longue : `conversations.memory` (profil structuré) sera remplie par l'agent au sprint suivant.
- Contexte officiel : en attendant le RAG, les formations actives (et leurs frais officiels) sont injectées.

Qui voit quoi :
- visiteur anonyme (X-Session-Id non rattaché)  → uniquement les conversations de SA session ;
- utilisateur connecté (JWT)                    → toutes les conversations de toutes ses sessions ;
- JWT + X-Session-Id non rattaché               → la session est rattachée au compte ;
- session rattachée à un compte SANS son JWT    → 401 (après déconnexion, le poste ne montre plus l'historique).
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbDep, OptionalUser, OptionalVisitor
from app.api.routes_auth import new_visitor_session
from app.api.schemas import ChatIn, ChatOut, ConversationOut, MessageOut
from app.core.config import settings
from app.core.errors import ApiError
from app.db.models import Conversation, Message, MessageRole, Program, User, VisitorSession
from app.llm.client import SYSTEM_PROMPT, LLMClient, LLMUnavailable, get_llm
from app.llm.language import detect_language

router = APIRouter(prefix="/chat", tags=["chat"])

LANG_HINT = {
    "fr": "Le candidat écrit en français : réponds en français.",
    "ar": "Le candidat écrit en arabe : réponds en arabe.",
    "tn": "Le candidat écrit en dialecte tunisien (lettres arabes) : réponds en tunisien.",
    "arabizi": "Le candidat écrit en Arabizi tunisien (lettres latines + chiffres 3, 7, 9, 5) : réponds en Arabizi.",
}


@dataclass
class ChatIdentity:
    """Qui parle : une session (facultative si JWT) et/ou un utilisateur connecté."""

    session: VisitorSession | None
    user: User | None

    @property
    def owner_id(self) -> uuid.UUID | None:
        return self.user.id if self.user else None


def get_identity(db: DbDep, session: OptionalVisitor, user: OptionalUser) -> ChatIdentity:
    if session is None and user is None:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "En-tête X-Session-Id manquant (POST /sessions) ou connexion requise",
                       "SESSION_ID_MISSING")
    if session is not None and session.user_id is not None:
        if user is None:
            raise ApiError(status.HTTP_401_UNAUTHORIZED, "Cette session appartient à un compte : connectez-vous",
                           "LOGIN_REQUIRED", headers={"WWW-Authenticate": "Bearer"})
        if session.user_id != user.id:
            raise ApiError(status.HTTP_403_FORBIDDEN, "Cette session appartient à un autre compte", "FORBIDDEN")
    if session is not None and user is not None and session.user_id is None:
        session.user_id = user.id  # connexion sur cet appareil : l'historique anonyme rejoint le compte
        db.flush()
    return ChatIdentity(session, user)


IdentityDep = Annotated[ChatIdentity, Depends(get_identity)]


def _visible(identity: ChatIdentity):
    """Filtre SQL des conversations visibles par cette identité."""
    if identity.owner_id is not None:
        account_sessions = select(VisitorSession.id).where(VisitorSession.user_id == identity.owner_id)
        return Conversation.session_id.in_(account_sessions)
    return Conversation.session_id == identity.session.id


def _get_conversation(db, identity: ChatIdentity, conversation_id: uuid.UUID) -> Conversation:
    conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id, _visible(identity)))
    if conversation is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "Conversation introuvable", "CONVERSATION_NOT_FOUND")
    return conversation


def official_context(db) -> str:
    """Formations actives telles qu'enregistrées (synchronisées depuis les sites) — rien d'autre."""
    programs = db.scalars(
        select(Program)
        .where(Program.is_active.is_(True))
        .options(selectinload(Program.institution), selectinload(Program.fees))
        .order_by(Program.code)
    ).all()
    if not programs:
        return "CONTEXTE OFFICIEL : aucune formation chargée. Ne cite aucune formation précise."
    lines = []
    for p in programs:
        line = f"- [{p.institution.code}] {p.name} ({p.level.value}"
        if p.duration_years:  # la durée n'est donnée que si la source l'indique
            line += f", {p.duration_years} ans"
        line += ")"
        fees = [f for f in p.fees if f.is_official]
        if fees:
            line += " — frais indicatifs : " + ", ".join(
                f"{f.fee_type} {f.amount.normalize():f} {f.currency} ({f.academic_year})" for f in fees
            )
        if p.source_url:
            line += f" — source : {p.source_url}"
        lines.append(line)
    return "CONTEXTE OFFICIEL (formations disponibles) :\n" + "\n".join(lines)


@router.post("/messages", response_model=ChatOut)
def send_message(
    payload: ChatIn, db: DbDep, identity: IdentityDep, request: Request,
    llm: Annotated[LLMClient, Depends(get_llm)],
):
    if payload.conversation_id:
        conversation = _get_conversation(db, identity, payload.conversation_id)
    else:
        session = identity.session or new_visitor_session(db, request.headers.get("user-agent"), identity.owner_id)
        conversation = Conversation(session_id=session.id, title=payload.message[:80])
        db.add(conversation)
        db.flush()

    language = detect_language(payload.message)
    conversation.detected_language = language
    conversation.updated_at = datetime.now(timezone.utc)
    if identity.session is not None:
        identity.session.preferred_language = language

    history = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(settings.chat_history_window)
    ).all()[::-1]

    llm_messages = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n{official_context(db)}\n{LANG_HINT[language]}"},
        *({"role": m.role.value, "content": m.content} for m in history),
        {"role": "user", "content": payload.message},
    ]
    try:
        result = llm.chat(llm_messages)
    except LLMUnavailable as exc:
        db.rollback()
        raise ApiError(status.HTTP_503_SERVICE_UNAVAILABLE, f"LLM indisponible ({exc}), réessayez plus tard",
                       "LLM_UNAVAILABLE")

    db.add(Message(conversation_id=conversation.id, role=MessageRole.user, content=payload.message, language=language))
    db.flush()  # garantit l'ordre user < assistant
    db.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.assistant,
            content=result.content,
            language=language,
            model=result.model,
            latency_ms=result.latency_ms,
        )
    )
    db.commit()
    return ChatOut(conversation_id=conversation.id, reply=result.content, language=language)


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(db: DbDep, identity: IdentityDep):
    conversations = db.scalars(
        select(Conversation).where(_visible(identity)).order_by(Conversation.updated_at.desc())
    ).all()
    db.commit()  # enregistre last_seen_at et un éventuel rattachement de session
    return conversations


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(conversation_id: uuid.UUID, db: DbDep, identity: IdentityDep):
    conversation = _get_conversation(db, identity, conversation_id)
    messages = list(conversation.messages)
    db.commit()
    return messages
