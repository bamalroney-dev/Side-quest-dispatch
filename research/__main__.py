"""Run a research collection and export the latest snapshot and source health."""

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

from .disney_food_blog import collect
from .http import HttpClient
from .storage import record_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("research-data"))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")
    records, health = collect(HttpClient())
    record_run(args.output_dir, datetime.now(timezone.utc).isoformat(), records, health)
    logging.info("%s collection %s. Reports in %s", health["source"], health["status"], args.output_dir)
    return int(health["status"] == "failed")


if __name__ == "__main__":
    raise SystemExit(main())
