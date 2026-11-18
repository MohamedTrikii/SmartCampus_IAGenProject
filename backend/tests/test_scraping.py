"""Synchronisation automatique : tests sur des pages HTML reproduisant la structure de iit.tn."""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db.models import CatalogSyncRun, OfficialDocument, Program
from app.scraping.extractor import (
    detect_level,
    extract_bac_sections,
    extract_duration,
    extract_fees,
    extract_program,
    make_code,
    verify_llm_fields,
)
from app.scraping.fetcher import USER_AGENT, SiteCrawler, allowed_url
from app.scraping.sources import SITES, SiteSource, get_site
from app.scraping.sync import run_sync
from tests.conftest import login

FIX = Path(__file__).parent / "fixtures" / "sites" / "iit"
TODAY = date(2026, 11, 17)
IIT = get_site("IIT")
UNREACHABLE = SiteSource("ISB", "ISB", "https://isb.tn/")


class FakeWeb:
    """Simule Internet : url -> (statut, contenu). Compte les requêtes."""

    def __init__(self):
        self.pages = {
            "https://iit.tn/robots.txt": (200, (FIX / "robots.txt").read_text(encoding="utf-8")),
            "https://iit.tn/wp-sitemap.xml": (200, (FIX / "wp-sitemap.xml").read_text(encoding="utf-8")),
            "https://iit.tn/wp-sitemap-posts-page-1.xml": (200, (FIX / "wp-sitemap-posts-page-1.xml").read_text(encoding="utf-8")),
            "https://iit.tn/": (200, (FIX / "home.html").read_text(encoding="utf-8")),
            "https://iit.tn/prepa/": (200, (FIX / "prepa.html").read_text(encoding="utf-8")),
            "https://iit.tn/big-data-et-analyse-de-donnees/": (200, (FIX / "big-data.html").read_text(encoding="utf-8")),
            "https://iit.tn/filieres-ingenieur/genie-civil/": (200, (FIX / "genie-civil.html").read_text(encoding="utf-8")),
            "https://iit.tn/architecture-2/": (200, (FIX / "architecture.html").read_text(encoding="utf-8")),
            "https://iit.tn/contact/": (200, (FIX / "contact.html").read_text(encoding="utf-8")),
            "https://iit.tn/prive/brouillon/": (200, "<h1>Licence secrète</h1>"),
        }
        self.calls: list[str] = []

    def __call__(self, url: str) -> tuple[int, str]:
        self.calls.append(url)
        if "isb.tn" in url:
            return 0, "ConnectError: unreachable"
        return self.pages.get(url, (404, "Not found"))


@pytest.fixture()
def web():
    return FakeWeb()


def sync(db, web, **kw):
    return run_sync(db, [IIT], web, today=TODAY, **kw)


# ---------------------------------------------------------------- extraction
def test_extracts_licence_page_exactly_as_written():
    html = (FIX / "big-data.html").read_text(encoding="utf-8")
    p = extract_program(IIT, "https://iit.tn/big-data-et-analyse-de-donnees/", html, TODAY)
    assert p.code == "IIT-BIG-DATA-ET-ANALYSE-DE-DONNEES"
    assert p.level == "licence" and p.name == "Big Data et Analyse de données"
    assert p.bac_sections == ["Mathématiques", "Sciences expérimentales", "Informatique", "Économie et gestion", "Technique"]
    assert "Data Scientist" in p.career_outcomes and "Python" in p.modules
    assert p.language == "Français / Anglais"
    assert p.duration_years is None  # la page ne donne pas de durée : on n'invente pas
    fees = {f["fee_type"]: (f["amount"], f["currency"]) for f in p.fees}
    assert fees == {
        "scolarite_9_mois": (Decimal("667"), "TND"),
        "scolarite_9_mois_intl": (Decimal("189"), "EUR"),
        "inscription": (Decimal("800"), "TND"),
        "inscription_intl": (Decimal("800"), "EUR"),
    }
    assert all(f["academic_year"] == "2026-2027" for f in p.fees)


