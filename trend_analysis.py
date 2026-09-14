from __future__ import annotations

from datetime import date
import math
import re
from functools import lru_cache

import pandas as pd
import requests

from public_odds import american_to_prob

HEADERS = {"User-Agent": "SportsEdgeLab/1.0"}


def _norm_name(s: str) -> str:
    s = re.sub(r"\([^)]*\)", "", str(s))
    s = re.sub(r"[^a-zA-Z0-9 .'-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def split_player_market(market: str, sport: str) -> tuple[str, str]:
    m = _norm_name(market)
    phrases = [
        "Hits + Runs + RBIs", "Strikeouts Thrown", "Total Bases", "Home Runs", "Runs Scored", "Stolen Bases",
        "Passing Yards", "Passing Touchdowns", "Passing Attempts", "Pass Completions", "Rushing Yards",
        "Rushing Attempts", "Receiving Yards", "Receptions", "Receiving Touchdowns", "Anytime Touchdown",
    ]
    for p in phrases:
        idx = m.lower().find(p.lower())
        if idx > 0:
            return m[:idx].strip(), p
    # Fallback: keep the whole label; no analysis will be claimed if unsupported.
    return "", m


def parse_threshold(line: str) -> tuple[str, float] | None:
    s = str(line).replace("−", "-").strip()
    # DK Network commonly exposes alt milestones such as 2+ or 1+.
    m = re.search(r"(\d+(?:\.\d+)?)\s*\+", s)
    if m:
        return ">=", float(m.group(1))
    m = re.search(r"\b(Over|Under)\s*(\d+(?:\.\d+)?)", s, re.I)
    if m:
        return (">" if m.group(1).lower() == "over" else "<"), float(m.group(2))
    return None


def _hit(value: float, op: str, threshold: float) -> bool:
    if op == ">=": return value >= threshold
    if op == ">": return value > threshold
    if op == "<": return value < threshold
    return False


def _trend_summary(values: list[float], op: str, threshold: float) -> dict | None:
    vals = [float(v) for v in values if pd.notna(v)]
    if len(vals) < 3:
        return None
    def chunk(n):
        x = vals[-n:] if len(vals) >= n else vals
        return {
            "n": len(x),
            "avg": sum(x) / len(x),
            "hit_rate": sum(_hit(v, op, threshold) for v in x) / len(x),
        }
    return {"last5": chunk(5), "last10": chunk(10), "season": chunk(len(vals)), "games": len(vals)}


def _grade(edge: float | None, games: int) -> str:
    if edge is None or games < 4: return "PASS"
    if edge >= 0.12 and games >= 8: return "STRONG LOOK"
    if edge >= 0.07 and games >= 6: return "LEAN"
    if edge <= -0.07: return "AVOID"
    return "PASS"


@lru_cache(maxsize=256)
def _mlb_people_search(name: str) -> dict | None:
    url = "https://statsapi.mlb.com/api/v1/people/search"
    r = requests.get(url, params={"names": name}, headers=HEADERS, timeout=15)
    r.raise_for_status()
    people = r.json().get("people", [])
    return people[0] if people else None


@lru_cache(maxsize=512)
def _mlb_game_log(player_id: int, group: str, season: int) -> list[dict]:
    url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats"
    r = requests.get(url, params={"stats": "gameLog", "group": group, "season": season}, headers=HEADERS, timeout=20)
    r.raise_for_status()
    splits = []
    for block in r.json().get("stats", []):
        splits.extend(block.get("splits", []))
    return splits


def analyze_mlb_prop(market: str, line: str, odds: str) -> dict | None:
    player, prop = split_player_market(market, "MLB")
    parsed = parse_threshold(line)
    if not player or not parsed:
        return None
    op, threshold = parsed
    person = _mlb_people_search(player)
    if not person:
        return None
    pid = int(person["id"])
    pitching = prop == "Strikeouts Thrown"
    logs = _mlb_game_log(pid, "pitching" if pitching else "hitting", date.today().year)
    values = []
    for g in logs:
        stat = g.get("stat", {}) or {}
        try:
            if prop == "Strikeouts Thrown": v = float(stat.get("strikeOuts", 0))
            elif prop == "Home Runs": v = float(stat.get("homeRuns", 0))
            elif prop == "Total Bases": v = float(stat.get("totalBases", 0))
            elif prop == "Runs Scored": v = float(stat.get("runs", 0))
            elif prop == "Stolen Bases": v = float(stat.get("stolenBases", 0))
            elif prop == "Hits + Runs + RBIs": v = float(stat.get("hits", 0)) + float(stat.get("runs", 0)) + float(stat.get("rbi", 0))
            elif prop.lower().startswith("hits"): v = float(stat.get("hits", 0))
            else: return None
            values.append(v)
        except Exception:
            continue
    trend = _trend_summary(values, op, threshold)
    if not trend:
        return None
    # Recency-weighted empirical baseline. It is intentionally labeled a trend probability,
    # not a full predictive model, because matchup/lineup/weather adjustments are not yet all present.
    p = 0.50 * trend["last5"]["hit_rate"] + 0.30 * trend["last10"]["hit_rate"] + 0.20 * trend["season"]["hit_rate"]
    implied = american_to_prob(odds)
    edge = (p - implied) if implied is not None else None
    return {
        "player": player, "prop": prop, "threshold": threshold, "operator": op,
        "trend_probability": p, "implied_probability": implied, "edge": edge,
        "grade": _grade(edge, trend["games"]), **trend,
    }


@lru_cache(maxsize=4)
def _nfl_player_stats(season: int) -> pd.DataFrame:
    import nflreadpy as nfl
    df = nfl.load_player_stats(seasons=season, summary_level="week").to_pandas()
    return df


def analyze_nfl_prop(market: str, line: str, odds: str) -> dict | None:
    player, prop = split_player_market(market, "NFL")
    parsed = parse_threshold(line)
    if not player or not parsed:
        return None
    op, threshold = parsed
    df = _nfl_player_stats(date.today().year)
    name_col = "player_display_name" if "player_display_name" in df.columns else "player_name"
    x = df[df[name_col].astype(str).str.lower() == player.lower()].copy()
    if x.empty:
        # Loose fallback for punctuation/suffixes.
        x = df[df[name_col].astype(str).str.lower().str.contains(re.escape(player.lower()), regex=True, na=False)].copy()
    if x.empty:
        return None
    stat_map = {
        "Passing Yards": "passing_yards", "Passing Touchdowns": "passing_tds", "Passing Attempts": "attempts",
        "Pass Completions": "completions", "Rushing Yards": "rushing_yards", "Rushing Attempts": "carries",
        "Receiving Yards": "receiving_yards", "Receptions": "receptions", "Receiving Touchdowns": "receiving_tds",
    }
    col = stat_map.get(prop)
    if not col or col not in x.columns:
        return None
    if "week" in x.columns:
        x = x.sort_values("week")
    trend = _trend_summary(pd.to_numeric(x[col], errors="coerce").dropna().tolist(), op, threshold)
    if not trend:
        return None
    p = 0.50 * trend["last5"]["hit_rate"] + 0.30 * trend["last10"]["hit_rate"] + 0.20 * trend["season"]["hit_rate"]
    implied = american_to_prob(odds)
    edge = (p - implied) if implied is not None else None
    return {
        "player": player, "prop": prop, "threshold": threshold, "operator": op,
        "trend_probability": p, "implied_probability": implied, "edge": edge,
        "grade": _grade(edge, trend["games"]), **trend,
    }


def analyze_prop(sport: str, market: str, line: str, odds: str) -> dict | None:
    try:
        return analyze_mlb_prop(market, line, odds) if sport == "MLB" else analyze_nfl_prop(market, line, odds)
    except Exception:
        return None
