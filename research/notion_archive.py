"""Notion API access for the briefing archive."""

import json
import re
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from .editorial_handoff import ARCHIVE_TITLE


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class NotionArchive:
    def __init__(self, token):
        if not token:
            raise ValueError("Set NOTION_TOKEN with access to the Notion briefing archive")
        self.headers = {"Authorization": f"Bearer {token}", "Notion-Version": "2026-03-11",
                        "Content-Type": "application/json"}
        self.opener = build_opener(NoRedirect)

    def request(self, method, path, payload=None):
        request = Request(f"https://api.notion.com/v1/{path}", method=method, headers=self.headers,
                          data=json.dumps(payload).encode() if payload is not None else None)
        for attempt in range(3):
            try:
                with self.opener.open(request, timeout=15) as response:
                    return json.load(response)
            except HTTPError as exc:
                if method == "GET" and exc.code in {429, 500, 502, 503, 504} and attempt < 2:
                    retry = exc.headers.get("Retry-After", "")
                    sleep(min(15, int(retry)) if retry.isdecimal() else 2 ** attempt)
                    continue
                raise ValueError(f"Notion {method} failed with HTTP {exc.code}") from None
            except (URLError, TimeoutError):
                if method == "GET" and attempt < 2:
                    sleep(2 ** attempt)
                    continue
                raise ValueError(f"Notion {method} request did not complete") from None

    def review_pages(self, parent):
        pages = {}
        query = {"page_size": 100}
        while True:
            result = self.request("GET", f"blocks/{UUID(parent)}/children?{urlencode(query)}")
            for block in result["results"]:
                title = block.get("child_page", {}).get("title", "")
                match = re.fullmatch(rf"{ARCHIVE_TITLE} ([1-9][0-9]{{0,19}})", title)
                if match:
                    number = int(match[1])
                    if number in pages:
                        raise ValueError(f"More than one Notion review exists for run {number}")
                    pages[number] = block
            if not result["has_more"]:
                return pages
            query["start_cursor"] = result["next_cursor"]

    def markdown(self, page_id):
        result = self.request("GET", f"pages/{UUID(page_id)}/markdown?markdown_version=v2")
        if result.get("truncated") or result.get("unknown_block_ids"):
            raise ValueError("Notion review page could not be read completely")
        return result["markdown"]

    def create_review(self, parent, title, content):
        return self.request("POST", "pages", {
            "parent": {"type": "page_id", "page_id": str(UUID(parent))},
            "properties": {"title": {"type": "title", "title": [
                {"type": "text", "text": {"content": title}},
            ]}},
            "markdown": content,
            "markdown_version": "v2",
        })
