import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_dispatch as d
from source_registry import FEEDS, RESEARCH_TARGETS

class SourceTests(unittest.TestCase):
    def test_registry_urls_https(self):
        for entries in FEEDS.values():
            for name, url in entries:
                self.assertTrue(name)
                self.assertTrue(url.startswith("https://"))
    def test_research_targets_not_treated_as_feeds(self):
        self.assertFalse(set(RESEARCH_TARGETS) & set(FEEDS))
    def test_date_parsing(self):
        self.assertEqual(d.parse_date("Mon, 19 Oct 2026 12:00:00 GMT"), dt.datetime(2026,10,19,12,tzinfo=dt.timezone.utc))
    def test_rss_parsing(self):
        xml=b"""<rss><channel><item><title>New event</title><link>https://example.org/news</link><pubDate>Mon, 19 Oct 2026 12:00:00 GMT</pubDate><description>Fresh update</description></item></channel></rss>"""
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,*args): return xml
        with patch.object(d.urllib.request, "urlopen", return_value=Response()):
            items=d.read_feed("Test", "https://example.org/feed")
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]["title"],"New event")
    def test_duplicate_normalization(self):
        self.assertEqual(d.story_key("https://example.org/post?utm_source=mail"), d.story_key("https://example.org/post/"))
if __name__=="__main__": unittest.main()
