import copy
import json
from pathlib import Path

from sqlalchemy import func, select

from app.db.models import Program, ProgramFee
from scripts.import_catalogue import import_catalogue

REPO_CATALOGUE = json.loads((Path(__file__).resolve().parents[2] / "data" / "catalogue.json").read_text(encoding="utf-8"))
CATALOGUE = json.loads((Path(__file__).parent / "fixtures" / "catalogue_test.json").read_text(encoding="utf-8"))


def official_program(**overrides):
    program = {
        "code": "ISB-LIC-GESTION",
        "institution_code": "ISB",
        "level": "licence",
        "name": "Licence en gestion",
        "duration_years": 3,
        "source_url": "https://exemple.tn/brochure.pdf",
        "fees": [{"academic_year": "2026-2027", "fee_type": "inscription", "amount": "150.00", "is_official": True}],
    }
    program.update(overrides)
    return {"institutions": [], "programs": [program]}


def test_repository_catalogue_is_valid(db):
    report = import_catalogue(db, copy.deepcopy(REPO_CATALOGUE))
    assert report.ok, report.errors


def test_example_data_is_flagged(db):
    report = import_catalogue(db, copy.deepcopy(CATALOGUE))
    assert report.ok, report.errors
    assert any("EXEMPLE" in w for w in report.warnings)  # les données de démo sont bien signalées


def test_import_creates_then_updates_without_duplicates(db):
    first = import_catalogue(db, official_program())
    assert first.ok and first.created == ["ISB-LIC-GESTION"] and first.warnings == []
    db.commit()
    second = import_catalogue(db, official_program(name="Licence en gestion (mise à jour)"))
    db.commit()
    assert second.updated == ["ISB-LIC-GESTION"] and second.created == []
    assert db.scalar(select(func.count()).select_from(Program).where(Program.code == "ISB-LIC-GESTION")) == 1
    assert db.scalar(select(Program.name).where(Program.code == "ISB-LIC-GESTION")).endswith("(mise à jour)")
    assert db.scalar(select(func.count()).select_from(ProgramFee)) == 1  # frais remplacés, pas dupliqués


def test_missing_field_is_reported(db):
    data = official_program()
    del data["programs"][0]["name"]
    report = import_catalogue(db, data)
    assert not report.ok and "name" in report.errors[0]


def test_unknown_institution_is_reported(db):
    report = import_catalogue(db, official_program(institution_code="XYZ"))
    assert not report.ok and "Établissement inconnu" in report.errors[0]
    assert db.scalar(select(Program).where(Program.code == "ISB-LIC-GESTION")) is None


def test_warnings_for_missing_source_and_unofficial_fees(db):
    data = official_program(source_url=None)
    data["programs"][0]["fees"][0]["is_official"] = False
    report = import_catalogue(db, data)
    assert report.ok
    assert any("source_url" in w for w in report.warnings)
    assert any("non marqués officiels" in w for w in report.warnings)


def test_duplicate_code_in_file(db):
    data = official_program()
    data["programs"].append(copy.deepcopy(data["programs"][0]))
    report = import_catalogue(db, data)
    assert any("double" in e for e in report.errors)


def test_imported_program_is_locked_as_manual(db):
    program = db.scalar(select(Program).where(Program.code == "IIT-ING-GI"))
    program.data_source = "scraped"
    db.commit()
    report = import_catalogue(db, official_program(code="IIT-ING-GI", institution_code="IIT"))
    db.commit()
    assert report.updated == ["IIT-ING-GI"]
    assert db.scalar(select(Program.data_source).where(Program.code == "IIT-ING-GI")) == "manual"


def test_import_twice_is_idempotent(db):
    for _ in range(2):
        assert import_catalogue(db, copy.deepcopy(CATALOGUE)).ok
        db.commit()
    assert db.scalar(select(func.count()).select_from(Program)) == 3
