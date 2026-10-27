"""Vercel serverless entrypoint.

Vercel's Python runtime looks for a module-level ASGI app in ``api/*.py``, so
this is a thin shim that puts ``backend/`` on the path and re-exports the same
FastAPI application the Docker image runs. There is no second implementation to
keep in step.

Live fetching is disabled here: the function must answer from the committed
snapshot, both to keep cold starts fast and so a BMRS outage cannot take the
demo down.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")

if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

os.environ.setdefault("WINDSIGHT_DATA_DIR", os.path.join(BACKEND, "data"))
os.environ.setdefault("ALLOW_LIVE_FETCH", "0")

from app.main import app  # noqa: E402  (path set up above)

__all__ = ["app"]
