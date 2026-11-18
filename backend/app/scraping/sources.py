"""Sites officiels synchronisés automatiquement.

Pour ajouter un site : ajouter une entrée ici. `program_url_hints` aide le crawler à reconnaître les pages
de formation (le classement final se fait sur le contenu de la page, voir extractor.classify_page).
Noms : lus sur les sites (nau.tn liste IIT, ISB et ISA) ; villes seulement si lues. Identiques à data/catalogue.json.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SiteSource:
    institution_code: str
    institution_name: str
    base_url: str
    city: str | None = "Sfax"  # None = non confirmée par le site
    # morceaux d'URL qui signalent probablement une page de formation
    program_url_hints: tuple[str, ...] = ()
    # morceaux d'URL à ne jamais visiter (actualités, blog, fichiers, admin...)
    exclude_url_parts: tuple[str, ...] = (
        "/wp-admin", "/wp-login", "/feed", "/tag/", "/category/", "/author/", "/page/",
        "/actualite", "/actualites", "/news", "/blog", "/evenement", "/event", "/galerie",
        "/wp-content/", "?", "#", "mailto:", "tel:", "/en/", "/ar/",
    )
    max_pages: int = 150
    # False pour un site « vitrine » de groupe (NAU) : ses pages sont gardées pour le RAG, sans formations attendues
    expects_programs: bool = True
    extra_seeds: tuple[str, ...] = field(default_factory=tuple)


SITES: list[SiteSource] = [
    SiteSource(
        institution_code="IIT",
        institution_name="Institut International de Technologie",
        base_url="https://iit.tn/",
        program_url_hints=(
            "prepa", "licence", "filieres-ingenieur", "genie", "mastere", "architecture",
            "reseaux", "big-data", "systemes", "logiciel",
        ),
    ),
    SiteSource(
        institution_code="ISB",
        institution_name="International School of Business",
        city=None,
        base_url="https://isb.tn/",
        program_url_hints=("licence", "master", "mastere", "mba", "formation", "programme", "bachelor"),
    ),
    SiteSource(
        institution_code="ISA",
        institution_name="IIT Section of Architecture",
        base_url="https://isa.tn/",
        program_url_hints=("architecture", "formation", "programme", "cycle"),
    ),
    SiteSource(
        institution_code="2I2S",
        institution_name="2I2S — École Internationale des Sciences de Santé",
        city=None,
        base_url="https://2i2s.tn/",
        program_url_hints=("licence", "master", "mastere", "formation", "programme", "ingenieur", "bts"),
    ),
    SiteSource(
        institution_code="NAU",
        institution_name="North American Private University",
        city=None,
        expects_programs=False,  # nau.tn présente le groupe (IIT, ISB, ISA) : formations sur les sites des écoles
        base_url="https://nau.tn/",
        program_url_hints=("formation", "programme", "licence", "master", "mastere", "ingenieur", "mba"),
    ),
]


def get_site(code: str) -> SiteSource:
    for site in SITES:
        if site.institution_code == code.upper():
            return site
    raise KeyError(f"Site inconnu : {code}. Sites disponibles : {', '.join(s.institution_code for s in SITES)}")
