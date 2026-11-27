"""Shared JSON record validation and URL normalization."""

import json
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from jsonschema import Draft202012Validator, FormatChecker

from scripts.editorial import timestamp, valid_https

FORMATS = FormatChecker()
SCHEMA = json.loads(Path(__file__).with_name("article.schema.json").read_text(encoding="utf-8"))


@FORMATS.checks("source-url", raises=ValueError)
def source_url(value):
    return isinstance(value, str) and valid_https(value) and urlsplit(value).hostname is not None


@FORMATS.checks("utc-timestamp", raises=ValueError)
def utc_timestamp(value):
    return value is None or (
        isinstance(value, str) and timestamp(value).isoformat() == value
    )


VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FORMATS)


def validate_article(article):
    VALIDATOR.validate(article)
    return article


def canonical_url(url, host_aliases):
    parts = urlsplit(url)
    if (
        parts.scheme not in ("http", "https") or parts.hostname not in host_aliases
        or parts.username is not None or parts.port not in (None, 443 if parts.scheme == "https" else 80)
    ):
        raise ValueError("Article URL is outside the publisher's hosts")
    query = urlencode(sorted(
        (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"fbclid", "gclid", "mc_cid", "mc_eid"}
    ))
    return urlunsplit(("https", host_aliases[parts.hostname],
                       parts.path.rstrip("/") or "/", query, ""))
