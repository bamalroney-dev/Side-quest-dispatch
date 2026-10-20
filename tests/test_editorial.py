import datetime as dt
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from editorial import validate_story, validate_package
NOW = dt.datetime(2026, 10, 19, 12, tzinfo=dt.timezone.utc)
def sample():
    return {"title":"Test","category":"Pokémon","url":"https://example.org/story","source":"Example","published_at":"2026-10-19T10:00:00Z","summary":"Test summary","why_it_matters":"Test relevance","evidence_urls":["https://example.org/story"]}
class EditorialTests(unittest.TestCase):
    def test_valid(self): self.assertEqual(validate_story(sample(), NOW), [])
    def test_old(self):
        s=sample(); s["published_at"]="2026-10-01T10:00:00Z"
        self.assertTrue(validate_story(s,NOW))
    def test_future_event(self):
        s=sample(); s["event"]={"official_url":"https://example.org/event","starts_at":"2026-11-01T10:00:00Z"}
        self.assertEqual(validate_story(s,NOW),[])
    def test_expired_event(self):
        s=sample(); s["event"]={"official_url":"https://example.org/event","starts_at":"2026-10-01T10:00:00Z"}
        self.assertTrue(validate_story(s,NOW))
    def test_no_evidence(self):
        s=sample(); del s["evidence_urls"]
        self.assertTrue(validate_story(s,NOW))
    def test_images_blocked(self):
        s=sample(); s["image"]="https://example.org/photo.jpg"
        self.assertTrue(validate_story(s,NOW))
    def test_duplicates(self): self.assertIn("1",validate_package({"stories":[sample(),sample()]},NOW))
    def test_missing_fields(self): self.assertTrue(validate_story({},NOW))
if __name__=="__main__": unittest.main()
