from datetime import date, timedelta
from pathlib import Path
import pandas as pd
from pybaseball import statcast
from config import RAW_DIR, PROCESSED_DIR

STATCAST_KEEP = [
    "game_date","game_pk","home_team","away_team","inning","inning_topbot",
    "batter","pitcher","player_name","stand","p_throws","pitch_type","release_speed",
    "release_spin_rate","pfx_x","pfx_z","plate_x","plate_z","zone","description","events",
    "launch_speed","launch_angle","estimated_woba_using_speedangle","woba_value","babip_value",
    "iso_value","bb_type","hc_x","hc_y","outs_when_up","on_1b","on_2b","on_3b",
    "fielder_2","fielder_3","fielder_4","fielder_5","fielder_6","fielder_7","fielder_8","fielder_9"
]

def fetch_statcast(start: str, end: str) -> pd.DataFrame:
    """Free MLB Statcast data via pybaseball/Baseball Savant."""
    df = statcast(start_dt=start, end_dt=end)
    keep = [c for c in STATCAST_KEEP if c in df.columns]
    df = df[keep].copy()
    out = RAW_DIR / f"mlb_statcast_{start}_{end}.parquet"
    df.to_parquet(out, index=False)
    return df

def fetch_recent(days: int = 14) -> pd.DataFrame:
    end = date.today()
    start = end - timedelta(days=days)
    return fetch_statcast(start.isoformat(), end.isoformat())

def build_hitter_pitcher_history(df: pd.DataFrame) -> pd.DataFrame:
    pa = df[df["events"].notna()].copy()
    pa["hit"] = pa["events"].isin(["single","double","triple","home_run"]).astype(int)
    pa["hr"] = (pa["events"] == "home_run").astype(int)
    pa["walk"] = pa["events"].isin(["walk","intent_walk"]).astype(int)
    pa["strikeout"] = pa["events"].isin(["strikeout","strikeout_double_play"]).astype(int)
    g = pa.groupby(["batter","pitcher"], dropna=False).agg(
        pa=("events","size"), hits=("hit","sum"), hr=("hr","sum"), bb=("walk","sum"), so=("strikeout","sum")
    ).reset_index()
    g["hit_rate"] = g["hits"] / g["pa"].clip(lower=1)
    g.to_parquet(PROCESSED_DIR / "mlb_batter_pitcher_history.parquet", index=False)
    return g

def build_pitch_arsenal(df: pd.DataFrame) -> pd.DataFrame:
    p = df[df["pitch_type"].notna()].copy()
    g = p.groupby(["pitcher","pitch_type"]).agg(
        pitches=("pitch_type","size"), velo=("release_speed","mean"), spin=("release_spin_rate","mean"),
        xmov=("pfx_x","mean"), zmov=("pfx_z","mean")
    ).reset_index()
    totals = g.groupby("pitcher")["pitches"].transform("sum")
    g["usage"] = g["pitches"] / totals
    g.to_parquet(PROCESSED_DIR / "mlb_pitch_arsenal.parquet", index=False)
    return g
