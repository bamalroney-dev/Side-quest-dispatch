"""Run a research collection and export the latest snapshot and source health."""

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

from .disney_food_blog import collect as collect_disney
from .gaming import collect_epic, collect_luna, collect_osrs, collect_pokemon
from .http import HttpClient
from .storage import record_run

COLLECTORS = (collect_disney, collect_pokemon, collect_epic, collect_luna, collect_osrs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("research-data"))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")
    client = HttpClient()
    batches = [collect(client) for collect in COLLECTORS]
    usable = record_run(args.output_dir, datetime.now(timezone.utc).isoformat(), batches)
    for records, health in batches:
        logging.info("%s collection %s (%s records)", health["source"], health["status"], len(records))
    logging.info("Reports in %s", args.output_dir)
    return int(not usable)


if __name__ == "__main__":
    raise SystemExit(main())
