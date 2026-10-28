# Windsight — GB day-ahead wind procurement

A web app for the team at a UK energy supplier that buys power from the
day-ahead market. It answers the two questions they have every morning before
gate closure:

1. **What is the latest wind forecast I can actually act on?** Not the newest
   forecast in the database — the newest one that existed *before* the auction
   deadline.
2. **How wrong is that forecast likely to be, in MW?** Quantified, so the
   procurement decision can carry the error rather than ignore it.

Data is Elexon BMRS only: `WINDFOR` (national wind forecast) and `FUELHH`
filtered to `fuelType=WIND` (metered outturn). The study window is every
purchase decision taken in **January 2026** — 31 decisions, 31 delivery days,
744 scored hours.

---

## The headline finding

Scored against the forecast a trader could genuinely have seen at the 09:30
N2EX deadline:

| | Raw WINDFOR | After a trailing 14-day bias correction |
|---|---|---|
| Mean absolute error | 2,039 MW | **1,470 MW** (−27.6%) |
| RMSE | 2,505 MW | **1,926 MW** (−23.4%) |
| Bias | **+1,748 MW** | **+117 MW** |
| Hours the book was short | **85.0%** | — |

WINDFOR ran *above* metered outturn in 85% of hours in January 2026, averaging
+1,748 MW. Over the month that is **1,300 GWh of net under-procurement** —
volume that had to be bought back closer to delivery, when it is usually
dearest.

Crucially, most of that is **not forecast noise, it is a lean**. A large part
of the gap is definitional: `FUELHH` records what the fleet actually delivered
*after curtailment*, while `WINDFOR` describes the wind that was *available*.
Supporting evidence is in the data — forecasts reach 21.4 GW in the window
while metered outturn never exceeds 17.8 GW, and the bias is worst in the
highest outturn bands, which is exactly when the Scottish export constraint
binds.

For a procurement desk the cause is secondary. A lean that persists is a lean
you can subtract, and subtracting it recovers roughly a quarter of the error
using nothing but information available on the morning of the bid.

The app also reports that WINDFOR beats a naive D-2 persistence forecast by
**54%** on RMSE, so the forecast is genuinely worth using — it just needs
de-biasing first.

---

## The three judgement calls

These are the decisions that determine whether the numbers mean anything.
They are implemented in `backend/app/align.py` and each one has a test.

**Vintage — which forecast counts.** For delivery on day D, the app uses the
latest `WINDFOR` publication issued *strictly before* gate closure on D-1.
Strictly, because the 09:30 run is stamped at the same minute N2EX closes;
treating it as usable would score the desk against information it did not
have. With a 09:30 deadline this selects the **07:30 run**. Scoring against a
later publication is the single most common way this analysis is inflated.

**Resolution — `WINDFOR` is hourly, `FUELHH` is half-hourly.** Outturn is
averaged *up* to the hour rather than the forecast being interpolated *down*.
Interpolating a forecast invents information it never contained; averaging a
measurement does not. An hour is only scored when both of its settlement
periods are present.

**Calendar — a "day" is a local-clock day in Europe/London**, because that is
how the auction product and the settlement calendar are defined. Not a UTC
day. (Tested against both GMT and BST.)

**Sign convention**, used everywhere: `error = forecast − actual`. Positive
means wind was over-forecast, so thermal cover was under-bought and the book
is **short**.

---

## What the app shows

**Day-ahead desk.** Pick a delivery day. You get the exact WINDFOR run that was
on the desk at gate closure (and how old it was), the hourly curve, the metered
outturn, and a plausible-outturn band built from the empirical error quantiles
of the *preceding* fortnight only — trailing, so there is no look-ahead. Below
it, a cover table: how much firm power to buy on top of the wind forecast at
each tolerance for being short.

**Forecast accuracy.** Headline MAE / RMSE / bias / hours-short / skill versus
persistence; the bias-correction result above; the error distribution; error by
hour of day; error by forecast horizon; error conditioned on how windy it
actually was; a comparison of all eight scheduled WINDFOR runs; and a row per
delivery day.

---

## Repository layout

