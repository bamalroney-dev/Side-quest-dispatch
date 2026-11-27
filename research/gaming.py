"""Official gaming announcements and store promotions."""

import json
import re
from calendar import month_name
from datetime import datetime, timezone
from functools import partial
from urllib.parse import urljoin, urlsplit

from jsonschema import ValidationError

from scripts.editorial import timestamp
from scripts.pokemon_tcg_discovery import Links, SOURCES as POKEMON_URLS, candidates_from_html
from scripts.source_registry import FEEDS

from .checks import collect_endpoints
from .parsing import article, rss_articles

POKEMON = "Pokémon TCG"
POKEMON_HOSTS = {"www.pokemon.com": "www.pokemon.com", "pokemon.com": "www.pokemon.com",
                 "press.pokemon.com": "press.pokemon.com"}
OSRS = "Old School RuneScape"
OSRS_URL = FEEDS[OSRS][0][1]
OSRS_HOSTS = {"secure.runescape.com": "secure.runescape.com",
              "oldschool.runescape.com": "oldschool.runescape.com"}
LUNA = "Amazon Luna (Prime Gaming)"
LUNA_HOST = "www.amazongamestudios.com"
LUNA_URL = f"https://{LUNA_HOST}/en-us/news/"
LUNA_PATH = re.compile(r"/en-us/news/articles/luna-([a-z]+)-(\d{4})/?")
MONTHS = {name.lower(): number for number, name in enumerate(month_name) if name}
EPIC = "Epic Games Store"
EPIC_API = "store-site-backend-static.ak.epicgames.com"
EPIC_URL = f"https://{EPIC_API}/freeGamesPromotions?locale=en-US&country=US&allowCountries=US"
EPIC_STORE = "store.epicgames.com"
EPIC_SLUG = re.compile(r"[a-z0-9][a-z0-9-]*")


def pokemon_articles(response, method):
    records, skipped = [], 0
    for candidate in candidates_from_html(response.url, response.body.decode("utf-8", errors="replace")):
        url = candidate["source_url"]
        parts = urlsplit(url)
        # The existing discovery parser also matches navigation and asset links.
        if parts.hostname == "press.pokemon.com":
            if not re.fullmatch(r"/en/(?:releases/)?[^/]+", parts.path) or candidate["title"] == "English":
                continue
        elif not re.fullmatch(r"/us/(?:pokemon-news|news)/[^/]+", parts.path):
            continue
        try:
            records.append(article(POKEMON, POKEMON_HOSTS, candidate["title"], url, method,
                                   review_status=candidate["review_status"]))
        except (ValueError, ValidationError):
            skipped += 1
    return records, skipped


def collect_pokemon(client):
    return collect_endpoints(client, POKEMON, "website", POKEMON_URLS, POKEMON_HOSTS,
                             "text/html", pokemon_articles)


def collect_osrs(client):
    parse = partial(rss_articles, source=OSRS, hosts=OSRS_HOSTS, expected_title=OSRS)
    return collect_endpoints(client, OSRS, "rss", (OSRS_URL,), OSRS_HOSTS,
                             "application/rss+xml, application/xml, text/xml", parse)


def luna_articles(response, method):
    links = Links()
    links.feed(response.body.decode("utf-8", errors="replace"))
    links.close()
    updates, skipped = [], 0
    for href, title in links.links:
        if not re.fullmatch(r"Luna .+ Content Update", title.strip(), re.IGNORECASE):
            continue
        url = urljoin(response.url, href)
        match = LUNA_PATH.fullmatch(urlsplit(url).path)
        if not match or match[1] not in MONTHS:
            continue
        try:
            record = article(LUNA, {LUNA_HOST: LUNA_HOST}, title, url, method,
                             review_status="needs_verification")
        except (ValueError, ValidationError):
            skipped += 1
            continue
        updates.append(((int(match[2]), MONTHS[match[1]]), record))
    newest = max(updates, key=lambda update: update[0])[1] if updates else None
    return [newest] if newest else [], skipped


def collect_luna(client):
    return collect_endpoints(client, LUNA, "website", (LUNA_URL,), {LUNA_HOST},
                             "text/html", luna_articles)


def epic_slug(item):
    for mapping in (item.get("catalogNs") or {}).get("mappings") or []:
        slug = mapping.get("pageSlug") or ""
        if mapping.get("pageType") == "productHome" and EPIC_SLUG.fullmatch(slug):
            return slug
    slug = (item.get("productSlug") or "").removesuffix("/home")
    if EPIC_SLUG.fullmatch(slug):
        return slug
    raise ValueError("Offer has no usable storefront path")


def epic_window(item, now):
    promotions = item.get("promotions") or {}
    total_price = (item.get("price") or {}).get("totalPrice") or {}
    if total_price.get("discountPrice") != 0 or total_price.get("originalPrice", 0) <= 0:
        return None
    for group in promotions.get("promotionalOffers") or []:
        for offer in group["promotionalOffers"]:
            discount = offer.get("discountSetting") or {}
            if discount.get("discountType") != "PERCENTAGE" or discount.get("discountPercentage") != 0:
                continue
            starts, ends = timestamp(offer["startDate"]), timestamp(offer["endDate"])
            if starts <= now < ends:
                return {"starts_at": starts.isoformat(), "ends_at": ends.isoformat(), "market": "US"}
    return None


def epic_articles(response, method, *, now):
    try:
        offers = json.loads(response.body)["data"]["Catalog"]["searchStore"]["elements"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Unexpected Epic storefront response") from exc
    if not isinstance(offers, list):
        raise ValueError("Unexpected Epic storefront offers")
    records, skipped = [], 0
    for item in offers:
        try:
            if item.get("offerType") != "BASE_GAME":
                continue
            window = epic_window(item, now)
            if window:
                records.append(article(EPIC, {EPIC_STORE: EPIC_STORE}, item["title"],
                                       f"https://{EPIC_STORE}/en-US/p/{epic_slug(item)}", method,
                                       review_status="needs_verification", offer_window=window))
        except (AttributeError, KeyError, TypeError, ValueError, ValidationError):
            skipped += 1
    return records, skipped


def collect_epic(client):
    parse = partial(epic_articles, now=datetime.now(timezone.utc))
    return collect_endpoints(client, EPIC, "store_api", (EPIC_URL,), {EPIC_API},
                             "application/json", parse, allow_empty=True)
