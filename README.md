# ValueScope

ValueScope is a local-first value investing research workstation and screener.

The first version focuses on reproducing the A-share financial report workflow from `stock-scripts` as a ValueScope-owned Python data pipeline plus a React report UI. Dynamic factor screening comes after the report capability exists. The long-term product should support global equities without requiring a database for normal offline use.

## First Version

- Market: A shares first.
- Storage: local JSON snapshots.
- Snapshot generation: ValueScope-owned Python pipeline that reproduces the needed stock financial report capabilities.
- App stack: Vite, React, TypeScript, Zod, Vitest, Playwright, FastAPI, and the ValueScope Python package.
- Core workflow: trigger local Python report generation from the report workspace, produce a single-stock financial report snapshot, validate it, and render it in React.
- Data source direction: study `stock-scripts` for proven A-share metric language and workflows, but do not depend on it at runtime.
- Product reference: terminal-style workflow inspired by `QuantumValue-Terminal`, but this is a new project.

## Non-Goals for MVP

- No database dependency.
- No full global market coverage yet.
- No live trading or brokerage integration.
- No automatic buy/sell or position-size decision as the first feature.
- No opaque AI recommendation engine.

## Next Step

Run the local generator:

```bash
python3 -m pip install -e '.[test]'
PYTHONPATH=python python3 -m valuescope.cli 000858 --years 10
```

This writes `data/report_snapshots/company_report_snapshot.json`. The committed browser sample is `public/samples/company_report_snapshot.json` and currently uses report snapshot schema v0.2 with current price, market context, valuation explanations, PE/EPS percentile nodes, and yearly valuation tables.

Run the MVP locally:

```bash
python3 -m pip install -e '.[test]'
npm install

PYTHONPATH=python uvicorn valuescope.api:app --reload
npm run dev
```

Open `http://127.0.0.1:5173`. The page loads the committed sample first and can call the local FastAPI bridge to generate a fresh report snapshot.

Run the FastAPI bridge by itself:

```bash
PYTHONPATH=python uvicorn valuescope.api:app --reload
```

Validation commands:

```bash
PYTHONPATH=python python3 -m pytest tests/python -q
npm test -- --run
npm run build
npm run test:e2e
```