def test_level_detection():
    assert detect_level("https://iit.tn/prepa/", "Cycle Préparatoire", "") == "prepa"
    assert detect_level("https://iit.tn/filieres-ingenieur/genie-civil/", "Génie Civil", "") == "ingenieur"
    # « Génie Logiciel » est une LICENCE à l'IIT : le mot licence en début de page l'emporte
    assert detect_level("https://iit.tn/genie-logiciel/", "Génie Logiciel", "Licence en informatique ...") == "licence"
    assert detect_level("https://iit.tn/mastere/", "Mastère Industries 4.0", "") == "master"
    assert detect_level("https://iit.tn/architecture-2/", "Architecture", "") == "autre"
    assert detect_level("https://iit.tn/contact/", "Contact", "Téléphone") is None


def test_duration_and_bac_parsing():
    assert extract_duration("La formation s'étend sur six ans : 2 ans de premier cycle et 4 ans de second cycle.") == 6
    assert extract_duration("Frais : 556DT/9 mois") is None
    assert extract_bac_sections("baccalauréat scientifique (mathématiques, sciences expérimentales, informatique ou technique)") == [
        "Mathématiques", "Sciences expérimentales", "Informatique", "Technique"]


def test_fee_without_registration_sentence():
    fees = extract_fees("National : 556DT/9 mois* International : 234€/9 mois*", "2026-2027")
    assert [(f["fee_type"], f["amount"]) for f in fees] == [("scolarite_9_mois", Decimal("556")), ("scolarite_9_mois_intl", Decimal("234"))]


def test_non_program_page_is_ignored():
    assert extract_program(IIT, "https://iit.tn/contact/", (FIX / "contact.html").read_text(encoding="utf-8")) is None


def test_long_codes_stay_unique():
    a = make_code(IIT, "https://iit.tn/licence-en-systemes-electriques-intelligents-energies-renouvelables/")
    b = make_code(IIT, "https://iit.tn/licence-en-systemes-electriques-intelligents-energies-nouvelles/")
    assert len(a) <= 40 and len(b) <= 40 and a != b


def test_llm_values_not_in_page_are_rejected():
    page = "Licence en informatique. Débouchés : Data Analyst, Développeur web. Durée : 3 ans. Cours en français."
    proposed = {
        "duration_years": 5,  # inventé
        "career_outcomes": ["Data Analyst", "Astronaute"],  # le 2e est inventé
        "language": "Français",
        "bac_sections": ["Lettres"],  # inventé
    }
    verified = verify_llm_fields(proposed, page)
    assert verified == {"career_outcomes": ["Data Analyst"], "language": "Français"}
    assert verify_llm_fields({"duration_years": 3}, page) == {"duration_years": 3}


# ---------------------------------------------------------------- synchronisation
def test_first_sync_creates_programs_and_documents(db, web):
    run = sync(db, web)
    assert run.status == "success", run.errors
    codes = set(db.scalars(select(Program.code).where(Program.data_source == "scraped")))
    # IIT-PREPA existe déjà en saisie manuelle dans le catalogue de test : il est verrouillé
    assert codes == {"IIT-BIG-DATA-ET-ANALYSE-DE-DONNEES", "IIT-GENIE-CIVIL", "IIT-ARCHITECTURE"}
    archi = db.scalar(select(Program).where(Program.code == "IIT-ARCHITECTURE"))
    assert archi.duration_years == 6 and archi.level.value == "autre"
    assert db.scalar(select(func.count()).select_from(OfficialDocument)) == 6  # 4 formations + accueil + contact
    assert run.stats["IIT"]["created"] == 3 and run.stats["IIT"]["ignored_manual"] == 1
    # robots.txt respecté, pas de PDF téléchargé
    assert "https://iit.tn/prive/brouillon/" not in web.calls
    assert not any(c.endswith(".pdf") for c in web.calls)


