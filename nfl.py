from datetime import date
import pandas as pd
from config import RAW_DIR, PROCESSED_DIR

PBP_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet"

def fetch_pbp(season: int | None = None) -> pd.DataFrame:
    """Free nflverse play-by-play parquet."""
    season = season or date.today().year
    url = PBP_URL.format(season=season)
    df = pd.read_parquet(url)
    df.to_parquet(RAW_DIR / f"nfl_pbp_{season}.parquet", index=False)
    return df

def build_team_tendencies(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ["posteam","defteam","play_type","epa","success","pass","rush","down","ydstogo","yardline_100","shotgun","no_huddle"] if c in df.columns]
    x = df[cols].copy()
    x = x[x.get("posteam").notna()]
    g = x.groupby("posteam").agg(
        plays=("posteam","size"),
        epa_per_play=("epa","mean"),
        success_rate=("success","mean"),
        pass_rate=("pass","mean"),
        rush_rate=("rush","mean"),
        shotgun_rate=("shotgun","mean"),
        no_huddle_rate=("no_huddle","mean"),
    ).reset_index()
    g.to_parquet(PROCESSED_DIR / "nfl_team_tendencies.parquet", index=False)
    return g

def build_defense_vs_position(df: pd.DataFrame) -> pd.DataFrame:
    required = ["defteam","receiver_player_id","receiver_player_name","receiving_yards","complete_pass","pass_attempt"]
    if not all(c in df.columns for c in required):
        return pd.DataFrame()
    rec = df[df["receiver_player_id"].notna()].copy()
    g = rec.groupby(["defteam","receiver_player_id","receiver_player_name"]).agg(
        targets=("pass_attempt","sum"), receptions=("complete_pass","sum"), yards=("receiving_yards","sum")
    ).reset_index()
    g.to_parquet(PROCESSED_DIR / "nfl_defense_receiver_history.parquet", index=False)
    return g
