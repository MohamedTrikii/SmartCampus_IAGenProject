"""Modèle relationnel des processus métier (SA-11, suite).

Couvre les processus définis par l'équipe :
  - Préinscription (dossier de candidature + orientation validée par un humain + consentement)
  - Demande d'équivalence
  - Pièces justificatives
  - QCM personnalisé
  - Disponibilités, rendez-vous et entretien
  - Notifications / relances (suivi agentique)
  - Profil candidat (construit par la conversation)
  - Historique des statuts (traçabilité + tunnel de conversion du dashboard direction)
"""
import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base, Program, User, utcnow


# ---------------------------------------------------------------- statuts
class ApplicationStatus(str, enum.Enum):
    """Cycle de vie unique du dossier de candidature (préinscription → inscription)."""

    brouillon = "brouillon"
    soumise = "soumise"
    en_traitement = "en_traitement"
    complement_demande = "complement_demande"
    en_attente_qcm = "en_attente_qcm"
    qcm_termine = "qcm_termine"
    prete_entretien = "prete_entretien"
    entretien_planifie = "entretien_planifie"
    acceptee = "acceptee"
    refusee = "refusee"
    inscrit = "inscrit"
    abandonnee = "abandonnee"


class EquivalenceStatus(str, enum.Enum):
    brouillon = "brouillon"
    soumise = "soumise"
    en_traitement = "en_traitement"
    complement_demande = "complement_demande"
    acceptee = "acceptee"
    refusee = "refusee"


class RecommendationStatus(str, enum.Enum):
    proposee = "proposee"  # générée par l'IA
    validee = "validee"  # confirmée par le responsable académique
    ajustee = "ajustee"  # modifiée par le responsable académique


class QuizStatus(str, enum.Enum):
    genere = "genere"
    en_cours = "en_cours"
    termine = "termine"
    expire = "expire"


class AppointmentStatus(str, enum.Enum):
    en_attente = "en_attente"
    confirme = "confirme"
    reporte = "reporte"
    annule = "annule"
    termine = "termine"


class InterviewResult(str, enum.Enum):
    favorable = "favorable"
    defavorable = "defavorable"
    complement_demande = "complement_demande"
    transmis = "transmis"  # dossier transmis à l'étape suivante


class NotificationStatus(str, enum.Enum):
    a_envoyer = "a_envoyer"
    envoyee = "envoyee"
    echec = "echec"


class NotificationType(str, enum.Enum):
    confirmation = "confirmation"
    complement = "complement"
    decision = "decision"
    rappel_rdv = "rappel_rdv"
    relance = "relance"
    escalade = "escalade"


# ---------------------------------------------------------------- profil
class CandidateProfile(Base):
    """Profil construit progressivement par l'agent conversationnel, puis complété par le candidat."""

    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    birth_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    city: Mapped[str | None] = mapped_column(String(100))
    current_level: Mapped[str | None] = mapped_column(String(50))  # terminale, bac, licence...
    bac_section: Mapped[str | None] = mapped_column(String(100))
    bac_year: Mapped[int | None] = mapped_column(Integer)
    bac_average: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    favorite_subjects: Mapped[list[str]] = mapped_column(JSON, default=list)
    interests: Mapped[list[str]] = mapped_column(JSON, default=list)
    career_goal: Mapped[str | None] = mapped_column(Text)
    constraints: Mapped[str | None] = mapped_column(Text)  # budget, ville, rythme...
    preferred_language: Mapped[str | None] = mapped_column(String(10))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship()