def test_second_sync_without_change_updates_nothing(db, web):
    sync(db, web)
    run = sync(db, web)
    assert run.stats["IIT"]["unchanged"] == 3 and run.stats["IIT"]["updated"] == 0
    assert [c["action"] for c in run.changes] == ["ignoree_saisie_manuelle"]


def test_change_on_site_is_applied_with_diff(db, web):
    sync(db, web)
    url = "https://iit.tn/big-data-et-analyse-de-donnees/"
    web.pages[url] = (200, web.pages[url][1].replace("667DT/9 mois", "700DT/9 mois"))
    run = sync(db, web)
    change = next(c for c in run.changes if c["code"] == "IIT-BIG-DATA-ET-ANALYSE-DE-DONNEES")
    assert change["action"] == "mise_a_jour" and set(change["champs"]) == {"fees"}
    fee = next(f for f in db.scalar(select(Program).where(Program.code == change["code"])).fees if f.fee_type == "scolarite_9_mois")
    assert fee.amount == Decimal("700")


def test_removed_page_deactivates_program(db, web):
    sync(db, web)
    del web.pages["https://iit.tn/filieres-ingenieur/genie-civil/"]
    run = sync(db, web)
    assert {"code": "IIT-GENIE-CIVIL", "action": "desactivee"}.items() <= next(
        c for c in run.changes if c["code"] == "IIT-GENIE-CIVIL").items()
    assert db.scalar(select(Program.is_active).where(Program.code == "IIT-GENIE-CIVIL")) is False


def test_network_error_never_deactivates(db, web):
    sync(db, web)
    web.pages["https://iit.tn/filieres-ingenieur/genie-civil/"] = (0, "Timeout")
    sync(db, web)
    assert db.scalar(select(Program.is_active).where(Program.code == "IIT-GENIE-CIVIL")) is True


def test_manual_program_is_never_overwritten(db, web):
    # IIT-PREPA existe déjà dans le catalogue de test, saisi à la main
    before = db.scalar(select(Program.name).where(Program.code == "IIT-PREPA"))
    run = sync(db, web)
    assert db.scalar(select(Program.name).where(Program.code == "IIT-PREPA")) == before
    assert any(c["action"] == "ignoree_saisie_manuelle" and c["code"] == "IIT-PREPA" for c in run.changes)


def test_dry_run_writes_nothing_but_the_log(db, web):
    run = sync(db, web, dry_run=True)
    assert run.stats["IIT"]["created"] == 3  # IIT-PREPA est manuel dans le catalogue de test
    assert db.scalar(select(func.count()).select_from(Program).where(Program.data_source == "scraped")) == 0
    assert db.scalar(select(func.count()).select_from(CatalogSyncRun)) == 1


def test_unreachable_site_does_not_block_others(db, web):
    run = run_sync(db, [UNREACHABLE, IIT], web, today=TODAY)
    assert run.status == "partial"
    assert any("ISB" in e and "injoignable" in e for e in run.errors)
    assert run.stats["IIT"]["created"] == 3


def test_llm_completion_is_verified(db, web):
    def fake_llm(messages):
        return json.dumps({"duration_years": 9, "career_outcomes": ["Bureaux d'études et de conseil", "Pilote de ligne"]})

    sync(db, web, llm_chat=fake_llm)
    civil = db.scalar(select(Program).where(Program.code == "IIT-GENIE-CIVIL"))
    assert civil.duration_years is None  # 9 ans : absent de la page → rejeté
    assert "Pilote de ligne" not in civil.career_outcomes


