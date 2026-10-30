import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from article_evidence import extract, permitted, collect, fetch
HTML="""<html><head><title>Example report</title><meta property="article:published_time" content="2026-10-20T12:00:00Z"><meta property="og:description" content="An example update"></head><body><script>ignore this</script><article><h1>Example report</h1><p>""" + ("Confirmed reporting from the publisher. "*8) + """</p></article></body></html>"""
class EvidenceTests(unittest.TestCase):
    def test_extract_metadata(self):
        item=extract(HTML,"https://example.org/a")
        self.assertEqual(item["title"],"Example report")
        self.assertEqual(item["published_at_claim"],"2026-10-20T12:00:00Z")
        self.assertNotIn("ignore this",item["evidence_excerpt"])
        self.assertFalse(item["evidence_verified"])
    def test_reject_unapproved_domain(self):
        self.assertFalse(permitted("https://localhost/a"))
        self.assertFalse(permitted("http://feeds.bbci.co.uk/a"))
        self.assertFalse(permitted("https://feeds.bbci.co.uk.evil.example/a"))
    def test_approved_domain(self):
        self.assertTrue(permitted("https://feeds.bbci.co.uk/news/story"))
    def test_success_packet(self):
        item={"url":"https://feeds.bbci.co.uk/news/story","title":"Story","category":"News","published_at":"2026-10-20T12:00:00Z"}
        packet=collect([item],fetcher=lambda _: HTML)
        self.assertEqual(packet["articles"][0]["status"],"extracted_unverified")
        self.assertFalse(packet["automatic_publication"])
    def test_fetch_failure_is_nonfatal(self):
        item={"url":"https://feeds.bbci.co.uk/news/story","title":"Story"}
        packet=collect([item],fetcher=lambda _: (_ for _ in ()).throw(TimeoutError("timeout")))
        self.assertEqual(packet["articles"][0]["status"],"needs_manual_review")
    def test_short_page_flagged(self):
        item={"url":"https://feeds.bbci.co.uk/news/story"}
        packet=collect([item],fetcher=lambda _: "<html><p>Short</p></html>")
        self.assertEqual(packet["articles"][0]["status"],"needs_manual_review")
    def test_redirect_blocked(self):
        from article_evidence import NoRedirect
        with self.assertRaises(ValueError):
            NoRedirect().redirect_request(None,None,302,"Moved",{},"https://other.example/")
if __name__=="__main__": unittest.main()
