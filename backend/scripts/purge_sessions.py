"""Rétention temporaire des visiteurs anonymes (SA-23 / SA-24).

Supprime les sessions visiteurs EXPIRÉES et NON rattachées à un compte, avec leurs conversations et leurs
messages. Une session rattachée à un compte n'est jamais supprimée : l'historique appartient au candidat.
Durée de rétention : VISITOR_SESSION_DAYS (date d'expiration fixée à la création de la session).

Usage :
  python -m scripts.purge_sessions            # supprime
  python -m scripts.purge_sessions --dry-run  # rapport seulement
Lancé une fois par jour par le service `scheduler` (scripts/scheduler.py).
"""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import Conversation, Message, VisitorSession
from app.db.session import SessionLocal
from scripts import utf8_console


@dataclass
class PurgeReport:
    sessions: int
    conversations: int
    messages: int
    dry_run: bool

    def __str__(self) -> str:
        verb = "seraient supprimés" if self.dry_run else "supprimés"
        return (f"Purge des sessions anonymes expirées ({'dry-run' if self.dry_run else 'réelle'}) : "
                f"{self.sessions} sessions, {self.conversations} conversations, {self.messages} messages {verb}.")


def purge_expired_sessions(db: Session, now: datetime | None = None, dry_run: bool = False) -> PurgeReport:
    now = now or datetime.now(timezone.utc)
    expired = select(VisitorSession.id).where(VisitorSession.user_id.is_(None), VisitorSession.expires_at < now)
    conversations = select(Conversation.id).where(Conversation.session_id.in_(expired))

    report = PurgeReport(
        sessions=db.scalar(select(func.count()).select_from(expired.subquery())) or 0,
        conversations=db.scalar(select(func.count()).select_from(conversations.subquery())) or 0,
        messages=db.scalar(select(func.count()).where(Message.conversation_id.in_(conversations))) or 0,
        dry_run=dry_run,
    )
    if not dry_run:
        # suppression explicite dans l'ordre (ne dépend pas des ON DELETE CASCADE, absents sous SQLite)
        db.execute(delete(Message).where(Message.conversation_id.in_(conversations)))
        db.execute(delete(Conversation).where(Conversation.session_id.in_(expired)))
        db.execute(delete(VisitorSession).where(VisitorSession.user_id.is_(None), VisitorSession.expires_at < now))
        db.commit()
    return report


def main() -> None:
    utf8_console()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="affiche le rapport sans rien supprimer")
    args = parser.parse_args()
    with SessionLocal() as db:
        print(purge_expired_sessions(db, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
