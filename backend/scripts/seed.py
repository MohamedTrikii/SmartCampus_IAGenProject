"""Données de référence (SA-15, SA-19) : compte admin + corrections manuelles de data/catalogue.json.

Les formations viennent AUTOMATIQUEMENT des sites officiels (python -m scripts.sync_sites) ;
data/catalogue.json ne contient que les établissements et d'éventuelles corrections manuelles.
Compte admin : ADMIN_EMAIL / ADMIN_PASSWORD (.env). Idempotent : relançable à chaque démarrage.

Usage : python -m scripts.seed
"""
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.models import Program, User, UserRole
from app.db.session import SessionLocal
from scripts.import_catalogue import import_catalogue

# en Docker, ./data est monté en lecture seule sur /data ; en local, data/ est à la racine du dépôt
_DOCKER_CATALOGUE = Path("/data/catalogue.json")
CATALOGUE = _DOCKER_CATALOGUE if _DOCKER_CATALOGUE.exists() else Path(__file__).resolve().parents[2] / "data" / "catalogue.json"


def seed(db: Session, catalogue_path: Path = CATALOGUE) -> None:
    admin_email = settings.admin_email.lower()
    if not db.scalar(select(User).where(User.email == admin_email)):
        db.add(
            User(
                email=admin_email,
                password_hash=hash_password(settings.admin_password),
                full_name="Admin SmartCampus",
                role=UserRole.admin,
            )
        )
    # anciennes données de démonstration : elles bloqueraient la synchronisation des vraies formations
    for example in db.scalars(
        select(Program).where(Program.data_source == "manual", Program.name.contains("(EXEMPLE)"))
    ).all():
        if catalogue_path == CATALOGUE:
            db.delete(example)
    db.flush()
    report = import_catalogue(db, json.loads(catalogue_path.read_text(encoding="utf-8")))
    if not report.ok:
        db.rollback()
        raise SystemExit(f"Catalogue invalide :\n{report}")
    db.commit()


if __name__ == "__main__":
    from scripts import utf8_console

    utf8_console()
    with SessionLocal() as session:
        seed(session)
    print("Seed terminé. Compte admin :", settings.admin_email)
    if settings.admin_password == "Admin123!":
        print("⚠️  Mot de passe admin de démo : définissez ADMIN_PASSWORD dans .env hors poste de développement.")
    print("Formations : lancez la synchronisation automatique → python -m scripts.sync_sites")
