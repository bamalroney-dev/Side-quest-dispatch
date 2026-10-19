import datetime as dt
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from editorial_queue import canonical_url, score, select, review_packet

NOW=dt.datetime(2026,10,19,12,tzinfo=dt.timezone.utc)
def story(url="https://example.org/a",category="Disney Parks",published="2026-10-19T10:00:00Z"):
    return {"title":"Headline","category":category,"url":url,"source":"Source",
            "published_at":published,"summary":"Summary","why_it_matters":"Relevance",
            "evidence_urls":[url]}
class QueueTests(unittest.TestCase):
    def test_tracking_dedupe(self):
        self.assertEqual(canonical_url("https://example.org/a/?utm_source=email"),
                         canonical_url("https://example.org/a"))
    def test_priority_scoring(self):
        self.assertGreater(score(story(),NOW),score(story(category="Major U.S. and World Developments"),NOW))
    def test_freshness_scoring(self):
        self.assertGreater(score(story(),NOW),score(story(published="2026-10-18T10:00:00Z"),NOW))
    def test_no_expired(self):
        self.assertEqual(select([story(published="2026-10-01T10:00:00Z")],NOW),[])
    def test_per_category_limit(self):
        items=[story(url=f"https://example.org/{i}") for i in range(7)]
        self.assertEqual(len(select(items,NOW,per_category=3)),3)
    def test_review_only(self):
        packet=review_packet([story()],NOW)
        self.assertFalse(packet["automatic_publication"])
        self.assertEqual(packet["status"],"review_required")
        self.assertEqual(packet["stories"][0]["review_status"],"pending")
    def test_dedupe_variants(self):
        self.assertEqual(len(select([story(),story(url="https://example.org/a?utm_medium=email")],NOW)),1)
if __name__=="__main__": unittest.main()
