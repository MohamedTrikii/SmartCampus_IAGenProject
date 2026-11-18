"""Import du catalogue officiel des formations depuis un fichier JSON (SA-19).

- Valide chaque formation avec le schéma de l'API (ProgramIn) : mêmes règles que POST /programs.
- Crée ou met à jour (idempotent : relancer l'import ne crée pas de doublons).
- Signale les données à compléter (EXEMPLE, TODO, source_url manquante, frais non officiels).

Usage : python -m scripts.import_catalogue ../data/catalogue.json [--dry-run]
"""
import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes_catalog import apply_program
from app.api.schemas import ProgramIn
from app.db.models import Institution, Program
from app.db.session import SessionLocal
from scripts import utf8_console


class InstitutionIn(BaseModel):
    code: str
    name: str
    city: str | None = None
    website: str | None = None


@dataclass
class ImportReport:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def __str__(self) -> str:
        lines = [
            f"Formations créées      : {len(self.created)} {self.created}",
            f"Formations mises à jour: {len(self.updated)} {self.updated}",
        ]
        lines += [f"⚠️  {w}" for w in self.warnings]
        lines += [f"❌ {e}" for e in self.errors]
        return "\n".join(lines)


def _warnings_for(p: ProgramIn) -> list[str]:
    out = []
    text = json.dumps(p.model_dump(mode="json"), ensure_ascii=False)
    if "EXEMPLE" in p.name:
        out.append(f"{p.code} : donnée d'EXEMPLE à remplacer par l'information officielle")
    elif "TODO" in text:
        out.append(f"{p.code} : contient encore des TODO")
    if not p.source_url:
        out.append(f"{p.code} : source_url manquante (traçabilité de l'information officielle)")
    if any(not f.is_official for f in p.fees):
        out.append(f"{p.code} : frais non marqués officiels — l'assistant ne doit pas les annoncer")
    return out


def import_catalogue(db: Session, data: dict) -> ImportReport:
    report = ImportReport()

    for raw in data.get("institutions", []):
        try:
            inst = InstitutionIn.model_validate(raw)
        except ValidationError as exc:
            report.errors.append(f"établissement {raw.get('code', '?')} : {exc.errors()[0]['msg']}")
            continue
        if "TODO" in inst.name:
            report.warnings.append(f"établissement {inst.code} : nom officiel à confirmer (TODO)")
        existing = db.scalar(select(Institution).where(Institution.code == inst.code.upper()))
        if existing is None:
            db.add(Institution(**{**inst.model_dump(), "code": inst.code.upper()}))
        else:
            for key, value in inst.model_dump(exclude={"code"}).items():
                setattr(existing, key, value)
    db.flush()

    seen: set[str] = set()
    for index, raw in enumerate(data.get("programs", [])):
        label = raw.get("code", f"#{index}")
        try:
            payload = ProgramIn.model_validate(raw)
        except ValidationError as exc:
            err = exc.errors()[0]
            report.errors.append(f"{label} : champ {'.'.join(map(str, err['loc']))} — {err['msg']}")
            continue
        if payload.code in seen:
            report.errors.append(f"{payload.code} : code en double dans le fichier")
            continue
        seen.add(payload.code)

        program = db.scalar(select(Program).where(Program.code == payload.code))
        is_new = program is None
        if is_new:
            program = Program()  # ajouté à la session seulement une fois rempli et valide
        try:
            with db.begin_nested():
                apply_program(db, program, payload)
                program.data_source = "manual"  # corrections manuelles : verrouillées pour la synchro
                if is_new:
                    db.add(program)
        except HTTPException as exc:
            report.errors.append(f"{payload.code} : {exc.detail}")
            continue
        (report.created if is_new else report.updated).append(payload.code)
        report.warnings.extend(_warnings_for(payload))

    known = {c for (c,) in db.execute(select(Program.code))}
    for code in seen:
        program = db.scalar(select(Program).where(Program.code == code))
        for bridge in program.bridges if program else []:
            if bridge not in known:
                report.warnings.append(f"{code} : passerelle vers {bridge} inconnue")
    return report


def main() -> None:
    utf8_console()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="valide et affiche le rapport sans rien enregistrer")
    args = parser.parse_args()

    data = json.loads(args.path.read_text(encoding="utf-8"))
    with SessionLocal() as db:
        report = import_catalogue(db, data)
        print(report)
        if not report.ok:
            db.rollback()
            print("\nImport annulé : corrigez les erreurs ci-dessus.")
            sys.exit(1)
        if args.dry_run:
            db.rollback()
            print("\n--dry-run : rien n'a été enregistré.")
        else:
            db.commit()
            print("\nImport terminé.")


if __name__ == "__main__":
    main()
