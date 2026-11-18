"""Extraction des informations d'une page de formation.

Principe anti-invention : on ne garde QUE ce qui figure dans le texte de la page.
1. Extraction par règles (titres, listes, motifs « 556DT/9 mois », « BAC (Math – Sciences – ...) »).
2. Optionnel : un LLM complète les champs restés vides ; chaque valeur qu'il propose est vérifiée dans le
   texte de la page et rejetée sinon (voir `verify_llm_fields`).
"""
import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from app.scraping.sources import SiteSource

NUMBER_WORDS = {"un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7}
BAC_NORMALIZATION = {
    "math": "Mathématiques",
    "sciences experimentales": "Sciences expérimentales",
    "sciences": "Sciences expérimentales",
    "informatique": "Informatique",
    "sciences de l'informatique": "Informatique",
    "technique": "Technique",
    "sciences techniques": "Technique",
    "economie": "Économie et gestion",
    "lettres": "Lettres",
    "sport": "Sport",
}
SECTION_KEYWORDS = {
    "outcomes": ("débouché", "debouche", "métier", "metier", "carrière", "carriere", "perspective", "emploi"),
    "modules": ("module", "programme", "contenu", "matière", "matiere", "enseignement"),
    "conditions": ("condition", "pré-requis", "prérequis", "pre-requis", "admission", "accès", "acces", "profil"),
}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def content_hash(text: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode()).hexdigest()


def current_academic_year(today: date | None = None) -> str:
    today = today or date.today()
    start = today.year if today.month >= 9 else today.year - 1
    return f"{start}-{start + 1}"


# ---------------------------------------------------------------- page → texte
@dataclass
class ParsedPage:
    url: str
    title: str
    text: str
    main: Tag
    meta_description: str | None


def parse_page(url: str, html: str) -> ParsedPage:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "form"]):
        tag.decompose()
    meta = soup.find("meta", attrs={"name": "description"})
    h1 = soup.find("h1")
    raw_title = (h1.get_text(" ", strip=True) if h1 else "") or (soup.title.get_text(strip=True) if soup.title else "")
    title = re.split(r"\s+[|–—-]\s+", raw_title)[0].strip()

    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(class_=re.compile(r"(entry|post|page)-content|elementor-section-wrap|content-area"))
        or soup.body
        or soup
    )
    for tag in main.find_all(["nav", "header", "footer", "aside"]):
        tag.decompose()
    text = re.sub(r"[ \t]+", " ", main.get_text("\n", strip=True))
    return ParsedPage(url, title, text, main, meta.get("content") if meta else None)


# ---------------------------------------------------------------- classement
PREREQ_LABEL = re.compile(r"^(pre-?requis|prerequis|conditions? d.acces|admission)\s*:?$")


def _without_prerequisites(text: str) -> str:
    """Retire le bloc « Pré-requis » (ex. « Prépa|Licence|Mastère ») : il décrit l'accès, pas le niveau."""
    lines, out, skip = text.splitlines(), [], 0
    for line in lines:
        if skip:
            skip -= 1
            continue
        if PREREQ_LABEL.match(strip_accents(line.strip())):
            skip = 1  # la ligne suivante liste les diplômes requis
            continue
        out.append(line)
    return "\n".join(out)


def detect_level(url: str, title: str, text: str) -> str | None:
    head = strip_accents(f"{urlparse(url).path} {title}")
    intro = strip_accents(_without_prerequisites(text)[:800])
    if re.search(r"prepa|preparatoire", head):
        return "prepa"
    if re.search(r"mastere|master|\bmba\b", head):
        return "master"
    if "architect" in head:
        return "autre"
    if re.search(r"filieres-ingenieur|ingenieur", head):
        return "ingenieur"
    if "licence" in head or re.search(r"\blicence\b", intro):
        return "licence"
    if re.search(r"\bgenie\b", head):
        return "ingenieur"
    return None


def is_program_page(page: ParsedPage, level: str | None) -> bool:
    if level is None:
        return False
    t = strip_accents(page.text)
    markers = sum(
        bool(re.search(p, t))
        for p in (r"pre-?requis|conditions? d.acces|admission", r"debouche|metiers|carriere", r"modules?|programme|duree")
    )
    has_fees = bool(re.search(r"\d\s*(dt|tnd|€|eur)\s*/\s*\d+\s*mois", t))
    return has_fees or markers >= 2


