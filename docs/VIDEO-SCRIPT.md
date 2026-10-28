# Demo video script (10 minutes)

Two parts, five minutes each. Record the app at 1440px wide, dark theme.

---

## Part 1 — To the client (5:00)

**0:00–0:30 — The problem in their words.**
> "Every morning your team commits to buying power for tomorrow, and the single
> biggest unknown is how much wind you'll get for free. You decide before 09:30,
> and the wind shows up 24 hours later. This pilot looks at every decision you
> would have made in January 2026 and asks two things: what did you actually
> know at 09:30, and how wrong was it?"

**0:30–2:00 — The day-ahead desk.** Open on the Desk tab, 15 January.
- Point at the vintage line: *"This is the honest bit. Not the best forecast
  that exists for the 15th — the 07:30 run, the last one published before the
  N2EX deadline. That's what you'd have had on screen."*
- The curve: forecast, outturn, shaded band.
- *"The band isn't a model assumption. It's your own forecast's track record
  over the previous fortnight, and it only uses days before this one."*
- The cover table: *"Translate that into an instruction: buy this much firm
  cover on top and you're short in at most one hour in ten."*

**2:00–4:15 — The finding.** Switch to Forecast accuracy.
- Tiles first: MAE 2,039 MW, bias +1,748 MW, **short in 85% of hours**.
- Pause on 85%. *"That's not a forecast that's randomly wrong. That's a
  forecast that's wrong in one direction, almost every hour."*
- The bias-correction panel: *"1,300 GWh of under-procurement over one month —
  volume you bought back late, when it costs most. But because the error is a
  lean and not noise, you can subtract it. Trailing 14 days, nothing you
  wouldn't have known on the morning. Error drops 28%, bias goes from +1,748
  to +117."*
- Why: *"Much of this isn't the weather. FUELHH measures what the fleet
  delivered after curtailment; WINDFOR describes the wind that was available.
  You can see it in the data — forecasts reach 21 GW, outturn never passes 18."*
- The output-band chart as evidence: *"Worst exactly when it's windiest, which
  is when the Scottish constraint binds."*

**4:15–5:00 — Close.**
- Skill vs persistence 54%: *"The forecast is worth using. It just needs
  de-biasing first."*
- *"Three things from the pilot: use the pre-deadline vintage, apply a rolling
  bias correction, size cover from the empirical error. The next step that
  makes this a procurement tool rather than an analysis tool is your demand
  forecast — then this outputs MW to buy, not MW of adjustment."*

---

## Part 2 — To the tech lead (5:00)

**0:00–0:45 — Shape.** The diagram in `docs/ARCHITECTURE.md`.
- React/Vite → FastAPI → committed snapshot.
- *"One origin in all three environments — Vite proxy, nginx, Vercel rewrite.
  The frontend never knows an API host, so there's no build-time URL to get
  wrong and no CORS to configure."*
- `api/index.py`: *"Nine lines. Re-exports the same app the container runs —
  no second serverless implementation to drift."*

**0:45–2:30 — Where the risk is.** Open `backend/app/align.py`.
- *"The plumbing is boring on purpose. All the risk is in three decisions."*
- **Vintage**: show `select_vintage`, the strict `<`. *"The 09:30 run is stamped
  at the same minute the auction closes. Using it would score the desk on
  information it never had. Strict inequality, and a test that pins it."*
- **Resolution**: *"WINDFOR hourly, FUELHH half-hourly. We average outturn up
  rather than interpolating the forecast down — interpolating invents forecast
  information that never existed."*
- **Calendar**: *"Local-clock days, not UTC. Tested on both GMT and BST, because
  this breaks silently in summer."*
- *"Each one is commented at its definition and pinned by a named test."*

**2:30–3:30 — Layering and tests.**
- *"`metrics.py` takes a DataFrame and returns dicts. It doesn't know HTTP
  exists, which is why it's cheap to test. `align.py` doesn't know what a
  metric is. `main.py` does no arithmetic."*
- Run `pytest -q` on camera — 34 passing.
- *"Three layers: judgement calls on hand-built frames; statistics on synthetic
  data with analytically known answers — a constant +1000 MW lean must correct
  to zero; and integration against the real snapshot, which also guards the
  data itself."*
- *"The headline finding has its own regression test, so a refactor can't
  silently invalidate it."*

**3:30–4:15 — Data and deployment.**
- *"Snapshot-first. The window is historical and immutable, so it's pinned —
  112 KB, committed. Reproducible demo, millisecond cold start, and a BMRS
  outage can't take down a client call. `/api/meta` reports provenance."*
- *"Gzipped CSV rather than Parquet — deliberate, keeps pyarrow out of the
  serverless bundle."*
- `docker compose up --build`. Multi-stage, unprivileged, healthchecked.

**4:15–5:00 — Honest close.**
- *"Limitations are in the README, not hidden. Wind only, so cover is relative
  — no demand model. The curtailment explanation is inferred from the outturn
  ceiling and the high-wind bias concentration, not measured; confirming it
  needs BOALF data. One month, so the method generalises but the number
  shouldn't be extrapolated to summer."*
- *"Next: demand data, confirm curtailment with BOALF, test a conditional bias
  correction against the pooled one, and price the error in £ via imbalance."*
