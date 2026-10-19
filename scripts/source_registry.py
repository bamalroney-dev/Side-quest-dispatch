"""Editorial source registry. Unverified endpoints are disabled until tested."""
FEEDS = {
    "Breaking U.S. and World News": [
        ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("BBC US & Canada", "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml"),
    ],
    "Major U.S. and World Developments": [
        ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
        ("BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
    ],
    "Surprising and Unusual News": [
        ("BBC Science", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"),
    ],
    "Disney Parks": [
        ("Disney Parks Blog", "https://disneyparksblog.com/feed/"),
    ],
    "Pokémon": [
        ("Pokémon News", "https://www.pokemon.com/us/pokemon-news/rss"),
    ],
    "RuneScape 3": [
        ("RuneScape News", "https://secure.runescape.com/m=news/latest_news.rss"),
    ],
    "Old School RuneScape": [
        ("Old School RuneScape", "https://secure.runescape.com/m=news/latest_news.rss?oldschool=1"),
    ],
}
# Editorial discovery targets, not RSS feeds. These require verified event dates,
# article-level verification, and/or an AI research stage before publication.
RESEARCH_TARGETS = {
    "Jenks and Tulsa Family Activities": ["https://www.okaquarium.org/", "https://jenkschamber.com/"],
    "Oklahoma Concerts and Live Music": ["https://www.bokcenter.com/", "https://www.cainsballroom.com/", "https://www.tulsatheater.com/"],
    "Viral Stories": [],
    "Walt Disney World": ["https://disneyparksblog.com/wdw/"],
    "Disneyland California": ["https://disneyparksblog.com/dlr/"],
    "Disney Cruise Line": ["https://disneycruise.disney.go.com/"],
    "Disney Lorcana": ["https://www.disneylorcana.com/"],
    "Pokémon Trading Card Game": ["https://www.pokemon.com/us/pokemon-tcg/"],
    "Pokémon Legends: Z-A Codes and Events": ["https://legends.pokemon.com/"],
}