# ---------------------------------------------------------------- extraction par règles
def _sections(main: Tag) -> dict[str, list[str]]:
    """Listes (puces) placées sous un titre dont le texte contient un mot-clé (débouchés, modules, conditions)."""
    out: dict[str, list[str]] = {k: [] for k in SECTION_KEYWORDS}
    headings = main.find_all(re.compile(r"^h[1-6]$")) + main.find_all("strong")
    for h in headings:
        label = strip_accents(h.get_text(" ", strip=True))
        if not label or len(label) > 80:
            continue
        for key, words in SECTION_KEYWORDS.items():
            if any(strip_accents(w) in label for w in words):
                items = []
                for sib in h.find_all_next():
                    if sib is not h and sib.name and re.match(r"^h[1-6]$", sib.name):
                        break
                    if main not in sib.parents:
                        break  # sortie du contenu principal (menu, pied de page) : on s'arrête
                    if sib.name == "li":
                        txt = sib.get_text(" ", strip=True)
                        if 2 < len(txt) < 200 and not txt.rstrip().endswith(":"):
                            items.append(txt)
                    if len(items) >= 30:
                        break
                out[key].extend(i for i in items if i not in out[key])
    return out


# Repli quand la page n'a pas de puces <li> : titres et éléments sont de simples lignes de texte
# (constructeurs de pages type Elementor). On lit les lignes courtes qui suivent le titre.
TEXT_SECTION_TITLES = {
    "outcomes": re.compile(r"^(debouches?|metiers? vises|perspectives? professionnelles?)\b"),
    "modules": re.compile(r"^(principaux modules|modules?|matieres|programme des? (cours|etudes))\b"),
}
TEXT_SECTION_STOP = re.compile(
    r"^(objectifs?|plans? d.etudes|resultats? d.apprentissage|referentiel|competences|debouches|contact|frais|"
    r"pre-?requis|conditions|principaux modules|route |copyright|nous utilisons des cookies)"
)


