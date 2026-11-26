"""Bounded HTTP GETs with per-endpoint diagnostics."""

import logging
from dataclasses import dataclass
from http.client import HTTPException
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

LOG = logging.getLogger(__name__)
RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class Response:
    body: bytes
    url: str
    attempts: int


class FetchError(Exception):
    def __init__(self, message, attempts, status=None):
        super().__init__(message)
        self.attempts = attempts
        self.status = status


def allowed(url, hosts):
    parts = urlsplit(url)
    return (
        parts.scheme == "https" and parts.hostname in hosts
        and parts.port in (None, 443) and parts.username is None
    )


class SourceRedirects(HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed(newurl, self.hosts):
            raise ValueError("Redirect outside configured HTTPS source hosts")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HttpClient:
    def __init__(self, *, timeout=12, max_attempts=3, max_bytes=4_000_000,
                 opener_factory=build_opener, wait=sleep):
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.max_bytes = max_bytes
        self.opener_factory = opener_factory
        self.wait = wait

    def get(self, url, *, source, hosts, accept):
        if not allowed(url, hosts):
            raise FetchError("URL outside configured HTTPS source hosts", 0)
        opener = self.opener_factory(SourceRedirects(hosts))
        request = Request(url, headers={
            "User-Agent": "SideQuestDispatch/1.0 (research collection)",
            "Accept": accept,
        })
        for attempt in range(1, self.max_attempts + 1):
            status, retry_after = None, 0
            try:
                with opener.open(request, timeout=self.timeout) as response:
                    body = response.read(self.max_bytes + 1)
                    if len(body) > self.max_bytes:
                        raise ValueError("Response exceeds byte limit")
                    LOG.info("%s GET %s succeeded on attempt %s", source, url, attempt)
                    return Response(body, response.geturl(), attempt)
            except HTTPError as exc:
                status = exc.code
                message = f"HTTP {status}"
                retryable = status in RETRYABLE_STATUSES
                header = exc.headers.get("Retry-After", "") if exc.headers else ""
                if header.isascii() and header.isdigit():
                    retry_after = int(header[:8])
                exc.close()
            except (URLError, OSError, HTTPException) as exc:
                message, retryable = str(exc), True
            except ValueError as exc:
                message, retryable = str(exc), False

            LOG.warning("%s GET %s attempt %s/%s failed: %s",
                        source, url, attempt, self.max_attempts, message)
            if not retryable or attempt == self.max_attempts:
                raise FetchError(message, attempt, status)
            self.wait(min(30, max(retry_after, 2 ** (attempt - 1))))
