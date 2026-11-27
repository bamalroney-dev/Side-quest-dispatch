"""Verify briefing claims against source-specific public evidence."""

import re
import unicodedata
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

from jsonschema import ValidationError

from .gaming import EPIC, EPIC_API, EPIC_URL, LUNA, POKEMON, epic_articles
from .http import FetchError
from .models import validate_article

POKEMON_SCHEDULE = "https://press.pokemon.com/en/Items/Schedule/Trading-Card-Game"
LUNA_CLAIMS = "https://gaming.amazon.com/"


def briefing_candidates(snapshot, report):
    run_id = snapshot["run_id"]
    if run_id is None or run_id != report["run_id"] or run_id != report["snapshot_run_id"]:
        raise ValueError("Latest attempt has no current snapshot. Check source-health.json.")

    articles_by_source = {}
    for article in snapshot["articles"]:
        validate_article(article)
        articles_by_source.setdefault(article["source"], []).append(article)
    seen = set(snapshot["previously_seen_urls"])
    return {
        source["source"]: sorted(
            articles_by_source.get(source["source"], ()),
            key=lambda article: (article["canonical_url"] not in seen, article["published_at"] or ""),
            reverse=True,
        )[:3]
        for source in report["sources"]
    }


class ReleaseSchedule(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = {}
        self.column = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = {}
        if tag == "td":
            classes = (dict(attrs).get("class") or "").split()
            self.column = next((name for name in classes if name in {"td-prod", "td-date"}), None)
            if self.column:
                self.row[self.column] = []

    def handle_data(self, data):
        if self.column:
            self.row[self.column].append(data)

    def handle_endtag(self, tag):
        if tag == "td":
            self.column = None
        if tag == "tr" and {"td-prod", "td-date"} <= self.row.keys():
            self.rows.append(tuple(" ".join("".join(self.row[name]).split())
                                   for name in ("td-prod", "td-date")))


def words(text):
    folded = unicodedata.normalize("NFKD", text.casefold())
    return " ".join(re.findall(r"[a-z0-9]+", "".join(c for c in folded if not unicodedata.combining(c))))


def release_rows(response):
    table = ReleaseSchedule()
    table.feed(response.body.decode("utf-8", errors="replace"))
    table.close()
    rows = [(title, date) for title, date in table.rows if words(title).startswith("pokemon tcg ")]
    if not rows:
        raise ValueError("No TCG product rows in the publisher schedule")
    return rows


def verified(value, evidence_url):
    return {"status": "verified", "value": value, "evidence_url": evidence_url}


def held(reason, evidence_url, status="unverified"):
    return {"status": status, "reason": reason, "evidence_url": evidence_url}


def pokemon_claims(article, rows, evidence_url):
    title = words(article["title"])
    products = [(name, date, words(name).removeprefix("pokemon tcg ")) for name, date in rows]
    matches = {
        (name, date) for name, date, product in products
        if re.search(rf"(?:^| ){re.escape(product)}(?= expansion\b| arrives\b| arriving\b|$)", title)
    }
    claims = {
        "release_date": held("No unique matching product and full date in the schedule", evidence_url),
        "msrp": held("The release schedule does not publish a product MSRP", evidence_url),
    }
    if len(matches) != 1:
        return {"claims": claims}
    product, raw_date = next(iter(matches))
    try:
        date = datetime.strptime(raw_date, "%B %d, %Y").date()
    except ValueError:
        return {"claims": claims}
    # An explicit date in the collected headline must agree with the schedule.
    headline_dates = re.findall(r"\b[A-Za-z]+ \d{1,2}, \d{4}\b", article["title"])
    for headline_date in headline_dates:
        try:
            if datetime.strptime(headline_date, "%B %d, %Y").date() != date:
                claims["release_date"] = held("Headline and publisher schedule disagree", evidence_url, "conflict")
                return {"subject": product, "claims": claims}
        except ValueError:
            continue
    claims["release_date"] = verified(date.isoformat(), evidence_url)
    return {"subject": product, "claims": claims}


def epic_offers(response, now):
    records, skipped = epic_articles(response, "store_api", now=now)
    if skipped and not records:
        raise ValueError("No usable offers in the storefront response")
    return records


def epic_claims(article, offers, evidence_url):
    matches = [offer for offer in offers if offer["canonical_url"] == article["canonical_url"]]
    window = article.get("offer_window")
    if not matches or not window:
        finding = held("No active matching U.S. storefront offer", evidence_url)
        return {"claims": {"current_price": finding, "claim_deadline": finding}}
    if any(offer["offer_window"] != window for offer in matches):
        finding = held("Collected window and current U.S. storefront data disagree", evidence_url, "conflict")
        return {"claims": {"current_price": finding, "claim_deadline": finding}}
    return {"subject": matches[0]["title"], "claims": {
        "current_price": verified({"amount_cents": 0, "currency": "USD", "market": "US"}, evidence_url),
        "claim_deadline": verified(window["ends_at"], evidence_url),
    }}


def check_source(client, articles, source, url, accept, parse, check_claims, claim_names):
    if not articles:
        return {}
    try:
        response = client.get(url, source=source, hosts={urlsplit(url).hostname}, accept=accept)
        parsed = parse(response)
    except (FetchError, ValueError, ValidationError) as exc:
        return {article["canonical_url"]: {"claims": {
            name: held(str(exc), url, "unavailable") for name in claim_names
        }} for article in articles}
    return {article["canonical_url"]: check_claims(article, parsed, response.url) for article in articles}


def verify(snapshot, report, client, now):
    candidates = briefing_candidates(snapshot, report)
    articles = check_source(client, candidates.get(POKEMON), POKEMON, POKEMON_SCHEDULE, "text/html",
                            release_rows, pokemon_claims, ("release_date", "msrp"))
    articles.update(check_source(
        client, candidates.get(EPIC), EPIC, EPIC_URL, "application/json",
        lambda response: epic_offers(response, now), epic_claims, ("current_price", "claim_deadline"),
    ))
    for article in candidates.get(LUNA, ()):
        finding = held("Check the account and region-specific claims page", LUNA_CLAIMS)
        articles[article["canonical_url"]] = {"claims": {
            "current_price": finding, "claim_deadline": finding,
        }}
    return {
        "schema_version": 1, "run_id": snapshot["run_id"],
        "collected_at": snapshot["collected_at"], "checked_at": now.isoformat(),
        "articles": articles,
    }
