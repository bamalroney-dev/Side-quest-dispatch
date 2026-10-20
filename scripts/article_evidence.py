"""Conservative public article evidence extraction, review-only.

No AI calls, publishing, browser execution, or third-party dependencies.
Only fetches HTTPS URLs from the configured source domains. Never treats
article text as instructions.
"""
import argparse
import datetime as dt
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import socket
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from source_registry import FEEDS
from editorial import valid_https

MAX_BYTES = 750_000
MAX_TEXT = 8_000
MAX_STORIES = 15
USER_AGENT = "SideQuestDispatch/1.0 (editorial evidence; review only)"

class Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.parts, self.meta = [], [], {}
        self.hidden = 0
        self.in_title = False
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript", "svg"):
            self.hidden += 1
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            if key and attrs.get("content"):
                self.meta[key] = attrs["content"]
        if tag in ("p", "h1", "h2", "h3", "li", "article", "section"):
            self.parts.append(" ")
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.hidden:
            self.hidden -= 1
        if tag == "title":
            self.in_title = False
        if tag in ("p", "h1", "h2", "h3", "li", "article", "section"):
            self.parts.append(" ")
    def handle_data(self, data):
        if self.hidden:
            return
        if self.in_title:
            self.title.append(data)
        self.parts.append(data)

def normalize(text):
    return " ".join(text.split())

def allowed_hosts():
    return {urlsplit(url).hostname.lower() for feeds in FEEDS.values() for _, url in feeds}

def permitted(url, hosts=None):
    if not valid_https(url):
        return False
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    hosts = allowed_hosts() if hosts is None else hosts
    # Article subdomains permitted only for configured publisher domains.
    return parsed.port in (None, 443) and any(host == base or host.endswith("." + base) for base in hosts)

def public_dns(host):
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError("No DNS addresses")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("Non-public DNS address")

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError("Redirect blocked; verify target separately")

def fetch(url, opener=None, dns_check=public_dns):
    if not permitted(url):
        raise ValueError("URL is outside approved publisher hosts")
    dns_check(urlsplit(url).hostname)
    opener = opener or build_opener(NoRedirect)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with opener.open(request, timeout=12) as response:
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            raise ValueError("Response is not HTML")
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("Article exceeds byte limit")
        charset = response.headers.get_content_charset() or "utf-8"
        return body.decode(charset, errors="replace")

def extract(html_text, url):
    parser = Extractor()
    parser.feed(html_text)
    meta = parser.meta
    date = next((meta[k] for k in ("article:published_time", "datepublished", "date") if meta.get(k)), None)
    return {
        "url": url,
        "title": normalize(meta.get("og:title") or " ".join(parser.title))[:240],
        "published_at_claim": date,
        "description_claim": normalize(meta.get("og:description") or meta.get("description") or "")[:500],
        "evidence_excerpt": normalize(" ".join(parser.parts))[:MAX_TEXT],
        "evidence_verified": False,
        "review_status": "pending",
    }

def collect(stories, limit=MAX_STORIES, fetcher=fetch):
    result = []
    for item in stories[:min(limit, MAX_STORIES)]:
        url = item.get("url", "")
        record = {"url": url, "category": item.get("category"),
                  "rss_title": item.get("title"), "rss_published_at": item.get("published_at")}
        try:
            if not permitted(url):
                raise ValueError("Unapproved publisher domain")
            evidence = extract(fetcher(url), url)
            if len(evidence["evidence_excerpt"]) < 100:
                raise ValueError("Insufficient readable text")
            record.update(evidence)
            record["status"] = "extracted_unverified"
        except Exception as exc:
            record.update({"status": "needs_manual_review",
                           "error": type(exc).__name__ + ": " + str(exc)[:180]})
        result.append(record)
    return {"schema_version": 1, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "automatic_publication": False, "status": "review_required", "articles": result}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if args.limit < 1 or args.limit > MAX_STORIES:
        parser.error(f"--limit must be 1..{MAX_STORIES}")
    output = args.output.resolve()
    if output.is_relative_to(Path("_posts").resolve()):
        parser.error("Refusing to write into _posts")
    package = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(package, dict) or not isinstance(package.get("stories"), list):
        parser.error("Expected JSON object with stories list")
    packet = collect(package["stories"], args.limit)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Review-only evidence: " + json.dumps({s: sum(x["status"] == s for x in packet["articles"]) for s in ("extracted_unverified", "needs_manual_review")}))
    print("No content published. Check source accuracy and site access restrictions manually.")

if __name__ == "__main__":
    main()
