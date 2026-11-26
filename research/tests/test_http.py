import unittest
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError, URLError
from unittest.mock import Mock

from research.http import FetchError, HttpClient, SourceRedirects

URL = "https://feeds.example.com/feed"
HOSTS = {"feeds.example.com"}


def http_error(status, retry_after=None):
    headers = Message()
    if retry_after:
        headers["Retry-After"] = retry_after
    return HTTPError(URL, status, "Test error", headers, BytesIO())


class HttpClientTests(unittest.TestCase):
    def setUp(self):
        self.opener = Mock()
        self.wait = Mock()
        self.client = HttpClient(opener_factory=Mock(return_value=self.opener), wait=self.wait)

    def get(self):
        return self.client.get(URL, source="Test source", hosts=HOSTS, accept="application/rss+xml")

    def response(self, body):
        response = BytesIO(body)
        response.geturl = lambda: URL
        return response

    def test_retries_timeouts_and_transient_status_with_bounded_backoff(self):
        self.opener.open.side_effect = [
            URLError(TimeoutError("read timed out")), http_error(429, "60"), self.response(b"<rss/>"),
        ]
        with self.assertLogs("research.http", level="INFO") as logs:
            response = self.get()
        self.assertEqual(response.body, b"<rss/>")
        self.assertEqual(response.attempts, 3)
        self.assertEqual([call.args for call in self.wait.call_args_list], [(1,), (30,)])
        self.assertIn("Test source", logs.output[0])
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.get_header("Accept"), "application/rss+xml")
        self.assertEqual(self.opener.open.call_args.kwargs["timeout"], 12)

    def test_permanent_http_error_stops_immediately(self):
        self.opener.open.side_effect = http_error(403)
        with self.assertRaises(FetchError) as caught:
            self.get()
        self.assertEqual((caught.exception.status, caught.exception.attempts), (403, 1))
        self.wait.assert_not_called()

    def test_transient_http_error_stops_at_attempt_limit(self):
        self.opener.open.side_effect = [http_error(503) for _ in range(3)]
        with self.assertRaises(FetchError) as caught:
            self.get()
        self.assertEqual((caught.exception.status, caught.exception.attempts), (503, 3))
        self.assertEqual(self.wait.call_count, 2)

    def test_oversized_response_is_reported_without_retry(self):
        self.client.max_bytes = 5
        self.opener.open.return_value = self.response(b"123456")
        with self.assertRaisesRegex(FetchError, "byte limit"):
            self.get()
        self.wait.assert_not_called()

    def test_redirects_to_unconfigured_hosts_or_http_are_rejected(self):
        handler = SourceRedirects(HOSTS)
        for target in ("https://unconfigured.example/feed", "http://feeds.example.com/feed"):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "Redirect outside"):
                handler.redirect_request(None, None, 302, "", {}, target)
