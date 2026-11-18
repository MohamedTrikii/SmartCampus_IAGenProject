"""Synchronise le catalogue des formations depuis les sites officiels (IIT, ISB, ISA, 2I2S, NAU).

Usage :
  python -m scripts.sync_sites                 # tous les sites de SYNC_SITES
  python -m scripts.sync_sites --site IIT      # un seul site
  python -m scripts.sync_sites --dry-run       # montre ce qui changerait, n'enregistre rien
  python -m scripts.sync_sites --use-llm       # le LLM complète les champs vides (valeurs vérifiées dans la page)
"""
import argparse
import sys

from app.core.config import settings
from app.db.session import SessionLocal
from app.llm.client import LLMClient
from app.scraping.fetcher import make_http_getter
from app.scraping.sources import get_site
from app.scraping.sync import format_report, run_sync
from scripts import utf8_console


def llm_chat_fn():
    client = LLMClient()
    return lambda messages: client.chat(messages).content


def sync_from_settings(trigger: str, site_codes: list[str] | None = None, dry_run: bool = False,
                       use_llm: bool | None = None):
    codes = site_codes or [c.strip() for c in settings.sync_sites.split(",") if c.strip()]
    sites = [get_site(c) for c in codes]
    use_llm = settings.sync_use_llm if use_llm is None else use_llm
    with SessionLocal() as db:
        return run_sync(
            db, sites, make_http_getter(delay_s=settings.sync_request_delay_s), trigger=trigger, dry_run=dry_run,
            llm_chat=llm_chat_fn() if use_llm else None,
        )


def main() -> None:
    utf8_console()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--site", action="append", help="code du site (répétable) : IIT, ISB, ISA, 2I2S, NAU")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--use-llm", action="store_true")
    args = parser.parse_args()

    run = sync_from_settings("cli", args.site, args.dry_run, args.use_llm or None)
    print(format_report(run))
    sys.exit(0 if run.status in ("success", "partial") else 1)


if __name__ == "__main__":
    main()
