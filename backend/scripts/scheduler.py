"""Planificateur (service `scheduler` de docker-compose).

- Synchronisation du catalogue depuis les sites officiels toutes les SYNC_INTERVAL_HOURS heures.
- Purge des sessions visiteurs anonymes expirées une fois par jour (rétention temporaire, SA-23).

Première exécution 1 minute après le démarrage. Ne s'arrête jamais sur une erreur.
Usage : python -m scripts.scheduler
"""
import logging
import time

from app.core.config import settings
from app.db.session import SessionLocal
from app.scraping.sync import format_report
from scripts.purge_sessions import purge_expired_sessions
from scripts.sync_sites import sync_from_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [scheduler] %(message)s")
log = logging.getLogger(__name__)

PURGE_INTERVAL_S = 24 * 3600
TICK_S = 60


def run_sync_job() -> None:
    run = sync_from_settings("schedule")
    log.info("\n%s", format_report(run))


def run_purge_job() -> None:
    with SessionLocal() as db:
        log.info("%s", purge_expired_sessions(db))


def run_forever(jobs: list[tuple[str, float, callable]], sleep=time.sleep, clock=time.monotonic, max_ticks=None):
    """Boucle simple : chaque tâche est lancée quand son intervalle est écoulé ; une erreur est journalisée
    puis la tâche est retentée au cycle suivant. `max_ticks` sert aux tests."""
    next_run = {name: clock() + TICK_S for name, _, _ in jobs}
    ticks = 0
    while max_ticks is None or ticks < max_ticks:
        ticks += 1
        sleep(TICK_S)
        for name, interval, job in jobs:
            if clock() >= next_run[name]:
                try:
                    job()
                except Exception:  # le planificateur ne doit jamais s'arrêter sur une erreur
                    log.exception("Échec de la tâche %s, nouvel essai au prochain cycle", name)
                next_run[name] = clock() + interval


def main() -> None:
    sync_interval = max(1, settings.sync_interval_hours) * 3600
    log.info("Synchro du catalogue toutes les %s h (sites : %s) ; purge des sessions anonymes toutes les 24 h",
             settings.sync_interval_hours, settings.sync_sites)
    run_forever([("synchro", sync_interval, run_sync_job), ("purge", PURGE_INTERVAL_S, run_purge_job)])


if __name__ == "__main__":
    main()
