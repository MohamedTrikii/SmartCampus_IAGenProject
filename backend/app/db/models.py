"""Modèle relationnel métier — Sprint 1 (SA-11).

Source de vérité pour : utilisateurs & rôles, sessions visiteurs, établissements, formations,
conditions d'accès, frais, conversations, messages et documents officiels (corpus RAG).
Les tables préinscription / QCM / rendez-vous seront ajoutées par migration aux sprints suivants.
"""
import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Noms de contraintes déterministes : indispensables pour que les migrations (et leur downgrade)
# puissent supprimer une contrainte par son nom, identique sur PostgreSQL et SQLite.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UserRole(str, enum.Enum):
    candidate = "candidate"
    academic_iit = "academic_iit"
    academic_isb = "academic_isb"
    interviewer = "interviewer"
    direction = "direction"
    admin = "admin"


class ProgramLevel(str, enum.Enum):
    licence = "licence"
    prepa = "prepa"
    ingenieur = "ingenieur"
    master = "master"
    autre = "autre"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(30))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), default=UserRole.candidate)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sessions: Mapped[list["VisitorSession"]] = relationship(back_populates="user")


class VisitorSession(Base):
    """Session d'un visiteur sans compte. Rattachée à un utilisateur s'il crée un compte plus tard."""

    __tablename__ = "visitor_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    preferred_language: Mapped[str | None] = mapped_column(String(10))  # fr | tn | arabizi | ar
    user_agent: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User | None] = relationship(back_populates="sessions")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="session")


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)  # IIT, ISB
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(String(255))

    programs: Mapped[list["Program"]] = relationship(back_populates="institution")


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"), index=True)
    level: Mapped[ProgramLevel] = mapped_column(Enum(ProgramLevel, name="program_level"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    specialization: Mapped[str | None] = mapped_column(String(200))
    duration_years: Mapped[int | None] = mapped_column(Integer)  # None = non précisée par la source
    language: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    career_outcomes: Mapped[list[str]] = mapped_column(JSON, default=list)
    bridges: Mapped[list[str]] = mapped_column(JSON, default=list)  # passerelles vers d'autres formations
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source_url: Mapped[str | None] = mapped_column(String(500))  # traçabilité de l'information officielle
    # "scraped" = mis à jour automatiquement depuis le site ; "manual" = verrouillé, la synchro ne l'écrase pas
    data_source: Mapped[str] = mapped_column(String(20), default="manual", server_default="manual")
    page_hash: Mapped[str | None] = mapped_column(String(64))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    institution: Mapped[Institution] = relationship(back_populates="programs")
    requirements: Mapped[list["AdmissionRequirement"]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )
    fees: Mapped[list["ProgramFee"]] = relationship(back_populates="program", cascade="all, delete-orphan")


class AdmissionRequirement(Base):
    __tablename__ = "admission_requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), index=True)
    bac_sections: Mapped[list[str]] = mapped_column(JSON, default=list)  # ex. ["Mathématiques", "Informatique"]
    min_average: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    required_diploma: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)

    program: Mapped[Program] = relationship(back_populates="requirements")


class ProgramFee(Base):
    __tablename__ = "program_fees"
    __table_args__ = (
        UniqueConstraint("program_id", "academic_year", "fee_type", name="uq_program_fees_program_year_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), index=True)
    academic_year: Mapped[str] = mapped_column(String(9))  # 2026-2027
    fee_type: Mapped[str] = mapped_column(String(50))  # inscription, scolarite_annuelle...
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="TND")
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)  # False = valeur de test

    program: Mapped[Program] = relationship(back_populates="fees")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("visitor_sessions.id", ondelete="CASCADE"), index=True)
    title: Mapped[str | None] = mapped_column(String(200))
    detected_language: Mapped[str | None] = mapped_column(String(10))
    # mémoire structurée (profil en construction) remplie par l'agent aux sprints suivants
    memory: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    session: Mapped[VisitorSession] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole, name="message_role"))
    content: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(10))
    input_mode: Mapped[str] = mapped_column(String(10), default="text")  # text | audio
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class OfficialDocument(Base):
    """Document officiel IIT/ISB (brochure, règlement, FAQ) — alimente le corpus RAG."""

    __tablename__ = "official_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institutions.id"))
    title: Mapped[str] = mapped_column(String(300))
    doc_type: Mapped[str] = mapped_column(String(50))  # brochure, reglement, faq, procedure
    source_url: Mapped[str | None] = mapped_column(String(500), unique=True)
    file_path: Mapped[str | None] = mapped_column(String(500))
    content_text: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    http_status: Mapped[int | None] = mapped_column(Integer)
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False)  # validé par un responsable
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CatalogSyncRun(Base):
    """Une exécution de la synchronisation automatique du catalogue depuis les sites officiels."""

    __tablename__ = "catalog_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger: Mapped[str] = mapped_column(String(20))  # cli | schedule | api
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | success | partial | failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    changes: Mapped[list[dict]] = mapped_column(JSON, default=list)
    errors: Mapped[list[str]] = mapped_column(JSON, default=list)
