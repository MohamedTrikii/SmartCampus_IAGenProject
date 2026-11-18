from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.models_workflow import (
    Application,
    ApplicationStatus as A,
    Appointment,
    AppointmentStatus as R,
    Attachment,
    EquivalenceRequest,
    EquivalenceStatus as E,
    StatusHistory,
)
from app.domain.workflow import (
    AGENT_IA,
    APPLICATION_TRANSITIONS,
    EQUIVALENCE_TRANSITIONS,
    CANDIDAT,
    RESP_ENTRETIEN,
    RESPONSABLE,
    SYSTEME,
    TransitionError,
    allowed_targets,
    change_status,
    make_reference,
)

def test_happy_path_preinscription_to_inscription(db, application):
    application.consent_given_at = datetime.now(timezone.utc)
    steps = [
        (A.soumise, CANDIDAT), (A.en_traitement, RESPONSABLE), (A.en_attente_qcm, RESPONSABLE),
        (A.qcm_termine, CANDIDAT), (A.prete_entretien, AGENT_IA), (A.entretien_planifie, CANDIDAT),
        (A.acceptee, RESP_ENTRETIEN), (A.inscrit, RESPONSABLE),
    ]
    for status, actor in steps:
        change_status(db, application, status, actor)
    db.commit()
    history = db.scalars(select(StatusHistory).order_by(StatusHistory.id)).all()
    assert [h.new_status for h in history] == [s.value for s, _ in steps]
    assert application.submitted_at is not None


def test_consent_required_before_submission(db, application):
    with pytest.raises(TransitionError, match="consentement"):
        change_status(db, application, A.soumise, CANDIDAT)


def test_ai_agent_cannot_take_official_decision(db, application):
    application.status = A.entretien_planifie
    with pytest.raises(TransitionError, match="agent_ia"):
        change_status(db, application, A.acceptee, AGENT_IA)


def test_no_decision_transition_open_to_ai_or_system():
    for targets in APPLICATION_TRANSITIONS.values():
        for status in (A.acceptee, A.refusee, A.inscrit):
            assert not targets.get(status, set()) & {AGENT_IA, SYSTEME}


def test_forbidden_jump(db, application):
    with pytest.raises(TransitionError, match="interdite"):
        change_status(db, application, A.acceptee, RESPONSABLE)


def test_candidate_activity_resets_reminders(db, application):
    application.consent_given_at = datetime.now(timezone.utc)
    application.reminder_count = 2
    change_status(db, application, A.soumise, CANDIDAT)
    assert application.reminder_count == 0


def test_equivalence_flow(db, application):
    req = EquivalenceRequest(
        reference="EQV-2026-000002", candidate_id=application.candidate_id,
        previous_institution="Université X", previous_diploma="Licence",
    )
    db.add(req)
    db.flush()
    for status, actor in [(E.soumise, CANDIDAT), (E.en_traitement, RESPONSABLE), (E.complement_demande, RESPONSABLE),
                          (E.soumise, CANDIDAT), (E.en_traitement, RESPONSABLE), (E.acceptee, RESPONSABLE)]:
        change_status(db, req, status, actor)
    assert req.decided_at is not None


def test_appointment_reschedule_limit(db, application):
    now = datetime.now(timezone.utc)
    appt = Appointment(application_id=application.id, interviewer_id=application.candidate_id,
                       starts_at=now, ends_at=now + timedelta(minutes=30))
    db.add(appt)
    db.flush()
    change_status(db, appt, R.confirme, RESP_ENTRETIEN)
    change_status(db, appt, R.reporte, CANDIDAT)
    change_status(db, appt, R.confirme, RESP_ENTRETIEN)
    change_status(db, appt, R.reporte, CANDIDAT)
    change_status(db, appt, R.confirme, RESP_ENTRETIEN)
    with pytest.raises(TransitionError, match="reports"):
        change_status(db, appt, R.reporte, CANDIDAT)


def test_allowed_targets_for_frontend_buttons(db, application):
    application.status = A.en_traitement
    assert set(allowed_targets(application, RESPONSABLE)) == {"complement_demande", "en_attente_qcm", "refusee"}
    assert allowed_targets(application, CANDIDAT) == []


def test_attachment_must_have_exactly_one_owner(db, application):
    db.add(Attachment(doc_type="diplome", original_name="d.pdf", storage_path="/x"))
    with pytest.raises(Exception):
        db.flush()


def test_program_required_before_submission(db, application):
    application.consent_given_at = datetime.now(timezone.utc)
    application.program_id = None
    with pytest.raises(TransitionError, match="formation"):
        change_status(db, application, A.soumise, CANDIDAT)


def test_equivalence_decision_reserved_to_humans(db, equivalence):
    equivalence.status = E.en_traitement
    for actor in (AGENT_IA, SYSTEME, CANDIDAT):
        with pytest.raises(TransitionError):
            change_status(db, equivalence, E.acceptee, actor)
    for targets in EQUIVALENCE_TRANSITIONS.values():
        for status in (E.acceptee, E.refusee):
            assert not targets.get(status, set()) & {AGENT_IA, SYSTEME}


def test_status_history_records_actor_and_comment(db, application):
    application.consent_given_at = datetime.now(timezone.utc)
    change_status(db, application, A.soumise, CANDIDAT, user_id=application.candidate_id, comment="dossier complet")
    db.commit()
    h = db.scalar(select(StatusHistory))
    assert (h.entity_type, h.old_status, h.new_status, h.actor_label, h.comment) == (
        "application", "brouillon", "soumise", "candidat", "dossier complet"
    )


def test_final_statuses_have_no_exit():
    for status in (A.refusee, A.inscrit, A.abandonnee):
        assert APPLICATION_TRANSITIONS[status] == {}


def test_attachment_cannot_have_two_owners(db, application, equivalence):
    db.add(Attachment(doc_type="diplome", original_name="d.pdf", storage_path="/x",
                      application_id=application.id, equivalence_request_id=equivalence.id))
    with pytest.raises(Exception):
        db.flush()


def test_attachment_with_one_owner_is_accepted(db, application):
    db.add(Attachment(doc_type="diplome", original_name="d.pdf", storage_path="/x", application_id=application.id))
    db.flush()