def _text_sections(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {k: [] for k in TEXT_SECTION_TITLES}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, line in enumerate(lines):
        label = strip_accents(line)
        for key, title in TEXT_SECTION_TITLES.items():
            if len(label) > 60 or not title.match(label):
                continue
            for item in lines[i + 1 : i + 31]:
                low = strip_accents(item)
                if TEXT_SECTION_STOP.match(low) or item.endswith(":") or len(item) > 120:
                    break
                if "@" in item or re.search(r"\+?\(?\+?216|\d{2} \d{2} \d{2}", item):
                    break  # coordonnées : fin du contenu
                if item not in out[key]:
                    out[key].append(item)
    return out


def _amount(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(" ", "").replace(" ", "").replace(",", "."))
    except InvalidOperation:
        return None


def extract_fees(text: str, academic_year: str) -> list[dict]:
    fees: list[dict] = []
    for raw, months in re.findall(r"(\d[\d  .,]*)\s*(?:DT|TND|dinars?)\s*/\s*(\d+)\s*mois", text, re.I):
        if (amount := _amount(raw)) is not None:
            fees.append({"fee_type": f"scolarite_{months}_mois", "amount": amount, "currency": "TND"})
            break
    for raw, months in re.findall(r"(\d[\d  .,]*)\s*(?:€|EUR|euros?)\s*/\s*(\d+)\s*mois", text, re.I):
        if (amount := _amount(raw)) is not None:
            fees.append({"fee_type": f"scolarite_{months}_mois_intl", "amount": amount, "currency": "EUR"})
            break
    for sentence in re.split(r"(?<=[.!?\n])\s+", text):
        if re.search(r"inscription", sentence, re.I) and re.search(r"(?:frais|droits?)", sentence, re.I):
            for raw, cur in re.findall(r"(\d[\d  .,]*)\s*(DT|TND|€|EUR)", sentence, re.I):
                intl = cur.upper() in ("€", "EUR")
                fee_type = "inscription_intl" if intl else "inscription"
                if (amount := _amount(raw)) is not None and fee_type not in {f["fee_type"] for f in fees}:
                    fees.append({"fee_type": fee_type, "amount": amount, "currency": "EUR" if intl else "TND"})
            break
    for f in fees:
        f.update(academic_year=academic_year, is_official=True)
    return fees


def extract_bac_sections(text: str) -> list[str]:
    found: list[str] = []
    for group in re.findall(r"(?:BAC|baccalaur[ée]at)[^()\n]{0,60}\(([^)]{3,200})\)", text, re.I):
        for part in re.split(r"\s*[–—\-,/;]\s*|\s+ou\s+|\s+et\s+(?=[A-ZÉ])", group):
            key = strip_accents(part.strip(" .")).replace("&", "et")
            key = re.sub(r"\s+", " ", key)
            label = next((v for k, v in BAC_NORMALIZATION.items() if key.startswith(k)), None)
            if label and label not in found:
                found.append(label)
    return found


def extract_duration(text: str) -> int | None:
    t = strip_accents(text)
    values = []
    for m in re.finditer(r"(?:duree|dure|s'etend sur|en|sur)\s*:?\s*(\d|un|deux|trois|quatre|cinq|six|sept)\s+(?:ans|annees)\b", t):
        values.append(int(m.group(1)) if m.group(1).isdigit() else NUMBER_WORDS[m.group(1)])
    return max(values) if values else None


def extract_language(text: str) -> str | None:
    m = re.search(
        r"(?:enseign\w*|cours|dispens\w*)[^.\n]{0,40}?\ben\s+(fran[cç]ais|anglais)"
        r"(?:\s+(?:et|ou)\s+(?:en\s+)?(fran[cç]ais|anglais))?",
        text,
        re.I,
    )
    if not m:
        return None
    langs = [g.capitalize().replace("Francais", "Français") for g in m.groups() if g]
    langs = list(dict.fromkeys(langs))
    return " / ".join(langs)


def extract_conditions_notes(text: str) -> str | None:
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+|\n", text)
        if re.search(r"dipl[ôo]me de pr[ée]paratoire|titulaire|baccalaur|\bBAC\b|licence en|pr[ée]-?requis|accessible", s, re.I)
        and 15 < len(s) < 400
    ]
    return " ".join(dict.fromkeys(sentences))[:1000] or None


def make_code(site: SiteSource, url: str) -> str:
    slug = urlparse(url).path.strip("/").split("/")[-1] or "accueil"
    slug = re.sub(r"-\d+$", "", slug)
    code = f"{site.institution_code}-{re.sub(r'[^A-Za-z0-9]+', '-', strip_accents(slug)).strip('-').upper()}"
    if len(code) <= 40:
        return code
    # code trop long : on garde le début et un suffixe stable dérivé de l'URL complète (pas de collision)
    return f"{code[:33].rstrip('-')}-{hashlib.sha1(url.encode()).hexdigest()[:6].upper()}"


@dataclass
class ScrapedProgram:
    code: str
    institution_code: str
    level: str
    name: str
    source_url: str
    page_hash: str
    duration_years: int | None = None
    language: str | None = None
    description: str | None = None
    career_outcomes: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    bac_sections: list[str] = field(default_factory=list)
    conditions_notes: str | None = None
    fees: list[dict] = field(default_factory=list)
    extracted_by: list[str] = field(default_factory=lambda: ["regles"])

    def to_program_in(self) -> dict:
        description = self.description or ""
        if self.modules:
            description = (description + "\n\nModules principaux : " + " ; ".join(self.modules)).strip()
        requirements = []
        if self.bac_sections or self.conditions_notes:
            requirements.append({"bac_sections": self.bac_sections, "notes": self.conditions_notes})
        return {
            "code": self.code,
            "institution_code": self.institution_code,
            "level": self.level,
            "name": self.name[:200],
            "duration_years": self.duration_years,
            "language": self.language,
            "description": description or None,
            "career_outcomes": self.career_outcomes,
            "bridges": [],
            "source_url": self.source_url,
            "requirements": requirements,
            "fees": self.fees,
        }

    def as_dict(self) -> dict:
        return json.loads(json.dumps(asdict(self), default=str))