# ---------------------------------------------------------------- préinscription
class Application(Base):
    """Demande de préinscription = dossier de candidature."""

    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # PRE-2026-000123
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    program_id: Mapped[int | None] = mapped_column(ForeignKey("programs.id"), index=True)  # choix du candidat
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"))
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, name="application_status"), default=ApplicationStatus.brouillon, index=True
    )
    # consentement RGPD / données personnelles (exigé par le sujet)
    consent_given_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_text_version: Mapped[str | None] = mapped_column(String(20))
    # suivi agentique
    last_candidate_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reminder_count: Mapped[int] = mapped_column(Integer, default=0)
    assigned_advisor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # après escalade
    reviewer_comment: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    candidate: Mapped[User] = relationship(foreign_keys=[candidate_id])
    program: Mapped[Program | None] = relationship()
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="application")
    quizzes: Mapped[list["Quiz"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="application")


class Recommendation(Base):
    """Formation recommandée par l'IA, avec justification, puis validée/ajustée par un humain."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id"))
    rank: Mapped[int] = mapped_column(Integer)  # 1 = meilleure correspondance
    compatibility_score: Mapped[int | None] = mapped_column(Integer)  # 0-100
    justification: Mapped[str] = mapped_column(Text)
    sources: Mapped[list[str]] = mapped_column(JSON, default=list)  # documents RAG cités
    status: Mapped[RecommendationStatus] = mapped_column(
        Enum(RecommendationStatus, name="recommendation_status"), default=RecommendationStatus.proposee
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    review_comment: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    application: Mapped[Application] = relationship(back_populates="recommendations")
    program: Mapped[Program] = relationship()


# ---------------------------------------------------------------- équivalence
class EquivalenceRequest(Base):
    __tablename__ = "equivalence_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # EQV-2026-000045
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    target_program_id: Mapped[int | None] = mapped_column(ForeignKey("programs.id"))
    previous_institution: Mapped[str] = mapped_column(String(200))
    previous_diploma: Mapped[str] = mapped_column(String(200))
    academic_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[EquivalenceStatus] = mapped_column(
        Enum(EquivalenceStatus, name="equivalence_status"), default=EquivalenceStatus.brouillon, index=True
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decision_comment: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    candidate: Mapped[User] = relationship(foreign_keys=[candidate_id])
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="equivalence_request")


# ---------------------------------------------------------------- pièces jointes
class Attachment(Base):
    """Pièce justificative rattachée à une préinscription OU à une demande d'équivalence."""

    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint(
            "(application_id IS NOT NULL) <> (equivalence_request_id IS NOT NULL)",
            name="ck_attachment_single_owner",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    equivalence_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("equivalence_requests.id", ondelete="CASCADE"), index=True
    )
    doc_type: Mapped[str] = mapped_column(String(50))  # releve_notes, diplome, cin, photo...
    original_name: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    application: Mapped[Application | None] = relationship(back_populates="attachments")
    equivalence_request: Mapped[EquivalenceRequest | None] = relationship(back_populates="attachments")


# ---------------------------------------------------------------- QCM
class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    status: Mapped[QuizStatus] = mapped_column(Enum(QuizStatus, name="quiz_status"), default=QuizStatus.genere)
    # [{"id","dimension":"connaissances|motivation|accompagnement","question","options":[...],"answer_index"}]
    questions: Mapped[list[dict]] = mapped_column(JSON, default=list)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)  # {question_id: option_index}
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    max_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    summary_for_interviewer: Mapped[str | None] = mapped_column(Text)  # synthèse générée par l'IA
    generated_by_model: Mapped[str | None] = mapped_column(String(100))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    application: Mapped[Application] = relationship(back_populates="quizzes")


# ---------------------------------------------------------------- rendez-vous & entretien
class AvailabilitySlot(Base):
    """Créneau proposé par un responsable d'entretien."""

    __tablename__ = "availability_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    interviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(200))  # salle ou lien visio
    is_booked: Mapped[bool] = mapped_column(Boolean, default=False)


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    slot_id: Mapped[int | None] = mapped_column(ForeignKey("availability_slots.id"))
    interviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, name="appointment_status"), default=AppointmentStatus.en_attente, index=True
    )
    reschedule_count: Mapped[int] = mapped_column(Integer, default=0)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    application: Mapped[Application] = relationship(back_populates="appointments")
    interview: Mapped["Interview | None"] = relationship(back_populates="appointment", uselist=False)


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    appointment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointments.id"), unique=True)
    interviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    knowledge_score: Mapped[int | None] = mapped_column(Integer)  # 0-20
    motivation_score: Mapped[int | None] = mapped_column(Integer)  # 0-20
    observations: Mapped[str | None] = mapped_column(Text)
    result: Mapped[InterviewResult | None] = mapped_column(Enum(InterviewResult, name="interview_result"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    appointment: Mapped[Appointment] = relationship(back_populates="interview")


# ---------------------------------------------------------------- notifications & traçabilité
class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"))
    type: Mapped[NotificationType] = mapped_column(Enum(NotificationType, name="notification_type"))
    channel: Mapped[str] = mapped_column(String(20), default="email")  # email | in_app
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    generated_by_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status"), default=NotificationStatus.a_envoyer
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StatusHistory(Base):
    """Chaque changement de statut (dossier, équivalence, RDV) — audit et statistiques."""

    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(30), index=True)  # application | equivalence | appointment
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    old_status: Mapped[str | None] = mapped_column(String(30))
    new_status: Mapped[str] = mapped_column(String(30))
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # None = système / agent IA
    actor_label: Mapped[str] = mapped_column(String(30), default="system")  # candidat, responsable, agent_ia...
    comment: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
