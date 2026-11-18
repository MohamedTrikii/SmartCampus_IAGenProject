"""Détection de langue légère (baseline Sprint 1) : fr | ar | tn | arabizi.

Heuristique volontairement simple, à remplacer par un classifieur entraîné (ou le LLM lui-même)
une fois le jeu d'évaluation constitué. Elle sert à journaliser la langue et à adapter la consigne.
"""
import re

ARABIC_CHARS = re.compile(r"[؀-ۿ]")
# chiffres utilisés comme lettres en Arabizi : 3=ع 7=ح 9=ق 5=خ 2=ء — collés à des lettres
ARABIZI_DIGITS = re.compile(r"[a-z][2357 9]|[2357 9][a-z]".replace(" ", ""), re.IGNORECASE)
TUNISIAN_WORDS = {
    # latin (Arabizi tunisien)
    "chnowa", "chnoua", "chniya", "chneya", "kifech", "kifach", "3lech", "3lach", "barcha", "behi", "bahi",
    "mte3", "mta3", "nheb", "n7eb", "n7ib", "nhib", "ena", "enti", "inti", "fama", "famma", "mouch", "mich",
    "taw", "tawa", "yesser", "yasser", "9adeh", "9addech", "9adech", "win", "wa9tech", "w9tech", "ya3ni",
    "3andi", "andi", "nejjem", "najem", "na9ra", "nakra", "far9", "bin", "w", "ama", "chkoun", "dima",
    # arabe (dialecte)
    "شنوة", "شنية", "كيفاش", "علاش", "برشا", "باهي", "متاع", "نحب", "فما", "موش", "توا", "ياسر", "قداش",
    "وقتاش", "نقرا", "نجم", "عندي",
}
FRENCH_WORDS = {
    "le", "la", "les", "des", "est", "une", "un", "pour", "quelle", "quelles", "quels", "comment",
    "formation", "licence", "ingénieur", "je", "voudrais", "veux", "quoi", "conditions", "accès", "et",
}


def detect_language(text: str) -> str:
    tokens = re.findall(r"[\w؀-ۿ']+", text.lower())
    if not tokens:
        return "fr"
    tn_hits = sum(t in TUNISIAN_WORDS for t in tokens)
    if ARABIC_CHARS.search(text):
        return "tn" if tn_hits else "ar"
    fr_hits = sum(t in FRENCH_WORDS for t in tokens)
    arabizi_hits = len(ARABIZI_DIGITS.findall(text))
    if tn_hits + arabizi_hits > fr_hits:
        return "arabizi"
    return "fr"
