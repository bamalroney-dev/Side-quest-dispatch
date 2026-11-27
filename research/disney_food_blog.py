"""Disney Food Blog collection in publisher fallback order."""

import re
from functools import partial
from urllib.parse import urljoin, urlsplit

from jsonschema import ValidationError

from scripts.pokemon_tcg_discovery import Links

from .checks import check_endpoint
from .parsing import article, rss_articles

SOURCE = "Disney Food Blog"
PUBLISHER = "www.disneyfoodblog.com"
HOST_ALIASES = {PUBLISHER: PUBLISHER, "disneyfoodblog.com": PUBLISHER}
ENDPOINTS = (
    ("feedburner", "https://feeds.feedburner.com/disneyfoodblog/feed"),
    ("original_rss", f"https://{PUBLISHER}/feed/"),
    ("website", f"https://{PUBLISHER}/the-latest/"),
)
POST_PATH = re.compile(r"/\d{4}/\d{2}/\d{2}/[^/]+/?")
ARTICLE_LIMIT = 30


def website_articles(response, method):
    page = Links()
    page.feed(response.body.decode("utf-8", errors="replace"))
    page.close()
    records, skipped, seen = [], 0, set()
    for href, title in page.links:
        try:
            url = urljoin(response.url, href)
            if not POST_PATH.fullmatch(urlsplit(url).path) or title.lower() in {
                "", "read more", "continue reading", "read more »",
            }:
                continue
            record = article(SOURCE, HOST_ALIASES, title, url, method)
        except (ValueError, ValidationError):
            skipped += 1
            continue
        if record["canonical_url"] not in seen:
            seen.add(record["canonical_url"])
            records.append(record)
        if len(records) == ARTICLE_LIMIT:
            break
    return records, skipped


def collect(client):
    checks = []
    for method, url in ENDPOINTS:
        is_website = method == "website"
        if is_website:
            parse = website_articles
            accept = "text/html"
        else:
            parse = partial(rss_articles, source=SOURCE, hosts=HOST_ALIASES)
            accept = "application/rss+xml, application/xml, text/xml"
        records, check = check_endpoint(
            client, SOURCE, method, url, set(HOST_ALIASES) | {"feeds.feedburner.com"}, accept, parse,
        )
        checks.append(check)
        if check["status"] == "ok":
            return records, {
                "source": SOURCE, "status": "ok" if method == "feedburner" and not check["skipped"] else "degraded",
                "method": method, "checks": checks,
            }
    return [], {"source": SOURCE, "status": "failed", "method": None, "checks": checks}
