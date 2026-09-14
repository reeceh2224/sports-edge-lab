from __future__ import annotations

from pathlib import Path
import pandas as pd

from config import PROCESSED_DIR


def _latest(pattern: str) -> Path | None:
    files = sorted(PROCESSED_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def mlb_pitcher_research(schedule: pd.DataFrame) -> pd.DataFrame:
    """Create non-betting research cards from schedule + cached pitcher arsenal data."""
    if schedule.empty:
        return pd.DataFrame()
    arsenal_file = PROCESSED_DIR / "mlb_pitch_arsenal.parquet"
    arsenal = pd.read_parquet(arsenal_file) if arsenal_file.exists() else pd.DataFrame()
    rows = []
    for _, g in schedule.iterrows():
        for side in ["away", "home"]:
            pid = g.get(f"{side}_probable_pitcher_id")
            pname = g.get(f"{side}_probable_pitcher")
            opp = g.get("home_team") if side == "away" else g.get("away_team")
            team = g.get(f"{side}_team")
            if pd.isna(pid) or not pname:
                continue
            sub = arsenal[arsenal["pitcher"] == pid].copy() if not arsenal.empty and "pitcher" in arsenal.columns else pd.DataFrame()
            top = []
            if not sub.empty:
                sub = sub.sort_values("usage", ascending=False).head(4)
                for _, r in sub.iterrows():
                    desc = f"{r['pitch_type']} {r['usage']:.0%}"
                    if pd.notna(r.get("velo")):
                        desc += f" · {r['velo']:.1f} mph"
                    top.append(desc)
            rows.append({
                "game": f"{g.get('away_team')} @ {g.get('home_team')}",
                "team": team,
                "opponent": opp,
                "player": pname,
                "player_id": int(pid),
                "lens": "Probable starting pitcher",
                "summary": "; ".join(top) if top else "Probable starter confirmed; Statcast arsenal cache not loaded yet.",
                "data_state": "Live schedule + cached Statcast" if top else "Live schedule only",
            })
    return pd.DataFrame(rows)


def nfl_team_research(schedule: pd.DataFrame, tendencies: pd.DataFrame | None = None) -> pd.DataFrame:
    """Create current-matchup team cards from free schedule + cached nflverse tendency features."""
    if schedule.empty:
        return pd.DataFrame()
    tendencies = tendencies if tendencies is not None else pd.DataFrame()
    rows = []
    for _, g in schedule.iterrows():
        away = g.get("away_team")
        home = g.get("home_team")
        for team, opp in [(away, home), (home, away)]:
            if not team:
                continue
            t = tendencies[tendencies["posteam"] == team].iloc[0] if (not tendencies.empty and "posteam" in tendencies and (tendencies["posteam"] == team).any()) else None
            if t is None:
                summary = "Current schedule matchup available; play-by-play tendency cache not loaded yet."
                state = "Live schedule only"
            else:
                summary = f"EPA/play {t['epa_per_play']:.3f} · success {t['success_rate']:.1%} · pass rate {t['pass_rate']:.1%} · shotgun {t['shotgun_rate']:.1%}"
                state = "Live schedule + cached nflverse"
            rows.append({"game": f"{away} @ {home}", "team": team, "opponent": opp, "lens": "Team offensive tendency", "summary": summary, "data_state": state})
    return pd.DataFrame(rows)
