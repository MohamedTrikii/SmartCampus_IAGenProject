"""Administration de la synchronisation du catalogue (SA-19) : admin ; lecture pour responsables et direction."""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DbDep, require_roles
from app.core.errors import ApiError
from app.db.models import CatalogSyncRun, UserRole
from app.scraping.sources import SITES

router = APIRouter(prefix="/admin/catalog", tags=["administration"])
Viewer = Depends(require_roles(UserRole.admin, UserRole.academic_iit, UserRole.academic_isb, UserRole.direction))
AdminOnly = Depends(require_roles(UserRole.admin))


class SyncRunOut(BaseModel):
    id: int
    trigger: str
    dry_run: bool
    status: str
    started_at: datetime
    finished_at: datetime | None
    stats: dict
    changes: list[dict]
    errors: list[str]

    model_config = {"from_attributes": True}


def _run_in_background(site_codes: list[str] | None, dry_run: bool) -> None:
    from scripts.sync_sites import sync_from_settings  # import tardif : évite de charger httpx/LLM au démarrage

    sync_from_settings("api", site_codes, dry_run)


@router.get("/sources", dependencies=[Viewer])
def list_sources():
    return [{"code": s.institution_code, "name": s.institution_name, "url": s.base_url} for s in SITES]


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED, dependencies=[AdminOnly])
def trigger_sync(
    background: BackgroundTasks,
    site: Annotated[list[str] | None, Query()] = None,
    dry_run: bool = False,
):
    known = {s.institution_code for s in SITES}
    unknown = [c for c in site or [] if c.upper() not in known]
    if unknown:
        raise ApiError(status.HTTP_400_BAD_REQUEST, f"Sites inconnus : {', '.join(unknown)}", "UNKNOWN_SITE")
    background.add_task(_run_in_background, [c.upper() for c in site] if site else None, dry_run)
    return {"detail": "Synchronisation lancée", "sites": site or "tous", "dry_run": dry_run}


@router.get("/sync-runs", response_model=list[SyncRunOut], dependencies=[Viewer])
def list_runs(db: DbDep, limit: int = Query(20, ge=1, le=100)):
    return db.scalars(select(CatalogSyncRun).order_by(CatalogSyncRun.id.desc()).limit(limit)).all()
