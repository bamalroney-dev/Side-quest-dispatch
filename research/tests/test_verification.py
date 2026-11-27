import json
import unittest
from datetime import datetime, timezone

from research import gaming
from research.briefing import draft
from research.http import FetchError
from research.verification import POKEMON_SCHEDULE, verify

from test_collection import FixtureClient

NOW = datetime(2026, 11, 27, tzinfo=timezone.utc)
DEADLINE = "2026-12-03T16:00:00+00:00"
GAME_URL = "https://store.epicgames.com/en-US/p/fixture-game"
TCG_URL = "https://www.pokemon.com/us/news/fixture-expansion"
LUNA_URL = "https://www.amazongamestudios.com/en-us/news/articles/luna-november-2026"
SCHEDULE = b"""
<table><tr><td class="td-prod"><a>Pok&#233;mon TCG: Mega Evolution &ndash; Fixture Expansion</a></td>
<td class="td-plat"> </td><td class="td-date">February 6, 2027</td></tr>
<tr><td class="td-prod">Pokemon TCG: Mega Evolution</td><td class="td-date">September 26, 2025</td></tr>
<tr><td class="td-prod">Pokemon TCG: Other Expansion</td><td class="td-date">2027</td></tr></table>
"""


def storefront(end=DEADLINE):
    return json.dumps({"data": {"Catalog": {"searchStore": {"elements": [{
        "title": "Fixture Game", "offerType": "BASE_GAME", "productSlug": "fixture-game/home",
        "price": {"totalPrice": {"discountPrice": 0, "originalPrice": 1999, "currencyCode": "USD"}},
        "promotions": {"promotionalOffers": [{"promotionalOffers": [{
            "startDate": "2026-11-26T16:00:00Z", "endDate": end,
            "discountSetting": {"discountType": "PERCENTAGE", "discountPercentage": 0},
        }]}]},
    }]}}}}).encode()


def candidate(source, url, title, **extra):
    return {"source": source, "canonical_url": url, "title": title, "summary": "Unverified $99.99",
            "published_at": None, "collection_method": "website",
            "review_status": "needs_verification", **extra}


def inputs(tcg_date="February 6, 2027"):
    snapshot = {"run_id": 3, "collected_at": NOW.isoformat(), "previously_seen_urls": [], "articles": [
        candidate(gaming.POKEMON, TCG_URL, f"Pokemon TCG Mega Evolution Fixture Expansion arriving {tcg_date}"),
        candidate(gaming.EPIC, GAME_URL, "Fixture Game", offer_window={
            "starts_at": "2026-11-26T16:00:00+00:00", "ends_at": DEADLINE, "market": "US",
        }),
        candidate(gaming.LUNA, LUNA_URL, "Claim your game today"),
    ]}
    report = {"run_id": 3, "snapshot_run_id": 3, "sources": [
        {"source": source, "status": "ok", "new": 1, "previously_seen": 0}
        for source in (gaming.POKEMON, gaming.EPIC, gaming.LUNA)
    ]}
    return snapshot, report


class VerificationTests(unittest.TestCase):
    def test_official_schedule_and_store_confirm_only_supported_fields(self):
        snapshot, report = inputs()
        press_url = "https://press.pokemon.com/en/releases/fixture-expansion"
        snapshot["articles"].append({**snapshot["articles"][0], "canonical_url": press_url})
        client = FixtureClient(SCHEDULE, storefront())
        findings = verify(snapshot, report, client, NOW)
        self.assertEqual(client.urls, [POKEMON_SCHEDULE, gaming.EPIC_URL])
        self.assertEqual(findings["articles"][TCG_URL]["claims"]["release_date"]["value"], "2027-02-06")
        self.assertEqual(findings["articles"][TCG_URL]["claims"]["msrp"]["status"], "unverified")
        self.assertEqual(findings["articles"][LUNA_URL]["claims"]["claim_deadline"]["status"], "unverified")
        rendered = draft(snapshot, report, findings, now=NOW)
        self.assertIn("Publisher release date 2027-02-06", rendered)
        self.assertEqual(rendered.count("Publisher release date 2027-02-06"), 1)
        self.assertIn(press_url, rendered)
        self.assertIn(f"U.S. store price USD 0.00 until {DEADLINE}", rendered)
        self.assertIn(POKEMON_SCHEDULE, rendered)
        self.assertNotIn("$99.99", rendered)
        self.assertNotIn("Claim your game today", rendered)

    def test_conflicting_source_data_and_raw_headlines_are_held(self):
        snapshot, report = inputs("February 7, 2027")
        findings = verify(snapshot, report, FixtureClient(SCHEDULE, storefront("2026-12-04T16:00:00Z")), NOW)
        self.assertEqual(findings["articles"][TCG_URL]["claims"]["release_date"]["status"], "conflict")
        self.assertEqual(findings["articles"][GAME_URL]["claims"]["current_price"]["status"], "conflict")
        rendered = draft(snapshot, report, findings, now=NOW)
        self.assertNotIn("February 7", rendered)
        self.assertNotIn("2027-02-06", rendered)
        self.assertNotIn(DEADLINE, rendered)
        self.assertNotIn("USD 0.00", rendered)

    def test_unavailable_source_does_not_block_other_source_or_publish_raw_window(self):
        snapshot, report = inputs()
        findings = verify(snapshot, report, FixtureClient(SCHEDULE, FetchError("HTTP 403", 1, 403)), NOW)
        self.assertEqual(findings["articles"][GAME_URL]["claims"]["claim_deadline"]["status"], "unavailable")
        rendered = draft(snapshot, report, findings, now=NOW)
        self.assertIn("2027-02-06", rendered)
        self.assertNotIn(DEADLINE, rendered)
        self.assertNotIn(DEADLINE, draft(snapshot, report, now=NOW))

    def test_expired_deadline_and_mismatched_run_are_rejected_for_display(self):
        snapshot, report = inputs()
        findings = verify(snapshot, report, FixtureClient(SCHEDULE, storefront()), NOW)
        expired = datetime.fromisoformat(DEADLINE)
        rendered = draft(snapshot, report, findings, now=expired)
        self.assertNotIn("USD 0.00", rendered)
        self.assertNotIn(DEADLINE, rendered)
        with self.assertRaisesRegex(ValueError, "different snapshot"):
            draft(snapshot, report, {**findings, "collected_at": "different"})

    def test_schedule_needs_an_unambiguous_product_and_full_date(self):
        snapshot, report = inputs()
        ambiguous = SCHEDULE.replace(b"</table>", b"""
            <tr><td class="td-prod">Pokemon TCG: Mega Evolution Fixture Expansion</td>
            <td class="td-date">March 1, 2027</td></tr></table>""")
        for table in (SCHEDULE.replace(b"February 6, 2027", b"2027"), ambiguous):
            findings = verify(snapshot, report, FixtureClient(table, storefront()), NOW)
            self.assertEqual(findings["articles"][TCG_URL]["claims"]["release_date"]["status"], "unverified")
        snapshot["articles"][0]["title"] = "Pokémon TCG: Mega Evolution — Unlisted Expansion"
        findings = verify(snapshot, report, FixtureClient(SCHEDULE, storefront()), NOW)
        self.assertEqual(findings["articles"][TCG_URL]["claims"]["release_date"]["status"], "unverified")
