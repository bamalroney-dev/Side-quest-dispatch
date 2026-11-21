#!/usr/bin/env python3
"""Discover Pokémon TCG announcement candidates from official Pokémon pages.

This deliberately produces a REVIEW QUEUE, not published product data. News
headlines are not enough to infer SKU, release date, variant or MSRP.
"""
import argparse
import datetime as dt
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "_data/pokemon_tcg_releases.json"
QUEUE = ROOT / "data/pokemon-tcg-review-queue.json"
SOURCES = (
    "https://www.pokemon.com/us/pokemon-news",
    "https://press.pokemon.com/en",
)
KEYWORDS = re.compile(r"pokemon.tc[g]|trading.card.game|mega.evolution|elite.trainer.box|booster.bundle", re.I)
MAX_BYTES = 2_000_000

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.href = None
        self.text = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.text = []
    def handle_data(self, value):
        if self.href is not None:
            self.text.append(value)
    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            self.links.append((self.href, " ".join(self.text).strip()))
            self.href = None
            self.text = []

def normalize_url(base, href):
    url = urllib.parse.urljoin(base, html.unescape(href))
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in {"www.pokemon.com", "pokemon.com", "press.pokemon.com"}:
        return None
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))

def candidates_from_html(base, document):
    parser = Links()
    parser.feed(document)
    candidates = []
    for href, title in parser.links:
        url = normalize_url(base, href)
        if not url or not title or not KEYWORDS.search(title + " " + url):
            continue
        if url.rstrip("/") == base.rstrip("/"):
            continue
        candidates.append({"title": re.sub(r"\\s+", " ", title).strip(), "source_url": url,
                           "release_date": None, "msrp_usd": None,
                           "msrp_verified": False, "review_status": "needs_verification"})
    return candidates

def deduplicate(candidates, existing):
    known_urls = {p.get("source", "").rstrip("/") for p in existing}
    seen = set()
    result = []
    for item in candidates:
        key = item["source_url"].rstrip("/")
        if key in known_urls or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return sorted(result, key=lambda x: (x["title"].lower(), x["source_url"]))

def validate_dataset(data):
    ids = set()
    for p in data["products"]:
        assert p.get("id") and p["id"] not in ids, "Duplicate or missing product id"
        ids.add(p["id"])
        assert p.get("source", "").startswith("https://"), "Official source URL required"
        assert p.get("msrp_usd") is None or p.get("msrp_verified") is True, "Unverified MSRP"
        assert p.get("reference_price_usd") is None or p.get("reference_price_source"), "Reference price missing source"
        date = p.get("release_date", p.get("date", ""))
        assert re.fullmatch(r"\\d{4}-\\d{2}(-\\d{2})?", date), "Invalid release date"
        if len(date) == 10:
            dt.date.fromisoformat(date)

def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "SideQuestDispatch/1.0 (editorial discovery)"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read(MAX_BYTES).decode("utf-8", errors="replace")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    data = json.loads(DATA.read_text())
    validate_dataset(data)
    discovered = []
    errors = []
    for url in SOURCES:
        try:
            discovered.extend(candidates_from_html(url, fetch(url)))
        except Exception as exc:
            errors.append({"source": url, "error_type": type(exc).__name__})
    if len(errors) == len(SOURCES):
        raise SystemExit("All official discovery sources failed; queue unchanged")
    current = json.loads(QUEUE.read_text()) if QUEUE.exists() else {"candidates": []}
    previous = current.get("candidates", [])
    combined = deduplicate(previous + discovered, data["products"])
    result = {"schema_version": 1, "candidates": combined}
    print(json.dumps({"new_candidates": len(combined) - len(previous), "total_candidates": len(combined),
                      "source_errors": errors}, indent=2))
    if not args.dry_run:
        QUEUE.parent.mkdir(parents=True, exist_ok=True)
        QUEUE.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\\n")

if __name__ == "__main__":
    main()
