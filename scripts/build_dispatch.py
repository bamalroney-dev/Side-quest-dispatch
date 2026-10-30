#!/usr/bin/env python3
"""Conservative, source-linked RSS daily digest. No generative AI or unverified events."""
import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import pathlib
import re
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from source_registry import FEEDS, RESEARCH_TARGETS

ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "story-index.json"
POSTS = ROOT / "_posts"
TZ = ZoneInfo("America/Chicago")
CATEGORIES = [
    "Jenks and Tulsa Family Activities", "Oklahoma Concerts and Live Music",
    "Breaking U.S. and World News", "Viral Stories",
    "Major U.S. and World Developments", "Surprising and Unusual News",
    "Disney Parks", "Walt Disney World", "Disneyland California",
    "Disney Cruise Line", "Disney Lorcana", "Pokémon Trading Card Game",
    "Pokémon", "Pokémon Legends: Z-A Codes and Events",
    "RuneScape 3", "Old School RuneScape",
]

def clean(value):
    value = re.sub(r"<[^>]*>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()

def sentence_aware_excerpt(value, limit=1000):
    """Prefer complete sentences, then word boundaries; never slice mid-word."""
    text = clean(value)
    if len(text) <= limit:
        return text
    prefix = text[:limit + 1]
    # Prefer a complete sentence near the end of the available excerpt.
    ends = list(re.finditer(r"[.!?](?=\\s|$)", prefix))
    if ends:
        end = ends[-1].end()
        if end >= limit // 2:
            return text[:end]
    # Otherwise truncate at a word boundary and indicate omitted content.
    cutoff = text.rfind(" ", 0, limit - 1)
    if cutoff < limit // 2:
        cutoff = limit - 1
    return text[:cutoff].rstrip(" ,;:") + "…"

def parse_date(raw):
    try:
        return email.utils.parsedate_to_datetime(raw).astimezone(dt.timezone.utc)
    except (TypeError, ValueError, IndexError):
        try:
            return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
        except (TypeError, ValueError):
            return None

def read_feed(source, url):
    req = urllib.request.Request(url, headers={"User-Agent": "SideQuestDispatch/1.0 (RSS newsletter)"})
    with urllib.request.urlopen(req, timeout=18) as response:
        data = response.read(2_000_000)
    root = ET.fromstring(data)
    entries = []
    for item in root.findall(".//item"):
        title = clean(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        date = parse_date(item.findtext("pubDate"))
        description = sentence_aware_excerpt(item.findtext("description"))
        if title and link.startswith("https://") and date:
            entries.append(dict(title=title, url=link, published=date, description=description, source=source))
    # Atom fallback
    ns = "{http://www.w3.org/2005/Atom}"
    for item in root.findall(f".//{ns}entry"):
        title = clean(item.findtext(f"{ns}title"))
        link_node = item.find(f"{ns}link")
        link = link_node.get("href", "") if link_node is not None else ""
        date = parse_date(item.findtext(f"{ns}published") or item.findtext(f"{ns}updated"))
        description = sentence_aware_excerpt(item.findtext(f"{ns}summary"))
        if title and link.startswith("https://") and date:
            entries.append(dict(title=title, url=link, published=date, description=description, source=source))
    return entries

def md(value):
    return re.sub(r"([\\*_`\[\]])", r"\\\1", clean(value))

def story_key(url):
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    query = urlencode(sorted((k,v) for k,v in parse_qsl(parts.query) if not k.lower().startswith("utm_") and k.lower() not in {"fbclid","gclid"}))
    normalized = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))
    return hashlib.sha256(normalized.encode()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduled", action="store_true")
    args = parser.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    local = now.astimezone(TZ)
    if args.scheduled and os.environ.get("GITHUB_EVENT_NAME") == "schedule" and local.hour != 7:
        print("Not 07:00 Central; skipping alternate DST cron.")
        return
    today = local.date().isoformat()
    path = POSTS / f"{today}-side-quest-dispatch.md"
    if path.exists():
        print("Edition already exists; not overwriting it.")
        return
    history = json.loads(INDEX.read_text()) if INDEX.exists() else {"urls": {}}
    seen = history.get("urls", {})
    grouped = {}
    run_keys = set()
    diagnostics = {}
    for category, sources in FEEDS.items():
        candidates = []
        errors = []
        for source, url in sources:
            try:
                candidates.extend(read_feed(source, url))
            except Exception as error:
                errors.append(f"{source}: {type(error).__name__}")
                print(f"Feed unavailable ({source}): {error}")
        eligible = []
        for item in sorted(candidates, key=lambda x: x["published"], reverse=True):
            age = now - item["published"]
            key = story_key(item["url"])
            if dt.timedelta(0) <= age <= dt.timedelta(hours=48) and key not in seen and key not in run_keys:
                item["key"] = key
                eligible.append(item)
                run_keys.add(key)
        grouped[category] = eligible[:5]
        diagnostics[category] = {"sources": len(sources), "retrieved": len(candidates), "selected": len(grouped[category]), "errors": errors}
    print("SOURCE_REPORT " + json.dumps(diagnostics, sort_keys=True))
    print("RESEARCH_ONLY_CATEGORIES " + ", ".join(RESEARCH_TARGETS))
    total = sum(map(len, grouped.values()))
    if not total:
        print("No fresh verified feed items; no post created.")
        return
    title = f"Side Quest Dispatch – {local.strftime('%B')} {local.day}, {local.year}"
    lines = ["---", "layout: post", f'title: "{title}"', f"date: {today}",
             'description: "Fresh source-linked Disney, Pokémon, gaming, and world news."',
             "tags: [news, pokemon, disney, gaming, oklahoma, concerts]",
             "---", "", "# 🎮 Side Quest Dispatch", "",
             "Your daily checkpoint for fresh headlines and hobby updates.", "",
             "## ⭐ Top Side Quests", ""]
    highlights = [x for items in grouped.values() for x in items]
    highlights.sort(key=lambda x: x["published"], reverse=True)
    for item in highlights[:5]:
        lines.append(f"- [{md(item['title'])}]({item['url']})")
    lines += ["", "## 📰 Today's Dispatches", ""]
    quiet = []
    for category in CATEGORIES:
        items = grouped.get(category, [])
        if not items:
            quiet.append(category)
            continue
        lines += [f"## {category}", ""]
        for item in items:
            lines += [f"### {md(item['title'])}", "",
                      f"**Source:** [{md(item['source'])}]({item['url']})  ",
                      f"**Published:** {item['published'].astimezone(TZ).strftime('%B %d, %Y')}", "",
                      f"**What happened:** {md(item['description']) or 'See the original source for details.'}", "",
                      "**Why it matters:** This is a newly published update in a topic followed by Side Quest Dispatch readers. Read the linked source for full context.", ""]
            seen[item["key"]] = today
    lines += ["## 📅 Upcoming Side Quests", "",
              "No future events are listed without separately verifying event dates and current availability.", "",
              "## 🔭 What To Watch Tomorrow", "",
              "- Watch the linked official sources for follow-up announcements.",
              "- Check local venue calendars for newly listed upcoming events.",
              "- Look for fresh game updates, release details, and official promotions.", "",
              "## 💤 Quiet Categories", "",
              "No significant new updates today that affect fans directly.", "",
              ", ".join(quiet), "",
              "*Editorial note: This automated edition uses dated RSS feed entries. It does not independently fact-check article claims, validate future event dates, summarize full articles, or generate predictions. It deliberately omits unverified concerts, events, promo codes, and images.*", ""]
    POSTS.mkdir(parents=True, exist_ok=True)
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    history["urls"] = seen
    INDEX.write_text(json.dumps(history, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Created {path.name} with {total} feed items.")

if __name__ == "__main__":
    main()
