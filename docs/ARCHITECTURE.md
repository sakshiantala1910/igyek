# Architecture and design notes

For the technical reviewer. The README covers what the product does and how to
run it; this covers why it is built the way it is.

## Shape

```
Browser (React 18 + TS + Vite + Recharts)
   │  fetch('/api/…')          same origin everywhere — no build-time API URL
   ▼
Edge:  nginx (Docker)  |  Vercel rewrite  |  Vite proxy (dev)
   │
   ▼
FastAPI (Python 3.12)
   ├── main.py      routes, query validation, response shaping
   ├── align.py     raw feeds → the one scored table
   ├── metrics.py   pure statistics over that table
   ├── store.py     snapshot-first data access, cached per process
   └── elexon.py    BMRS HTTP client
   ▼
data/*.csv.gz       committed January 2026 snapshot (~112 KB)
```

## Decisions and the reasoning behind them

**One origin, three deployment targets.** The frontend never knows an API host.
Vite proxies `/api` in development, nginx proxies it in Docker, and Vercel
rewrites it in production. This removes a whole class of environment bug (wrong
`VITE_API_URL` in a build) and means CORS never has to be configured for the
real deployments.

**The same FastAPI app runs everywhere.** `api/index.py` is a nine-line shim
that puts `backend/` on `sys.path` and re-exports `app`. There is no second
serverless implementation to drift out of step with the container.

**Snapshot-first data access.** The study window is historical and immutable,
so it is pinned to disk and committed. Live fetching exists (`ALLOW_LIVE_FETCH`)
but is off in the container and on Vercel. This buys reproducibility, fast cold
starts, and immunity to a BMRS outage during a demo. Provenance is exposed on
`/api/meta` so the data in front of you is always identifiable.

**Layering is strict and one-directional.** `metrics.py` takes a DataFrame and
returns plain dicts — it does not know HTTP exists, which is why it is cheap to
test. `align.py` does not know what a metric is. `main.py` does no arithmetic.
The interesting logic is therefore testable without a client, and the tests
reflect that split.

**`lru_cache` on the dataset, not a cache layer.** The data is ~112 KB and
immutable for the life of the process. Parsing it once per process is the whole
caching strategy; anything more would be machinery without a problem.

**Gzipped CSV, not Parquet.** Parquet would be the normal choice, but it drags
in `pyarrow`, and the Vercel function has a bundle size limit. At this volume
the format makes no measurable difference.

## Where the risk actually is

Not in the plumbing — in the three alignment decisions. Each is documented at
its definition in `align.py` and pinned by a test:

| Decision | Failure if wrong | Test |
|---|---|---|
| Vintage strictly before gate closure | Scores the desk on information it never had; flatters every metric | `test_vintage_is_strictly_before_the_deadline` |
| Average outturn up, don't interpolate forecast down | Invents forecast resolution that never existed | `test_hourly_actuals_average_both_settlement_periods` |
| Local-clock delivery days | Silently mis-aligns 1–2 hours per day across BST | `test_delivery_day_handles_bst` |
| Trailing-only uncertainty band | Look-ahead bias; the band would be impossibly good | `rolling_bias_correction` uses `.shift(1)`, covered by `test_bias_correction_uses_only_prior_days` |

## Testing

33 tests, split by what they protect:

- `test_align.py` — the judgement calls, on hand-built frames with known answers.
- `test_metrics.py` — statistics on synthetic data where the correct result is
  known analytically (a constant +1000 MW lean must correct to ~0 bias).
- `test_api.py` — integration against the committed snapshot. These double as a
  guard on the data: if a snapshot rebuild loses days or changes resolution,
  `test_accuracy_scores_every_hour_of_every_delivery_day` fails rather than
  every headline number quietly shifting.

The headline finding itself has a regression test
(`test_accuracy_reports_the_january_over_forecast_lean`), so it cannot be
silently invalidated by a refactor.

## Practices worth noting in review

- **Comments explain *why*, never *what*.** Every non-obvious line says what
  would go wrong otherwise.
- **Config is centralised** in `config.py`, so anything a reviewer might want to
  challenge (deadline, capacity assumption, study window, lookback) is in one
  file and overridable by environment variable.
- **The sign convention is stated once and held everywhere** — API, metrics, UI
  colour (red = short), and the footer of the app itself.
- **Containers run unprivileged**, multi-stage so the runtime image carries no
  Node or source, with healthchecks that compose depends on.
- **Limitations are written down** in the README rather than left to be
  discovered.

## What I would do next

1. **Demand data**, to turn the cover table from "MW on top of the wind
   forecast" into an absolute procurement volume.
2. **Confirm the curtailment hypothesis** with BOALF data and split the error
   into meteorological and curtailment components. That decides whether the fix
   belongs in the bias correction or in the forecast source.
3. **A conditional bias correction** (by forecast level, or by hour) measured
   against the current pooled one on held-out months.
4. **Price the error**, by joining day-ahead and imbalance prices, so the cover
   table reads in £ rather than MWh.
5. **Scheduled ingestion** for live operation — the snapshot model is right for
   a pilot over a fixed window, not for a running desk.