# ---------------------------------------------------------------- API d'administration
def test_admin_sync_endpoints_permissions(client, monkeypatch):
    import app.api.routes_admin as routes_admin

    calls = []
    monkeypatch.setattr(routes_admin, "_run_in_background", lambda sites, dry: calls.append((sites, dry)))
    admin = login(client, "admin@smartcampus.local", "Admin123!")
    r = client.post("/api/v1/admin/catalog/sync", params={"site": "iit", "dry_run": True}, headers=admin)
    assert r.status_code == 202 and calls == [(["IIT"], True)]
    assert client.post("/api/v1/admin/catalog/sync", params={"site": "XYZ"}, headers=admin).status_code == 400
    assert client.post("/api/v1/admin/catalog/sync").status_code == 401
    assert client.get("/api/v1/admin/catalog/sync-runs", headers=admin).status_code == 200
    assert {s["code"] for s in client.get("/api/v1/admin/catalog/sources", headers=admin).json()} == {
        "IIT", "ISB", "ISA", "2I2S", "NAU"}


# ---------------------------------------------------------------- robot poli
def test_robots_txt_is_respected(web):
    crawler = SiteCrawler(IIT, web)
    urls = crawler.discover()
    for url in crawler.program_candidates(urls):
        crawler.fetch(url)
    assert "https://iit.tn/prive/brouillon/" not in web.calls  # Disallow: /prive/
    assert crawler.fetch("https://iit.tn/prive/brouillon/").status == 403


def test_pdf_and_images_are_never_fetched(db, web):
    sync(db, web)
    assert not any(u.endswith((".pdf", ".png", ".jpg")) or "/wp-content/" in u for u in web.calls)
    assert not allowed_url("https://iit.tn/brochure.PDF", IIT)
    assert not allowed_url("https://autre-site.tn/licence/", IIT)  # jamais hors du site


def test_link_crawl_when_no_sitemap(web):
    for key in [k for k in web.pages if "sitemap" in k]:
        del web.pages[key]
    web.pages["https://iit.tn/robots.txt"] = (200, "User-agent: *\nDisallow: /prive/\n")
    web.pages["https://iit.tn/"] = (200, '<a href="/prepa/">Prépa</a> <a href="/contact/">Contact</a>'
                                        ' <a href="https://facebook.com/iit">fb</a>')
    urls = SiteCrawler(IIT, web).discover()
    assert {"https://iit.tn/", "https://iit.tn/prepa/", "https://iit.tn/contact/"} <= set(urls)
    assert not any("facebook" in u for u in urls)


def test_bot_is_identified_and_sites_configured():
    assert "SmartCampusAI-bot" in USER_AGENT
    assert [s.institution_code for s in SITES] == ["IIT", "ISB", "ISA", "2I2S", "NAU"]
    assert all(s.max_pages == 150 and "/wp-admin" in s.exclude_url_parts for s in SITES)
    with pytest.raises(KeyError):
        get_site("XYZ")


def test_blocked_site_is_reported_not_silent(db):
    """Un site qui répond 403 partout (protection anti-robot) ne doit pas donner un statut « success »."""
    blocked = SiteSource("ISB", "ISB", "https://isb.tn/")

    def http_get(url):
        return (200, "User-agent: *\n") if url.endswith("robots.txt") else (403, "Security check")

    run = run_sync(db, [blocked], http_get, today=TODAY)
    assert run.status == "failed"
    assert any("aucune page lisible" in e for e in run.errors)


def test_site_without_recognized_program_is_flagged(db, web):
    for url in list(web.pages):
        if url.endswith(("prepa/", "donnees/", "genie-civil/", "architecture-2/")):
            del web.pages[url]
    run = sync(db, web)
    assert run.status == "failed" or any("aucune formation reconnue" in e for e in run.errors)


# ---------------------------------------------------------------- pages réelles (enregistrées le 2026-11-18)
REEL = Path(__file__).parent / "fixtures" / "sites"


def reel(path):
    return (REEL / path).read_text(encoding="utf-8")