```
├── backend/                  Python API and all analytics
│   ├── app/
│   │   ├── config.py         Every tunable: deadline, timezone, study window
│   │   ├── elexon.py         BMRS client for WINDFOR + FUELHH, with retries
│   │   ├── store.py          Snapshot load/build; Elexon only as a fallback
│   │   ├── ingest.py         CLI to rebuild the snapshot from the live API
│   │   ├── align.py          The three judgement calls above
│   │   ├── metrics.py        Error metrics, cover sizing, bias correction
│   │   ├── schemas.py        Response models / the API contract
│   │   └── main.py           FastAPI routes
│   ├── data/                 Committed January 2026 snapshot (~112 KB gzipped)
│   ├── tests/                34 tests: unit + integration against real data
│   └── Dockerfile
├── frontend/                 React + TypeScript + Vite + Recharts
│   ├── src/
│   │   ├── api.ts            Typed mirror of the backend contract
│   │   ├── App.tsx           Shell, tabs, gate-closure selector
│   │   └── components/       DeskView, AccuracyView, shared UI
│   ├── nginx.conf            Serves the bundle, proxies /api to the API
│   └── Dockerfile            Multi-stage: Node builds, nginx serves
├── api/index.py              Vercel entrypoint — re-exports the same app
├── docker-compose.yml        Whole product, one command
└── vercel.json               Static frontend + Python serverless function
```

### Why the data is committed

The study window is historical and immutable, so it is pinned. A committed
snapshot (~112 KB gzipped CSV) makes the deployed demo reproducible, gives
millisecond cold starts on serverless, and means a BMRS outage cannot take down
a client walkthrough. `GET /api/meta` reports the snapshot's provenance and
build time, so nobody has to guess which data they are looking at. Rebuild it
any time with `python -m app.ingest`.

Gzipped CSV rather than Parquet deliberately: it keeps `pyarrow` out of the
dependency tree, which matters for the serverless bundle size limit.

---

## Running it

### Docker (recommended)

```bash
docker compose up --build
```

Then open <http://localhost:8080>. The API is also exposed directly on
<http://localhost:8000/docs> for review.

### Locally, without Docker

```bash
# API — http://localhost:8000
cd backend
python3 -m venv .venv && ./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/uvicorn app.main:app --port 8000

# Frontend — http://localhost:5199 (proxies /api to :8000)
cd frontend
npm install
npm run dev
```

### Tests

```bash
cd backend && ./.venv/bin/python -m pytest tests -q     # 34 tests
cd frontend && npm run typecheck && npm run build
```

### Rebuilding the data snapshot

```bash
cd backend
./.venv/bin/python -m app.ingest                  # the January 2026 window
./.venv/bin/python -m app.ingest 2026-02-01 2026-02-28
```

---

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Liveness |
| `GET /api/meta` | Snapshot provenance, study window, available WINDFOR runs |
| `GET /api/day?date=&deadline=&confidence=` | One delivery day: vintage used, hourly curve, band, cover table |
| `GET /api/accuracy?deadline=&from=&to=` | Headline metrics, bias correction, distribution, breakdowns |
| `GET /api/leadtime?from=&to=` | Error by horizon and by scheduled publication run |

`deadline` is a local Europe/London time and defaults to `09:30`. Interactive
docs at `/docs`.

---

## Deployment

Deployed on Vercel: the frontend is a static build, and `api/index.py` runs the
same FastAPI application as a Python serverless function, with `/api/*`
rewritten to it. Because both are served from one origin, the frontend's fetch
paths are identical in development, in Docker and in production — there is no
build-time API URL to get wrong, and no CORS to configure.

**Live app:** _<add the deployment URL here once deployed>_

```bash
npm i -g vercel && vercel --prod
```

---

## Known limitations

Worth stating plainly rather than leaving for a reviewer to find.

- **Scope is wind only.** The brief limited this to Elexon wind data, so the app
  sizes cover *relative to the wind forecast*. It does not model consumer
  demand, so it cannot output an absolute MW volume to buy. Adding a demand
  forecast is the obvious next step and would turn the cover table into a
  procurement instruction.
- **The curtailment hypothesis is inferred, not measured.** The evidence is
  strong (the capped outturn ceiling, the bias concentrated in high-wind hours)
  but confirming it needs BOALF/curtailment data, which was out of scope.
- **The bias correction is deliberately simple** — a trailing pooled mean. A
  correction conditioned on forecast level or on hour of day would likely do
  better; this one was chosen because it is explainable to a trading desk and
  cannot overfit.
- **One month of data.** January is a high-wind, heavily-constrained month.
  The *magnitude* of the bias should not be extrapolated to summer without
  re-running the analysis; the method carries over, the number does not.
- **No authentication.** It is a read-only pilot over public data.
- **The Docker setup has not been executed on this machine** — Docker was not
  installed on the development host. The Dockerfiles and compose file are
  written and reviewed but unbuilt; this should be verified before the demo.

---

## AI tool use

This application was built with AI assistance (Claude). AI was used for
scaffolding the FastAPI and React code, writing the test suite, and drafting
this documentation. The domain decisions — strict-inequality vintage selection
against gate closure, averaging outturn up rather than interpolating forecasts
down, local-clock delivery days, the trailing-only uncertainty band, and the
curtailment interpretation of the bias — were reviewed and verified against the
live Elexon data rather than accepted as generated.
