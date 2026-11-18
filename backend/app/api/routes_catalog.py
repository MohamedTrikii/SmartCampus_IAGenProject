"""API catalogue des formations et frais officiels (SA-19) — source de vérité pour l'agent."""
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbDep, require_roles
from app.api.schemas import InstitutionOut, ProgramIn, ProgramOut, ProgramSummary
from app.core.errors import ApiError
from app.db.models import (
    AdmissionRequirement,
    Institution,
    Program,
    ProgramFee,
    ProgramLevel,
    User,
    UserRole,
)

router = APIRouter(tags=["catalogue"])
EDITORS = (UserRole.admin, UserRole.academic_iit, UserRole.academic_isb)
EditorDep = Annotated[User, Depends(require_roles(*EDITORS))]
SCOPES = {UserRole.academic_iit: "IIT", UserRole.academic_isb: "ISB"}


def _check_scope(user: User, institution_code: str) -> None:
    """Un responsable IIT ne gère que l'IIT, un responsable ISB que l'ISB (les autres : admin uniquement)."""
    scope = SCOPES.get(user.role)
    if scope and scope != institution_code.upper():
        raise ApiError(status.HTTP_403_FORBIDDEN, f"Vous ne pouvez gérer que les formations {scope}", "OUT_OF_SCOPE")


def _get_program(db, code: str) -> Program:
    program = db.scalar(
        select(Program)
        .where(Program.code == code)
        .options(selectinload(Program.requirements), selectinload(Program.fees), selectinload(Program.institution))
    )
    if program is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "Formation introuvable", "PROGRAM_NOT_FOUND")
    return program


def apply_program(db, program: Program, payload: ProgramIn) -> None:
    """Remplit une formation à partir du schéma validé.

    Partagée par l'API (POST/PUT), l'import JSON (scripts/import_catalogue.py) et la synchronisation des
    sites (app/scraping/sync.py). L'appelant fixe ensuite `data_source` (manual ou scraped).
    """
    institution = db.scalar(select(Institution).where(Institution.code == payload.institution_code.upper()))
    if institution is None:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "Établissement inconnu", "UNKNOWN_INSTITUTION")
    data = payload.model_dump(exclude={"requirements", "fees", "institution_code"})
    for key, value in data.items():
        setattr(program, key, value)
    program.institution_id = institution.id
    if program.id is not None and (program.requirements or program.fees):
        # supprimer d'abord les anciennes lignes : sinon SQLAlchemy insère les nouvelles avant
        # de supprimer les anciennes et la contrainte d'unicité (programme, année, type) échoue
        program.requirements.clear()
        program.fees.clear()
        db.flush()
    program.requirements = [AdmissionRequirement(**r.model_dump()) for r in payload.requirements]
    program.fees = [ProgramFee(**f.model_dump()) for f in payload.fees]


@router.get("/institutions", response_model=list[InstitutionOut])
def list_institutions(db: DbDep):
    return db.scalars(select(Institution).order_by(Institution.code)).all()


@router.get("/programs", response_model=list[ProgramSummary])
def list_programs(db: DbDep, institution: str | None = None, level: ProgramLevel | None = None):
    query = select(Program).join(Institution).where(Program.is_active.is_(True)).options(
        selectinload(Program.institution)
    )
    if institution:
        query = query.where(Institution.code == institution.upper())
    if level:
        query = query.where(Program.level == level)
    return db.scalars(query.order_by(Program.code)).all()


@router.get("/programs/{code}", response_model=ProgramOut)
def get_program(code: str, db: DbDep):
    return _get_program(db, code)


@router.post("/programs", response_model=ProgramOut, status_code=status.HTTP_201_CREATED)
def create_program(payload: ProgramIn, db: DbDep, user: EditorDep):
    _check_scope(user, payload.institution_code)
    if db.scalar(select(Program).where(Program.code == payload.code)):
        raise ApiError(status.HTTP_409_CONFLICT, "Code de formation déjà utilisé", "PROGRAM_CODE_ALREADY_USED")
    program = Program()
    apply_program(db, program, payload)
    program.data_source = "manual"  # saisie humaine : verrouillée, la synchronisation ne l'écrase pas
    db.add(program)
    db.commit()
    return _get_program(db, program.code)


@router.put("/programs/{code}", response_model=ProgramOut)
def update_program(code: str, payload: ProgramIn, db: DbDep, user: EditorDep):
    program = _get_program(db, code)
    _check_scope(user, program.institution.code)
    _check_scope(user, payload.institution_code)
    apply_program(db, program, payload)
    program.data_source = "manual"  # une correction humaine verrouille la formation
    db.commit()
    return _get_program(db, program.code)
