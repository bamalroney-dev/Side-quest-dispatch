"""Common normalization for public listings and RSS feeds."""

import logging
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin

import feedparser
from jsonschema import ValidationError

from .models import canonical_url, validate_article

LOG = logging.getLogger(__name__)


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


def article(source, hosts, title, url, method, published_at=None, summary="", **metadata):
    return validate_article({
        "source": source,
        "title": plain_text(title, 300),
        "canonical_url": canonical_url(url, hosts),
        "published_at": published_at,
        "summary": plain_text(summary, 500),
        "collection_method": method,
        **metadata,
    })


def rss_articles(response, method, *, source, hosts, expected_title=None):
    # Pass bytes so the shared HTTP client owns transport.
    feed = feedparser.parse(response.body, response_headers={
        "content-location": response.url,
        "content-type": "application/xml",
    })
    if feed.bozo or not feed.version.startswith("rss"):
        detail = type(feed.bozo_exception).__name__ if feed.bozo else "wrong feed format"
        raise ValueError(f"Invalid RSS: {detail}")
    if expected_title and expected_title.casefold() not in feed.feed.get("title", "").casefold():
        raise ValueError(f"Unexpected feed title for {source}")

    records, skipped = [], 0
    for entry in feed.entries:
        try:
            published = entry.get("published_parsed")
            published_at = datetime(*published[:6], tzinfo=timezone.utc).isoformat() if published else None
            link = entry.get("feedburner_origlink") or entry.get("link", "")
            if not link:
                raise ValueError("Missing article URL")
            records.append(article(source, hosts, entry.get("title", ""), urljoin(response.url, link),
                                   method, published_at, entry.get("summary", "")))
        except (ValueError, ValidationError) as exc:
            skipped += 1
            LOG.debug("%s skipped invalid RSS article: %s", source, exc)
    return records, skipped
