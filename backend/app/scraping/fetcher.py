"""Collecte polie des pages : respecte robots.txt, limite le débit, découvre les pages par sitemap
puis par liens internes. Toute la partie réseau passe par `HttpGetter` pour pouvoir être simulée en test.
"""
import re
import time
import urllib.robotparser
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.scraping.sources import SiteSource

USER_AGENT = "SmartCampusAI-bot/0.1 (projet academique IIT Sfax; synchronisation du catalogue des formations)"
SITEMAP_CANDIDATES = ("wp-sitemap.xml", "sitemap_index.xml", "sitemap.xml", "page-sitemap.xml")


@dataclass
class FetchResult:
    url: str
    status: int
    html: str


# (url) -> (status, body). Implémentation réelle ci-dessous ; les tests fournissent un faux.
HttpGetter = Callable[[str], tuple[int, str]]


def make_http_getter(timeout: float = 20.0, delay_s: float = 1.0) -> HttpGetter:
    client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True)
    last_call = [0.0]

    def get(url: str) -> tuple[int, str]:
        wait = delay_s - (time.monotonic() - last_call[0])
        if wait > 0:
            time.sleep(wait)  # au maximum 1 requête par seconde : on ne surcharge pas les sites
        last_call[0] = time.monotonic()
        try:
            r = client.get(url)
            return r.status_code, r.text
        except httpx.HTTPError as exc:
            return 0, f"{exc.__class__.__name__}: {exc}"

    return get


def normalize(url: str) -> str:
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    path = parsed.path or "/"
    if not path.endswith("/") and "." not in path.rsplit("/", 1)[-1]:
        path += "/"
    return f"{parsed.scheme}://{parsed.netloc.lower().removeprefix('www.')}{path}"


def same_site(url: str, site: SiteSource) -> bool:
    return urlparse(url).netloc.lower().removeprefix("www.") == urlparse(site.base_url).netloc.lower().removeprefix("www.")


def allowed_url(url: str, site: SiteSource) -> bool:
    lowered = url.lower()
    if not same_site(url, site) or any(part in lowered for part in site.exclude_url_parts):
        return False
    return not re.search(r"\.(pdf|jpe?g|png|gif|svg|webp|zip|docx?|xlsx?|pptx?|mp4|css|js)$", lowered)


class SiteCrawler:
    def __init__(self, site: SiteSource, http_get: HttpGetter):
        self.site = site
        self.get = http_get
        self.robots = urllib.robotparser.RobotFileParser()
        status, body = self.get(urljoin(site.base_url, "robots.txt"))
        self.robots.parse(body.splitlines() if status == 200 else [])
        self.errors: list[str] = []
        self.cache: dict[str, FetchResult] = {}

    def can_fetch(self, url: str) -> bool:
        return self.robots.can_fetch(USER_AGENT, url)

    def fetch(self, url: str) -> FetchResult:
        if url in self.cache:
            return self.cache[url]
        if not self.can_fetch(url):
            return FetchResult(url, 403, "")  # interdit par robots.txt : on n'insiste pas
        status, body = self.get(url)
        self.cache[url] = FetchResult(url, status, body)
        return self.cache[url]

    # ------------------------------------------------------------------ découverte
    def _sitemap_urls(self) -> list[str]:
        found: list[str] = []
        queue = deque(urljoin(self.site.base_url, c) for c in SITEMAP_CANDIDATES)
        queue.extend(self.robots.site_maps() or [])
        seen: set[str] = set()
        while queue and len(seen) < 30:
            sm = queue.popleft()
            if sm in seen:
                continue
            seen.add(sm)
            status, body = self.get(sm)
            if status != 200 or "<loc>" not in body:
                continue
            for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body):
                (queue if loc.endswith(".xml") else found).append(loc)
        return [normalize(u) for u in found if allowed_url(u, self.site)]

    def discover(self) -> list[str]:
        """Liste des pages du site : sitemap si disponible, sinon parcours des liens (profondeur 2)."""
        pages = list(dict.fromkeys(self._sitemap_urls()))
        start = [normalize(self.site.base_url), *map(normalize, self.site.extra_seeds)]
        if pages:
            return list(dict.fromkeys(start + pages))[: self.site.max_pages]

        seen: dict[str, None] = {}
        queue = deque((u, 0) for u in start)
        while queue and len(seen) < self.site.max_pages:
            url, depth = queue.popleft()
            if url in seen or not allowed_url(url, self.site):
                continue
            seen[url] = None
            if depth >= 2:
                continue
            res = self.fetch(url)
            if res.status != 200:
                if res.status == 0:
                    self.errors.append(f"{url} : {res.html}")
                continue
            soup = BeautifulSoup(res.html, "html.parser")
            for a in soup.find_all("a", href=True):
                link = normalize(urljoin(url, a["href"]))
                if link not in seen and allowed_url(link, self.site):
                    queue.append((link, depth + 1))
        return list(seen)

    def program_candidates(self, urls: list[str]) -> list[str]:
        """Pages à analyser en priorité : celles dont l'URL ressemble à une formation, puis les autres."""
        hinted = [u for u in urls if any(h in u.lower() for h in self.site.program_url_hints)]
        others = [u for u in urls if u not in hinted]
        return hinted + others
