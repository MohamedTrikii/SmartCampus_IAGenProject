"""Synchronisation automatique du catalogue depuis les sites officiels (SA-19).

Pour chaque site : découverte des pages → extraction des formations → comparaison avec la base →
création / mise à jour / désactivation, avec un journal détaillé (`catalog_sync_runs`).

Règles :
- une formation saisie à la main (data_source="manual", ex. via data/catalogue.json) n'est jamais écrasée ;
- une formation n'est désactivée que si sa page répond 404/410 (jamais sur une simple erreur réseau) ;
- toutes les pages collectées sont gardées dans `official_documents` (corpus du RAG au sprint 2).
"""
from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.routes_catalog import apply_program
from app.api.schemas import ProgramIn
from app.db.models import CatalogSyncRun, Institution, OfficialDocument, Program
from app.scraping.extractor import ScrapedProgram, complete_with_llm, content_hash, extract_program, parse_page
from app.scraping.fetcher import HttpGetter, SiteCrawler
from app.scraping.sources import SiteSource

ChatFn = Callable[[list[dict]], str]
COMPARED_FIELDS = ("name", "level", "duration_years", "language", "description", "career_outcomes", "source_url")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _snapshot(program: Program) -> dict:
    return {
        "name": program.name,
        "level": program.level.value if hasattr(program.level, "value") else program.level,
        "duration_years": program.duration_years,
        "language": program.language,
        "description": program.description,
        "career_outcomes": list(program.career_outcomes or []),
        "source_url": program.source_url,
        "bac_sections": sorted({s for r in program.requirements for s in (r.bac_sections or [])}),
        "fees": sorted((f.fee_type, str(Decimal(f.amount).normalize()), f.currency) for f in program.fees),
        "is_active": program.is_active,
    }


def _payload_snapshot(payload: ProgramIn) -> dict:
    return {
        "name": payload.name,
        "level": payload.level.value,
        "duration_years": payload.duration_years,
        "language": payload.language,
        "description": payload.description,
        "career_outcomes": list(payload.career_outcomes),
        "source_url": payload.source_url,
        "bac_sections": sorted({s for r in payload.requirements for s in r.bac_sections}),
        "fees": sorted((f.fee_type, str(Decimal(f.amount).normalize()), f.currency) for f in payload.fees),
        "is_active": True,
    }


def _richness(p: ScrapedProgram) -> int:
    """Quantité d'information officielle extraite (pour départager deux pages au même code)."""
    return (3 * len(p.fees) + 2 * bool(p.duration_years) + len(p.bac_sections) + len(p.career_outcomes)
            + len(p.modules) + bool(p.language) + bool(p.conditions_notes))


def _diff(before: dict, after: dict) -> dict:
    return {k: {"avant": before[k], "apres": after[k]} for k in after if before.get(k) != after[k]}


def _ensure_institution(db: Session, site: SiteSource) -> Institution:
    inst = db.scalar(select(Institution).where(Institution.code == site.institution_code))
    if inst is None:
        inst = Institution(code=site.institution_code, name=site.institution_name, city=site.city, website=site.base_url)
        db.add(inst)
        db.flush()
    elif not inst.website:
        inst.website = site.base_url
    return inst


def _store_document(db: Session, inst: Institution, url: str, html: str, status: int, is_program: bool) -> None:
    page = parse_page(url, html)
    digest = content_hash(page.text)
    doc = db.scalar(select(OfficialDocument).where(OfficialDocument.source_url == url))
    now = _now()
    if doc is None:
        doc = OfficialDocument(source_url=url, institution_id=inst.id, created_at=now, last_changed_at=now)
        db.add(doc)
    elif doc.content_hash != digest:
        doc.last_changed_at = now
    doc.title = (page.title or url)[:300]
    doc.doc_type = "page_formation" if is_program else "page_site"
    doc.content_text = page.text
    doc.content_hash = digest
    doc.http_status = status
    doc.last_fetched_at = now


