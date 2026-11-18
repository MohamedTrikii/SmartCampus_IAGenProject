"""Règles de transition des statuts — une seule source de vérité pour l'API, les agents IA et les tests.

Chaque transition déclare QUI a le droit de la faire. Les agents IA passent par `change_status` comme
n'importe quel acteur : ils ne peuvent jamais prendre une décision réservée à un humain
(acceptation, refus, validation d'équivalence).
"""
import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy.orm import Session

from app.db.models_workflow import (
    Application,
    ApplicationStatus as A,
    Appointment,
    AppointmentStatus as R,
    EquivalenceRequest,
    EquivalenceStatus as E,
    StatusHistory,
)

# Acteurs logiques (le rôle technique de l'utilisateur est vérifié par l'API avant l'appel)
CANDIDAT = "candidat"
RESPONSABLE = "responsable"  # académique IIT/ISB ou admissions
RESP_ENTRETIEN = "resp_entretien"
SYSTEME = "systeme"  # tâches planifiées (rappels, expiration)
AGENT_IA = "agent_ia"  # orchestrateur LangGraph

HUMAINS_DECISION = {RESPONSABLE, RESP_ENTRETIEN}

# ---------------------------------------------------------------- préinscription
APPLICATION_TRANSITIONS: dict[A, dict[A, set[str]]] = {
    A.brouillon: {A.soumise: {CANDIDAT}, A.abandonnee: {CANDIDAT, SYSTEME}},
    A.soumise: {A.en_traitement: {RESPONSABLE}, A.abandonnee: {CANDIDAT}},
    A.en_traitement: {
        A.complement_demande: {RESPONSABLE},
        A.en_attente_qcm: {RESPONSABLE},  # dossier conforme → génération du QCM
        A.refusee: {RESPONSABLE},
    },
    A.complement_demande: {A.soumise: {CANDIDAT}, A.abandonnee: {CANDIDAT, SYSTEME}},
    A.en_attente_qcm: {A.qcm_termine: {CANDIDAT, SYSTEME}, A.abandonnee: {SYSTEME}},
    A.qcm_termine: {A.prete_entretien: {SYSTEME, AGENT_IA}},  # synthèse générée
    A.prete_entretien: {A.entretien_planifie: {CANDIDAT, RESP_ENTRETIEN, AGENT_IA}, A.abandonnee: {SYSTEME}},
    A.entretien_planifie: {
        A.prete_entretien: {CANDIDAT, RESP_ENTRETIEN, SYSTEME},  # RDV annulé → à replanifier
        A.acceptee: {RESP_ENTRETIEN},
        A.refusee: {RESP_ENTRETIEN},
        A.complement_demande: {RESP_ENTRETIEN},
    },
    A.acceptee: {A.inscrit: {RESPONSABLE}, A.abandonnee: {CANDIDAT}},
    A.refusee: {},
    A.inscrit: {},
    A.abandonnee: {},
}

# ---------------------------------------------------------------- équivalence
EQUIVALENCE_TRANSITIONS: dict[E, dict[E, set[str]]] = {
    E.brouillon: {E.soumise: {CANDIDAT}},
    E.soumise: {E.en_traitement: {RESPONSABLE}},
    E.en_traitement: {E.complement_demande: {RESPONSABLE}, E.acceptee: {RESPONSABLE}, E.refusee: {RESPONSABLE}},
    E.complement_demande: {E.soumise: {CANDIDAT}},
    E.acceptee: {},
    E.refusee: {},
}

# ---------------------------------------------------------------- rendez-vous
APPOINTMENT_TRANSITIONS: dict[R, dict[R, set[str]]] = {
    R.en_attente: {R.confirme: {RESP_ENTRETIEN}, R.reporte: {RESP_ENTRETIEN}, R.annule: {CANDIDAT, RESP_ENTRETIEN}},
    R.confirme: {R.reporte: {CANDIDAT, RESP_ENTRETIEN}, R.annule: {CANDIDAT, RESP_ENTRETIEN}, R.termine: {RESP_ENTRETIEN}},
    R.reporte: {R.confirme: {RESP_ENTRETIEN}, R.annule: {CANDIDAT, RESP_ENTRETIEN}},
    R.annule: {},
    R.termine: {},
}

MAX_RESCHEDULES = 2  # règle métier : au-delà, le report est refusé

FINAL_APPLICATION_STATUSES = {A.refusee, A.inscrit, A.abandonnee}


class TransitionError(Exception):
    pass


def allowed_targets(entity, actor: str) -> list[str]:
    """Statuts atteignables par cet acteur — utile pour afficher les boutons du frontend."""
    table, current = _table_for(entity), entity.status
    return [s.value for s, actors in table[current].items() if actor in actors]


def _table_for(entity) -> dict:
    if isinstance(entity, Application):
        return APPLICATION_TRANSITIONS
    if isinstance(entity, EquivalenceRequest):
        return EQUIVALENCE_TRANSITIONS
    if isinstance(entity, Appointment):
        return APPOINTMENT_TRANSITIONS
    raise TypeError(f"Pas de workflow pour {type(entity).__name__}")


def _entity_type(entity) -> str:
    return {Application: "application", EquivalenceRequest: "equivalence", Appointment: "appointment"}[type(entity)]


def change_status(
    db: Session,
    entity,
    new_status: Enum,
    actor: str,
    user_id: uuid.UUID | None = None,
    comment: str | None = None,
) -> StatusHistory:
    """Applique une transition si elle est autorisée et l'historise. Ne fait pas de commit."""
    table = _table_for(entity)
    current = entity.status
    authorized = table[current].get(new_status)
    if authorized is None:
        raise TransitionError(f"Transition interdite : {current.value} → {new_status.value}")
    if actor not in authorized:
        raise TransitionError(f"L'acteur '{actor}' ne peut pas passer de {current.value} à {new_status.value}")

    now = datetime.now(timezone.utc)
    if isinstance(entity, Appointment) and new_status == R.reporte:
        if entity.reschedule_count >= MAX_RESCHEDULES:
            raise TransitionError(f"Nombre maximal de reports atteint ({MAX_RESCHEDULES})")
        entity.reschedule_count += 1
    if isinstance(entity, Application):
        if new_status == A.soumise:
            if entity.consent_given_at is None:
                raise TransitionError("Le consentement du candidat est obligatoire avant la soumission")
            if entity.program_id is None:
                raise TransitionError("Une formation doit être choisie avant la soumission")
            entity.submitted_at = now
        if actor == CANDIDAT:
            entity.last_candidate_activity_at = now
            entity.reminder_count = 0
    if isinstance(entity, EquivalenceRequest):
        if new_status == E.soumise:
            entity.submitted_at = now
        if new_status in (E.acceptee, E.refusee):
            entity.decided_at = now
            entity.reviewer_id = user_id

    history = StatusHistory(
        entity_type=_entity_type(entity),
        entity_id=str(entity.id),
        old_status=current.value,
        new_status=new_status.value,
        changed_by_id=user_id,
        actor_label=actor,
        comment=comment,
    )
    entity.status = new_status
    db.add(history)
    return history


def make_reference(prefix: str, sequence: int, year: int | None = None) -> str:
    """PRE-2026-000123 / EQV-2026-000045."""
    return f"{prefix}-{year or datetime.now(timezone.utc).year}-{sequence:06d}"
