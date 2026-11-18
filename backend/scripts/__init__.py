"""Scripts d'exploitation (seed, import, synchronisation, purge, planificateur)."""
import sys


def utf8_console() -> None:
    """Évite les accents illisibles dans la console Windows (cp1252 / cp850)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
