"""Disney Food Blog collection in publisher fallback order."""

import logging
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import feedparser
from jsonschema import ValidationError

from scripts.pokemon_tcg_discovery import Links

from .http import FetchError
from .models import canonical_url, validate_article

LOG = logging.getLogger(__name__)
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


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {"p", "br", "li", "div"}:
            self.parts.append(" ")


def plain_text(markup, limit):
    parser = PlainText()
    parser.feed(markup)
    parser.close()
    return " ".join("".join(parser.parts).split())[:limit].strip()


def article(title, url, method, published_at=None, summary=""):
    return validate_article({
        "source": SOURCE,
        "title": plain_text(title, 300),
        "canonical_url": canonical_url(url, HOST_ALIASES),
        "published_at": published_at,
        "summary": plain_text(summary, 500),
        "collection_method": method,
    })


def rss_articles(response, method):
    # The HTTP client owns transport. Passing bytes prevents feedparser from fetching.
    feed = feedparser.parse(response.body, response_headers={
        "content-location": response.url,
        "content-type": "application/xml",
    })
    if feed.bozo or not feed.version.startswith("rss"):
        detail = type(feed.bozo_exception).__name__ if feed.bozo else "wrong feed format"
        raise ValueError(f"Invalid RSS: {detail}")

    records, skipped = [], 0
    for entry in feed.entries:
        try:
            published = entry.get("published_parsed")
            published_at = datetime(*published[:6], tzinfo=timezone.utc).isoformat() if published else None
            link = entry.get("feedburner_origlink") or entry.get("link", "")
            if not link:
                raise ValueError("Missing article URL")
            records.append(article(entry.get("title", ""), urljoin(response.url, link),
                                   method, published_at, entry.get("summary", "")))
        except (ValueError, ValidationError) as exc:
            skipped += 1
            LOG.debug("%s skipped invalid RSS article: %s", SOURCE, exc)
    return records, skipped


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
            record = article(title, url, method)
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
        check = {"method": method, "url": url, "attempts": 0, "skipped": 0}
        checks.append(check)
        try:
            response = client.get(
                url, source=SOURCE, hosts=set(HOST_ALIASES) | {"feeds.feedburner.com"},
                accept="text/html" if method == "website" else "application/rss+xml, application/xml, text/xml",
            )
            check.update(attempts=response.attempts, final_url=response.url)
            parse = website_articles if method == "website" else rss_articles
            records, skipped = parse(response, method)
            check["skipped"] = skipped
            if not records:
                raise ValueError("No valid articles found")
        except FetchError as exc:
            check.update(attempts=exc.attempts, http_status=exc.status, error=str(exc), stage="fetch")
        except ValueError as exc:
            check.update(error=str(exc), stage="parse")
        else:
            check["status"] = "ok"
            return records, {
                "source": SOURCE, "status": "ok" if method == "feedburner" and not skipped else "degraded",
                "method": method, "checks": checks,
            }
        check["status"] = "failed"
        LOG.warning("%s %s failed: %s", SOURCE, method, check["error"])
    return [], {"source": SOURCE, "status": "failed", "method": None, "checks": checks}
