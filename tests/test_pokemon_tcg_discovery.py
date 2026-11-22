import unittest
from scripts.pokemon_tcg_discovery import candidates_from_html, deduplicate, validate_dataset

class DiscoveryTests(unittest.TestCase):
    def test_official_candidate(self):
        html = '<a href="/us/pokemon-news/example">Pokémon TCG New Expansion</a>'
        rows = candidates_from_html("https://www.pokemon.com/us/pokemon-news", html)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["msrp_usd"])
        self.assertIsNone(rows[0]["release_date"])
    def test_reject_external(self):
        html = '<a href="https://evil.example/pokemon-tcg">Pokémon TCG</a>'
        self.assertEqual(candidates_from_html("https://www.pokemon.com/us/pokemon-news", html), [])
    def test_dedupe(self):
        row = {"source_url":"https://www.pokemon.com/us/pokemon-news/example","title":"Example"}
        self.assertEqual(len(deduplicate([row,row], [])),1)
    def test_msrp_guard(self):
        with self.assertRaises(AssertionError):
            validate_dataset({"products":[{"id":"a","source":"https://www.pokemon.com/a","release_date":"2027-02-06","msrp_usd":50,"msrp_verified":False}]})
if __name__ == "__main__":
    unittest.main()
