"""CLI: rebuild the committed data snapshot from the live Elexon API.

    python -m app.ingest                      # the January 2026 study window
    python -m app.ingest 2026-02-01 2026-02-28
"""
from __future__ import annotations

import logging
import sys
from datetime import date

from .config import STUDY_DECISION_END, STUDY_DECISION_START
from .store import build_snapshot, reset_cache


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    start = date.fromisoformat(argv[0]) if len(argv) > 0 else STUDY_DECISION_START
    end = date.fromisoformat(argv[1]) if len(argv) > 1 else STUDY_DECISION_END
    manifest = build_snapshot(start, end)
    reset_cache()
    print(
        f"Snapshot ready: {manifest['forecast_rows']} forecast rows across "
        f"{manifest['forecast_publications']} publications, "
        f"{manifest['actual_rows']} actual rows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
