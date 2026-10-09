"""Validate a built MkDocs site without network access or extra dependencies."""

from __future__ import annotations

import gzip
import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

SITE_URL = "https://pooyanazad.github.io/kube-saver/"
REPOSITORY = "https://github.com/pooyanazad/kube-saver"


class Page(HTMLParser):
    """Collect rendered metadata, navigation targets and anchors."""

    def __init__(self, html: str) -> None:
        super().__init__()
        self.title = ""
        self.in_title = False
        self.headings = 0
        self.meta: dict[str, str] = {}
        self.canonicals: list[str] = []
        self.links: list[str] = []
        self.assets: list[str] = []
        self.ids: set[str] = set()
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(str(values["id"]))
        if tag == "title":
            self.in_title = True
        if tag == "h1":
            self.headings += 1
        if tag == "meta" and values.get("name"):
            self.meta[str(values["name"])] = values.get("content") or ""
        if tag == "link" and values.get("rel") == "canonical":
            self.canonicals.append(values.get("href") or "")
        attribute = "href" if tag in {"a", "link"} else "src"
        if tag in {"a", "link", "img", "script"} and values.get(attribute):
            self.links.append(str(values[attribute]))
            if tag in {"img", "script"} or values.get("rel") == "stylesheet":
                self.assets.append(str(values[attribute]))

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data


def validate(site: Path) -> None:
    """Check crawlable pages, assets, metadata, search and sitemap consistency."""
    errors: list[str] = []
    pages: dict[str, Page] = {}
    for path in site.rglob("*.html"):
        name = path.relative_to(site).as_posix()
        html = path.read_text(encoding="utf-8")
        if re.fullmatch(r"google[0-9a-f]+\.html", name):
            # Google supplies this static file after owner authentication.
            # It is not a content page and must retain Google's exact body.
            if html.strip() != f"google-site-verification: {name}":
                errors.append(f"{name}: invalid Search Console verification file")
            continue
        pages[name] = Page(html)
    canonicals: set[str] = set()
    titles: set[str] = set()
    descriptions: set[str] = set()
    checked_links = 0
    for name, page in pages.items():
        if name == "404.html":
            continue
        relative_url = name.removesuffix("index.html")
        expected = urljoin(SITE_URL, relative_url)
        if page.canonicals != [expected]:
            errors.append(f"{name}: canonical must be {expected}")
        canonicals.add(expected)
        if not page.title.strip() or page.title in titles:
            errors.append(f"{name}: missing or duplicate title")
        titles.add(page.title)
        description = page.meta.get("description", "")
        if not description or description in descriptions:
            errors.append(f"{name}: missing or duplicate description")
        descriptions.add(description)
        if "width=device-width" not in page.meta.get("viewport", ""):
            errors.append(f"{name}: missing mobile viewport")
        if "noindex" in page.meta.get("robots", "").lower():
            errors.append(f"{name}: unexpected noindex")
        if page.headings != 1:
            errors.append(f"{name}: expected one main heading")
        for asset in page.assets:
            if urlsplit(urljoin(expected, asset)).netloc != urlsplit(SITE_URL).netloc:
                errors.append(f"{name}: external runtime asset: {asset}")
        for link in page.links:
            target = urlsplit(urljoin(expected, link))
            if target.scheme not in {"http", "https"}:
                continue
            if target.netloc != urlsplit(SITE_URL).netloc:
                # Navigation may link to GitHub; styles/scripts must be local.
                continue
            if not target.path.startswith("/kube-saver/"):
                errors.append(f"{name}: link escapes project path: {link}")
                continue
            checked_links += 1
            relative = unquote(target.path.removeprefix("/kube-saver/"))
            destination = site / relative
            if destination.is_dir():
                destination /= "index.html"
            if not destination.is_file():
                errors.append(f"{name}: missing local target: {link}")
                continue
            key = destination.relative_to(site).as_posix()
            if target.fragment and key in pages and unquote(target.fragment) not in pages[key].ids:
                errors.append(f"{name}: missing anchor: {link}")

    sitemap = (site / "sitemap.xml").read_bytes()
    locations = [
        str(element.text)
        for element in ET.fromstring(sitemap).iter(
            "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
        )
    ]
    if len(locations) != len(set(locations)) or set(locations) != canonicals:
        errors.append("sitemap must contain exactly the canonical content URLs")
    with gzip.open(site / "sitemap.xml.gz", "rb") as compressed:
        if compressed.read() != sitemap:
            errors.append("compressed sitemap differs from XML sitemap")
    robots = (site / "robots.txt").read_text()
    if "Disallow:" in robots or f"Sitemap: {SITE_URL}sitemap.xml" not in robots:
        errors.append("project robots.txt has unexpected crawl rules or sitemap")
    if (site / "maintenance").exists() or (site / "screenshots/pr-plan").exists():
        errors.append("maintainer records/historical executable plans leaked into site")
    search = json.loads((site / "search/search_index.json").read_text())
    if not search.get("docs"):
        errors.append("empty local search index")
    home = pages.get("index.html")
    if home is None or REPOSITORY not in home.links:
        errors.append("homepage missing GitHub repository link")
    if home is None or f"{REPOSITORY}/blob/main/CONTRIBUTING.md" not in home.links:
        errors.append("homepage missing contribution guide")
    for name in ("faq/index.html", "safety/index.html", "gitops/index.html"):
        if name not in pages:
            errors.append(f"missing priority guide: {name}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(
        f"PASS: {len(canonicals)} canonical pages, unique titles/descriptions, "
        f"{checked_links} internal links/assets/anchors, XML/gzip sitemap, "
        "project robots.txt, mobile viewport and local search index"
    )
    print("Host-root robots policy and live indexing require post-deployment checks.")


if __name__ == "__main__":
    validate(Path(sys.argv[1] if len(sys.argv) > 1 else "site"))
