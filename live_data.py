from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any
import json

import pandas as pd
import requests

from config import RAW_DIR

MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
NFL_SCHEDULE_CSV = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
NFL_INJURY_URL = "https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{season}.parquet"
NFL_DEPTH_URL = "https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_{season}.parquet"


def _get_json(url: str, params: dict[str, Any] | None = None, timeout: int = 20) -> dict:
    r = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": "SportsEdgeLab/0.2"})
    r.raise_for_status()
    return r.json()


def fetch_mlb_schedule(day: str | date | None = None) -> pd.DataFrame:
    """Fetch one day of MLB schedule/probable-pitcher metadata from the public Stats API."""
    if day is None:
        day = date.today()
    if isinstance(day, date):
        day = day.isoformat()
    payload = _get_json(
        MLB_SCHEDULE_URL,
        params={"sportId": 1, "date": day, "hydrate": "team,linescore,probablePitcher"},
    )
    rows: list[dict[str, Any]] = []
    for d in payload.get("dates", []):
        for g in d.get("games", []):
            away = g.get("teams", {}).get("away", {})
            home = g.get("teams", {}).get("home", {})
            rows.append({
                "game_id": g.get("gamePk"),
                "game_date": d.get("date"),
                "game_datetime": g.get("gameDate"),
                "status": g.get("status", {}).get("detailedState"),
                "away_team": away.get("team", {}).get("name"),
                "away_abbr": away.get("team", {}).get("abbreviation"),
                "away_score": away.get("score"),
                "away_probable_pitcher": away.get("probablePitcher", {}).get("fullName"),
                "away_probable_pitcher_id": away.get("probablePitcher", {}).get("id"),
                "home_team": home.get("team", {}).get("name"),
                "home_abbr": home.get("team", {}).get("abbreviation"),
                "home_score": home.get("score"),
                "home_probable_pitcher": home.get("probablePitcher", {}).get("fullName"),
                "home_probable_pitcher_id": home.get("probablePitcher", {}).get("id"),
                "venue": g.get("venue", {}).get("name"),
                "series": g.get("seriesDescription"),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(RAW_DIR / f"mlb_schedule_{day}.parquet", index=False)
    return df


def fetch_nfl_schedule(season: int | None = None) -> pd.DataFrame:
    """Fetch free NFL game/schedule metadata maintained by nflverse/nfldata."""
    season = season or date.today().year
    df = pd.read_csv(NFL_SCHEDULE_CSV)
    if "season" in df.columns:
        df = df[df["season"] == season].copy()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(RAW_DIR / f"nfl_schedule_{season}.parquet", index=False)
    return df


def fetch_nfl_injuries(season: int | None = None) -> pd.DataFrame:
    season = season or date.today().year
    df = pd.read_parquet(NFL_INJURY_URL.format(season=season))
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(RAW_DIR / f"nfl_injuries_{season}.parquet", index=False)
    return df


def fetch_nfl_depth_charts(season: int | None = None) -> pd.DataFrame:
    season = season or date.today().year
    df = pd.read_parquet(NFL_DEPTH_URL.format(season=season))
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(RAW_DIR / f"nfl_depth_charts_{season}.parquet", index=False)
    return df


def data_health() -> pd.DataFrame:
    """Show which locally cached live/free datasets are present and how old they are."""
    rows = []
    for pattern, label in [
        ("mlb_schedule_*.parquet", "MLB schedule"),
        ("mlb_statcast_*.parquet", "MLB Statcast"),
        ("nfl_schedule_*.parquet", "NFL schedule"),
        ("nfl_pbp_*.parquet", "NFL play-by-play"),
        ("nfl_injuries_*.parquet", "NFL injuries"),
        ("nfl_depth_charts_*.parquet", "NFL depth charts"),
    ]:
        matches = sorted(RAW_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if matches:
            p = matches[0]
            stamp = datetime.fromtimestamp(p.stat().st_mtime)
            rows.append({"dataset": label, "status": "Cached", "latest_file": p.name, "updated": stamp.isoformat(timespec="minutes")})
        else:
            rows.append({"dataset": label, "status": "Not cached", "latest_file": "—", "updated": "—"})
    return pd.DataFrame(rows)
