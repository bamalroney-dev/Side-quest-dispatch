"""Collect and report endpoint outcomes independently."""

import logging

from .http import FetchError

LOG = logging.getLogger(__name__)


def check_endpoint(client, source, method, url, hosts, accept, parse, *, allow_empty=False):
    check = {"method": method, "url": url, "attempts": 0, "skipped": 0}
    try:
        response = client.get(url, source=source, hosts=hosts, accept=accept)
        check.update(attempts=response.attempts, final_url=response.url)
        records, skipped = parse(response, method)
        check["skipped"] = skipped
        if not records and (not allow_empty or skipped):
            raise ValueError("No valid articles found")
    except FetchError as exc:
        check.update(attempts=exc.attempts, http_status=exc.status, error=str(exc), stage="fetch")
    except ValueError as exc:
        check.update(error=str(exc), stage="parse")
    else:
        check["status"] = "ok"
        return records, check
    check["status"] = "failed"
    LOG.warning("%s %s at %s failed: %s", source, method, url, check["error"])
    return [], check


def collect_endpoints(client, source, method, urls, hosts, accept, parse, *, allow_empty=False):
    records, checks = [], []
    for url in urls:
        batch, check = check_endpoint(
            client, source, method, url, hosts, accept, parse, allow_empty=allow_empty,
        )
        records.extend(batch)
        checks.append(check)
    if all(check["status"] == "failed" for check in checks):
        status = "failed"
    elif any(check["status"] == "failed" or check["skipped"] for check in checks):
        status = "degraded"
    else:
        status = "ok"
    return records, {"source": source, "status": status,
                     "method": method if status != "failed" else None, "checks": checks}
