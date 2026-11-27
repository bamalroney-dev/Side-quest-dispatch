import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from research import disney_food_blog, gaming
from research.briefing import draft
from research.http import FetchError, Response
from research.storage import record_run

from test_collection import FixtureClient, NOW, fixture

POKEMON_HTML = b"""
<a href="/en/Items/Schedule/Pokemon-Trading-Card-Game">Pokemon Trading Card Game</a>
<a href="/en/releases/flowing-fists">Pokemon TCG: Flowing Fists</a>
<a href="/en/releases/flowing-fists">English</a>
"""
LUNA_HTML = b"""
<a href="/en-us/news/articles/luna-october-2026">Luna October Content Update</a>
<a href="/en-us/news/articles/luna-november-2026">Luna November Content Update</a>
<a href="/en-us/news/articles/luna-extra-2027">Luna Other News</a>
"""
OSRS_XML = b"""
<rss version="2.0"><channel><title>Old School RuneScape Recent News</title>
<item><title>Quest News</title>
<link>https://secure.runescape.com/m=news/a-quest?oldschool=1&amp;utm_medium=rss</link>
<pubDate>Wed, 25 Nov 2026 12:00:00 GMT</pubDate></item></channel></rss>
"""


class GamingTests(unittest.TestCase):
    def test_pokemon_reuses_discovery_and_keeps_review_status_when_one_page_fails(self):
        records, report = gaming.collect_pokemon(FixtureClient(FetchError("HTTP 503", 3, 503), POKEMON_HTML))
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(report["checks"][0]["http_status"], 503)
        self.assertEqual([record["title"] for record in records], ["Pokemon TCG: Flowing Fists"])
        self.assertEqual(records[0]["review_status"], "needs_verification")
        self.assertNotIn("offer_window", records[0])

    def test_luna_picks_latest_monthly_newsroom_announcement(self):
        records, report = gaming.collect_luna(FixtureClient(LUNA_HTML))
        self.assertEqual(report["status"], "ok")
        self.assertEqual([record["title"] for record in records], ["Luna November Content Update"])
        self.assertEqual(records[0]["review_status"], "needs_verification")

    def test_osrs_preserves_product_query_and_rejects_other_feeds(self):
        records, report = gaming.collect_osrs(FixtureClient(OSRS_XML))
        self.assertEqual(report["status"], "ok")
        self.assertTrue(records[0]["canonical_url"].endswith("/a-quest?oldschool=1"))
        self.assertEqual(records[0]["published_at"], "2026-11-25T12:00:00+00:00")
        _, report = gaming.collect_osrs(FixtureClient(fixture("original.xml")))
        self.assertEqual(report["status"], "failed")
        self.assertIn("Unexpected feed title", report["checks"][0]["error"])

    def test_epic_filters_nonzero_prices_expired_offers_and_addons(self):
        game = {
            "title": "Fixture Game", "offerType": "BASE_GAME", "productSlug": "fixture-game/home",
            "price": {"totalPrice": {"discountPrice": 0, "originalPrice": 1999, "currencyCode": "USD"}},
            "promotions": {"promotionalOffers": [{"promotionalOffers": [{
                "startDate": "2026-11-26T16:00:00Z", "endDate": "2026-12-03T16:00:00Z",
                "discountSetting": {"discountType": "PERCENTAGE", "discountPercentage": 0},
            }]}]},
        }
        paid = {**game, "price": {"totalPrice": {"discountPrice": 399, "originalPrice": 1999,
                                                  "currencyCode": "USD"}}}
        always_free = {**game, "price": {"totalPrice": {"discountPrice": 0, "originalPrice": 0,
                                                         "currencyCode": "USD"}}}
        other_currency = {**game, "price": {"totalPrice": {"discountPrice": 0, "originalPrice": 1999,
                                                            "currencyCode": "CAD"}}}
        wrongly_discounted = copy.deepcopy(game)
        wrongly_discounted["promotions"]["promotionalOffers"][0]["promotionalOffers"][0][
            "discountSetting"
        ]["discountPercentage"] = 25
        payload = {"data": {"Catalog": {"searchStore": {"elements": [
            game, paid, always_free, other_currency, wrongly_discounted, {**game, "offerType": "ADD_ON"},
        ]}}}}
        response = Response(json.dumps(payload).encode(), gaming.EPIC_URL, 1)
        current = datetime(2026, 11, 27, tzinfo=timezone.utc)
        records, skipped = gaming.epic_articles(response, "store_api", now=current)
        self.assertEqual(len(records), 1)
        self.assertEqual(skipped, 0)
        self.assertTrue(records[0]["canonical_url"].endswith("/en-US/p/fixture-game"))
        self.assertEqual(records[0]["offer_window"]["ends_at"], "2026-12-03T16:00:00+00:00")
        end = datetime(2026, 12, 3, 16, tzinfo=timezone.utc)
        self.assertEqual(gaming.epic_articles(response, "store_api", now=end), ([], 0))

    def test_epic_distinguishes_empty_offers_from_broken_payload(self):
        records, report = gaming.collect_epic(FixtureClient(
            b'{"data":{"Catalog":{"searchStore":{"elements":[]}}}}',
        ))
        self.assertEqual((records, report["status"]), ([], "ok"))
        _, report = gaming.collect_epic(FixtureClient(b'{"unexpected": true}'))
        self.assertEqual(report["status"], "failed")

    def test_history_retains_independent_source_success_and_deduplicates_across_sources(self):
        disney = disney_food_blog.collect(
            FixtureClient(FetchError("503", 1, 503), fixture("original.xml")),
        )
        pokemon = gaming.collect_pokemon(FixtureClient(FetchError("503", 1, 503), POKEMON_HTML))
        duplicate = {**disney[0][0], "source": gaming.POKEMON}
        pokemon = ([*pokemon[0], duplicate], pokemon[1])
        pokemon_down = gaming.collect_pokemon(FixtureClient(b"<html/>", b"<html/>"))
        later = "2026-11-26T16:00:00+00:00"
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            # Seed with the same single-source layout used by Phase 1.
            record_run(directory, NOW, [disney])
            record_run(directory, later, [disney, pokemon])
            snapshot, report = read_reports(directory)
            pokemon_health = report["sources"][1]
            self.assertEqual((pokemon_health["new"], pokemon_health["duplicates_in_run"]), (1, 1))
            self.assertEqual(len(snapshot["previously_seen_urls"]), 2)
            self.assertEqual(len(snapshot["articles"]), 3)
            self.assertIn("Open source", draft(snapshot, report))
            record_run(directory, "2026-11-26T17:00:00+00:00", [disney, pokemon_down])
            snapshot, report = read_reports(directory)
            self.assertEqual(report["sources"][1]["status"], "failed")
            self.assertEqual(report["sources"][1]["last_success_at"], later)
            self.assertEqual(len(snapshot["articles"]), 2)
            self.assertIn("No candidates in this snapshot", draft(snapshot, report))
            failed = disney_food_blog.collect(FixtureClient(b"<html/>", b"<html/>", b"<html/>"))
            epic_empty = gaming.collect_epic(FixtureClient(
                b'{"data":{"Catalog":{"searchStore":{"elements":[]}}}}',
            ))
            self.assertFalse(record_run(
                directory, "2026-11-26T18:00:00+00:00", [failed, pokemon_down, epic_empty],
            ))
            snapshot, report = read_reports(directory)
            with self.assertRaisesRegex(ValueError, "no current snapshot"):
                draft(snapshot, report)


def read_reports(directory):
    return tuple(json.loads((directory / name).read_text(encoding="utf-8"))
                 for name in ("latest.json", "source-health.json"))