def sync_site(
    db: Session,
    site: SiteSource,
    http_get: HttpGetter,
    llm_chat: ChatFn | None = None,
    today: date | None = None,
) -> tuple[dict, list[dict], list[str]]:
    stats = dict(pages=0, programs_found=0, created=0, updated=0, unchanged=0, deactivated=0, ignored_manual=0, errors=0)
    changes: list[dict] = []
    errors: list[str] = []

    crawler = SiteCrawler(site, http_get)
    urls = crawler.discover()
    errors.extend(f"[{site.institution_code}] {e}" for e in crawler.errors)
    if not urls or all(crawler.fetch(u).status == 0 for u in urls[:1]):
        errors.append(f"[{site.institution_code}] site injoignable ({site.base_url}) : aucune modification")
        stats["errors"] = len(errors)
        return stats, changes, errors

    inst = _ensure_institution(db, site)
    seen_codes: set[str] = set()

    # 1) lecture de toutes les pages ; si deux pages donnent le même code, on garde la plus complète
    extracted: dict[str, tuple[str, str, ScrapedProgram]] = {}
    for url in crawler.program_candidates(urls):
        res = crawler.fetch(url)
        if res.status != 200 or not res.html:
            continue
        stats["pages"] += 1
        scraped = extract_program(site, url, res.html, today)
        _store_document(db, inst, url, res.html, res.status, scraped is not None)
        if scraped is None:
            continue
        previous = extracted.get(scraped.code)
        if previous is None or _richness(scraped) > _richness(previous[2]):
            extracted[scraped.code] = (url, res.html, scraped)

    # 2) création / mise à jour des formations
    for code, (url, html, scraped) in extracted.items():
        seen_codes.add(code)
        stats["programs_found"] += 1
        if llm_chat is not None:
            scraped = complete_with_llm(scraped, html, llm_chat)

        try:
            payload = ProgramIn.model_validate(scraped.to_program_in())
        except ValidationError as exc:
            err = exc.errors()[0]
            errors.append(f"[{site.institution_code}] {url} : {'.'.join(map(str, err['loc']))} — {err['msg']}")
            continue

        program = db.scalar(
            select(Program)
            .where(Program.code == payload.code)
            .options(selectinload(Program.requirements), selectinload(Program.fees))
        )
        if program is not None and program.data_source == "manual":
            stats["ignored_manual"] += 1
            changes.append({"code": payload.code, "action": "ignoree_saisie_manuelle", "url": url})
            continue
        if program is not None and program.page_hash == scraped.page_hash and program.is_active:
            program.last_synced_at = _now()
            stats["unchanged"] += 1
            continue

        is_new = program is None
        before = {} if is_new else _snapshot(program)
        target = Program() if is_new else program
        try:
            with db.begin_nested():
                apply_program(db, target, payload)
                target.data_source = "scraped"
                target.page_hash = scraped.page_hash
                target.last_synced_at = _now()
                target.is_active = True
                if is_new:
                    db.add(target)
        except HTTPException as exc:
            errors.append(f"[{site.institution_code}] {payload.code} : {exc.detail}")
            continue

        after = _payload_snapshot(payload)
        diff = after if is_new else _diff(before, after)
        stats["created" if is_new else "updated"] += 1
        changes.append({
            "code": payload.code, "action": "creee" if is_new else "mise_a_jour", "url": url,
            "extrait_par": scraped.extracted_by, "champs": diff,
        })

    # formations synchronisées précédemment dont la page a disparu (404 / 410) → désactivées
    previous = db.scalars(
        select(Program).where(
            Program.institution_id == inst.id, Program.data_source == "scraped", Program.is_active.is_(True)
        )
    ).all()
    for program in previous:
        if program.code in seen_codes or not program.source_url:
            continue
        status = crawler.fetch(program.source_url).status
        if status in (404, 410):
            program.is_active = False
            program.last_synced_at = _now()
            stats["deactivated"] += 1
            changes.append({"code": program.code, "action": "desactivee", "url": program.source_url, "http": status})

    if stats["pages"] == 0:
        errors.append(f"[{site.institution_code}] aucune page lisible ({site.base_url}) : site protégé contre "
                      "les robots ou indisponible — aucune modification")
    elif stats["programs_found"] == 0 and site.expects_programs:
        errors.append(f"[{site.institution_code}] {stats['pages']} pages lues mais aucune formation reconnue : "
                      "vérifier l'extracteur sur une page réelle")
    stats["errors"] = len(errors)
    return stats, changes, errors


def run_sync(
    db: Session,
    sites: list[SiteSource],
    http_get: HttpGetter,
    trigger: str = "cli",
    dry_run: bool = False,
    llm_chat: ChatFn | None = None,
    today: date | None = None,
) -> CatalogSyncRun:
    """Synchronise tous les sites. En --dry-run, rien n'est enregistré sauf le journal de l'exécution."""
    all_stats: dict[str, dict] = {}
    all_changes: list[dict] = []
    all_errors: list[str] = []
    started = _now()

    for site in sites:
        try:
            with db.begin_nested():
                stats, changes, errors = sync_site(db, site, http_get, llm_chat, today)
        except Exception as exc:  # une panne sur un site n'empêche pas les autres
            stats, changes, errors = {"errors": 1}, [], [f"[{site.institution_code}] erreur inattendue : {exc!r}"]
        all_stats[site.institution_code] = stats
        all_changes.extend(changes)
        all_errors.extend(errors)

    if dry_run:
        db.rollback()
    ok_sites = [c for c, s in all_stats.items() if s.get("pages", 0) > 0]
    status = "failed" if not ok_sites else ("partial" if all_errors else "success")
    run = CatalogSyncRun(
        trigger=trigger, dry_run=dry_run, status=status, started_at=started, finished_at=_now(),
        stats=all_stats, changes=all_changes, errors=all_errors,
    )
    db.add(run)
    db.commit()
    return run


def format_report(run: CatalogSyncRun) -> str:
    lines = [f"Synchronisation #{run.id} ({run.trigger}{', dry-run' if run.dry_run else ''}) : {run.status}"]
    for code, s in run.stats.items():
        lines.append(
            f"  {code:5} pages={s.get('pages', 0):3} formations={s.get('programs_found', 0):3} "
            f"créées={s.get('created', 0)} maj={s.get('updated', 0)} inchangées={s.get('unchanged', 0)} "
            f"désactivées={s.get('deactivated', 0)} manuelles={s.get('ignored_manual', 0)} erreurs={s.get('errors', 0)}"
        )
    for c in run.changes:
        detail = ", ".join(c.get("champs", {}).keys()) if c["action"] == "mise_a_jour" else c.get("url", "")
        lines.append(f"  • {c['action']:24} {c['code']:40} {detail}")
    lines += [f"  ⚠️ {e}" for e in run.errors]
    return "\n".join(lines)
