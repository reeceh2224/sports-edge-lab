# Sports Edge Lab

A $0-data-cost prototype for deep MLB + NFL matchup analysis.

## What is implemented

- Mobile-friendly Streamlit dashboard shell
- MLB and NFL ranked matchup cards
- Evidence-for / evidence-against explanations
- Sample-size-aware helper functions
- American-odds implied probability and model-edge calculation
- SQLite audit trail for predictions
- Free MLB Statcast ingestion through `pybaseball`
- MLB batter-vs-pitcher and pitcher-arsenal feature builders
- Free NFL play-by-play ingestion through `nflverse`
- NFL team-tendency and defense/receiver-history feature builders
- Manual sportsbook odds entry so v1 does not require a paid odds API
- Clearly labeled demo review data so the UI can be inspected before live hosting

## Core design rule

The model never treats a tiny historical matchup as decisive. Direct history is shrunk toward broader baselines and weighted by sample size, recency, and (for coaching/scheme context) continuity.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
streamlit run app.py
```

## Load free raw data

MLB recent Statcast:

```bash
python update_data.py --sport mlb --mlb-days 14
```

NFL current-season play-by-play:

```bash
python update_data.py --sport nfl --nfl-season 2026
```

## Important limitation of the review build

The cards visible immediately are DEMO examples so no fabricated/current betting recommendation is presented as live. When deployed on an internet-connected host, the ingestion pipelines can populate the database and the next model layer can generate live matchup features.

## Zero-dollar source strategy

- MLB Baseball Savant / Statcast
- pybaseball for public-data retrieval
- MLB public game metadata endpoints for schedule/probable-starter metadata
- nflverse / nflfastR public datasets
- public official league/team pages for supplemental verification
- manual market-line entry in v1

No paid data provider is required by the architecture.

## Added in the live-data build

- On-demand MLB schedule ingestion from the public MLB Stats API, including probable pitchers when available
- On-demand NFL schedule ingestion from nflverse/nfldata
- Free NFL injury and depth-chart adapters from nflverse releases
- Live Research tab for current schedule/matchup context
- Data Health tab that clearly shows which datasets are cached/current versus unavailable
- Current matchup research cards that combine live schedule metadata with cached Statcast/nflverse features when available
- No fabricated live odds: sportsbook lines remain manual until a reliable legitimate $0 feed is available

### Live-data behavior

The app is designed to fail honestly. If a free source is unreachable, stale, or missing a required field, that input is marked unavailable and the app does not silently replace it with a made-up value.