def test_real_iit_licence_page_big_data():
    p = extract_program(IIT, "https://iit.tn/big-data-et-analyse-de-donnees/", reel("iit/reel/big-data.html"), TODAY)
    assert p.level == "licence" and p.name == "Big Data et Analyse de données"
    assert {(f["fee_type"], f["amount"], f["currency"]) for f in p.fees} == {
        ("scolarite_9_mois", Decimal("667"), "TND"), ("scolarite_9_mois_intl", Decimal("189"), "EUR")
    }
    assert set(p.bac_sections) == {"Mathématiques", "Sciences expérimentales", "Informatique", "Économie et gestion",
                                   "Technique"}
    assert p.career_outcomes[:2] == ["Data Scientist", "Data Analyst"] and len(p.career_outcomes) == 8
    assert "Consultant en Intelligence Artificielle" in p.career_outcomes
    assert not any("Route" in o or "@" in o for o in p.career_outcomes)  # le pied de page n'est pas un débouché
    assert p.modules[0] == "Algorithmique & Programmation" and "MLOps" in p.modules
    assert p.duration_years is None  # non écrite sur la page : jamais inventée


def test_real_prerequisite_line_does_not_decide_level():
    """« Pré-requis : Prépa|Licence|Mastère » décrit l'accès au cycle ingénieur, pas une licence."""
    p = extract_program(IIT, "https://iit.tn/genie-des-procedes/", reel("iit/reel/genie-des-procedes.html"), TODAY)
    assert p.level == "ingenieur"
    assert {f["amount"] for f in p.fees} == {Decimal("611"), Decimal("234")}


def test_real_prose_page_has_no_invented_lists():
    p = extract_program(IIT, "https://iit.tn/filieres-ingenieur/genie-mecanique/",
                        reel("iit/reel/genie-mecanique-filiere.html"), TODAY)
    assert p.level == "ingenieur"
    assert not any(x in p.modules + p.career_outcomes for x in ("Accueil", "Contact", "Formation"))
    isa = extract_program(get_site("ISA"), "https://isa.tn/genie-mecanique/", reel("isa/reel/genie-mecanique.html"), TODAY)
    assert isa.career_outcomes == [] and isa.modules == []  # le menu du site n'est pas lu comme une liste


def test_duplicate_code_keeps_richest_page(db, web):
    # deux URL donnent le même code IIT-BIG-DATA… : la page avec les frais doit gagner
    web.pages["https://iit.tn/big-data-et-analyse-de-donnees-2/"] = (
        200, "<html><body><main><h1>Big Data et Analyse de données</h1><p>Licence. Pré-requis : BAC. "
             "Débouchés : data analyst. Modules : python.</p></main></body></html>")
    sitemap = web.pages["https://iit.tn/wp-sitemap-posts-page-1.xml"][1]
    web.pages["https://iit.tn/wp-sitemap-posts-page-1.xml"] = (200, sitemap.replace(
        "</urlset>", "<url><loc>https://iit.tn/big-data-et-analyse-de-donnees-2/</loc></url></urlset>"))
    sync(db, web)
    program = db.scalar(select(Program).where(Program.code == "IIT-BIG-DATA-ET-ANALYSE-DE-DONNEES"))
    assert program.fees and program.source_url == "https://iit.tn/big-data-et-analyse-de-donnees/"


def test_admin_sync_permissions_by_role(client, monkeypatch):
    import app.api.routes_admin as routes_admin
    from tests.conftest import user_with_role

    monkeypatch.setattr(routes_admin, "_run_in_background", lambda sites, dry: None)
    for role, can_read in [("academic_iit", True), ("academic_isb", True), ("direction", True),
                           ("interviewer", False), ("candidate", False)]:
        h = user_with_role(client, f"{role}@test.tn", role)
        assert (client.get("/api/v1/admin/catalog/sync-runs", headers=h).status_code == 200) is can_read
        assert (client.get("/api/v1/admin/catalog/sources", headers=h).status_code == 200) is can_read
        assert client.post("/api/v1/admin/catalog/sync", headers=h).status_code == 403  # admin uniquement
    r = client.post("/api/v1/admin/catalog/sync", params={"site": "XYZ"}, headers=login(client, "admin@smartcampus.local", "Admin123!"))
    assert r.json()["code"] == "UNKNOWN_SITE"
