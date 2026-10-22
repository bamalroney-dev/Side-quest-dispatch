import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_dispatch import sentence_aware_excerpt

class ExcerptTests(unittest.TestCase):
    def test_short_text_is_unchanged(self):
        self.assertEqual(sentence_aware_excerpt("A complete update.", 100), "A complete update.")
    def test_complete_sentence_preferred(self):
        value = "First complete sentence. Second complete sentence. " + "Extra detail " * 20
        self.assertEqual(sentence_aware_excerpt(value, 55), "First complete sentence. Second complete sentence.")
    def test_word_boundary_fallback(self):
        value = "An unusually detailed description of a very important announcement without punctuation"
        excerpt = sentence_aware_excerpt(value, 50)
        self.assertTrue(excerpt.endswith("…"))
        self.assertFalse(excerpt.endswith("announcemen…"))
    def test_html_removed(self):
        self.assertEqual(sentence_aware_excerpt("<p>Useful update.</p>", 100), "Useful update.")
    def test_preserves_full_description_under_limit(self):
        value = "A " + "detail " * 75
        self.assertEqual(sentence_aware_excerpt(value, 1000), value.strip())

if __name__ == "__main__":
    unittest.main()