def extract_program(site: SiteSource, url: str, html: str, today: date | None = None) -> ScrapedProgram | None:
    page = parse_page(url, html)
    level = detect_level(url, page.title, page.text)
    if not page.title or not is_program_page(page, level):
        return None
    sections = _sections(page.main)
    fallback = _text_sections(page.text)
    for key in ("outcomes", "modules"):
        if not sections[key]:
            sections[key] = fallback[key]
    description = page.meta_description
    if not description:
        paragraph = next(
            (p.get_text(" ", strip=True) for p in page.main.find_all("p") if len(p.get_text(strip=True)) >= 80), None
        )
        description = paragraph
    return ScrapedProgram(
        code=make_code(site, url),
        institution_code=site.institution_code,
        level=level,
        name=page.title,
        source_url=url,
        page_hash=content_hash(page.text),
        duration_years=extract_duration(page.text),
        language=extract_language(page.text),
        description=(description or "")[:1500] or None,
        career_outcomes=sections["outcomes"][:20],
        modules=sections["modules"][:25],
        bac_sections=extract_bac_sections(page.text),
        conditions_notes=extract_conditions_notes(page.text),
        fees=extract_fees(page.text, current_academic_year(today)),
    )


# ---------------------------------------------------------------- complément par LLM (vérifié)
LLM_PROMPT = """Tu extrais des informations d'une page web d'une formation universitaire tunisienne.
Réponds UNIQUEMENT par un objet JSON avec ces clés (null ou [] si l'information n'est PAS écrite dans la page) :
{"duration_years": entier|null, "language": texte|null, "career_outcomes": [texte], "modules": [texte],
 "bac_sections": [texte], "conditions": texte|null}
Recopie les éléments tels qu'ils sont écrits. N'invente rien, ne déduis rien."""


def verify_llm_fields(proposed: dict, page_text: str) -> dict:
    """Garde uniquement les valeurs du LLM qui apparaissent réellement dans la page."""
    t = strip_accents(page_text)

    def present(value: str) -> bool:
        v = strip_accents(str(value)).strip(" .")
        return len(v) >= 3 and v in t

    out: dict = {}
    dur = proposed.get("duration_years")
    if isinstance(dur, int) and 1 <= dur <= 8:
        words = [w for w, n in NUMBER_WORDS.items() if n == dur]
        if re.search(rf"\b({dur}|{'|'.join(words)})\s+(ans|annees)\b", t):
            out["duration_years"] = dur
    if proposed.get("language") and all(present(x) for x in re.split(r"\s*(?:/|et|,)\s*", proposed["language"]) if x):
        out["language"] = proposed["language"]
    for key in ("career_outcomes", "modules"):
        values = [v for v in proposed.get(key) or [] if isinstance(v, str) and present(v)]
        if values:
            out[key] = values[:25]
    bac = [b for b in proposed.get("bac_sections") or [] if isinstance(b, str) and present(b[:6])]
    if bac:
        out["bac_sections"] = extract_bac_sections(f"BAC ({' - '.join(bac)})") or bac
    if proposed.get("conditions") and present(str(proposed["conditions"])[:40]):
        out["conditions_notes"] = str(proposed["conditions"])[:1000]
    return out


def complete_with_llm(program: ScrapedProgram, html: str, chat) -> ScrapedProgram:
    """`chat(messages) -> str`. Ne remplit que les champs vides ; tout ce qui n'est pas dans la page est rejeté."""
    page = parse_page(program.source_url, html)
    try:
        raw = chat([{"role": "system", "content": LLM_PROMPT}, {"role": "user", "content": page.text[:12000]}])
        proposed = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
    except Exception:  # LLM indisponible ou réponse non JSON : on garde l'extraction par règles
        return program
    verified = verify_llm_fields(proposed, page.text)
    filled = False
    for key, value in verified.items():
        if not getattr(program, key):
            setattr(program, key, value)
            filled = True
    if filled:
        program.extracted_by = [*program.extracted_by, "llm_verifie"]
    return program
