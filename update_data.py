import argparse
from database import init_db
from mlb import fetch_recent, build_hitter_pitcher_history, build_pitch_arsenal
from nfl import fetch_pbp, build_team_tendencies, build_defense_vs_position
from live_data import fetch_mlb_schedule, fetch_nfl_schedule, fetch_nfl_injuries, fetch_nfl_depth_charts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport", choices=["mlb","nfl","all"], default="all")
    parser.add_argument("--mlb-days", type=int, default=14)
    parser.add_argument("--nfl-season", type=int)
    args = parser.parse_args()
    init_db()

    if args.sport in ("mlb","all"):
        mlb = fetch_recent(args.mlb_days)
        build_hitter_pitcher_history(mlb)
        build_pitch_arsenal(mlb)
        sched = fetch_mlb_schedule()
        print(f"MLB rows: {len(mlb):,} | schedule games: {len(sched):,}")

    if args.sport in ("nfl","all"):
        nfl = fetch_pbp(args.nfl_season)
        build_team_tendencies(nfl)
        build_defense_vs_position(nfl)
        season = args.nfl_season
        sched = fetch_nfl_schedule(season)
        try:
            injuries = fetch_nfl_injuries(season)
            injury_count = len(injuries)
        except Exception as e:
            injury_count = 0
            print(f"NFL injuries unavailable: {e}")
        try:
            depth = fetch_nfl_depth_charts(season)
            depth_count = len(depth)
        except Exception as e:
            depth_count = 0
            print(f"NFL depth charts unavailable: {e}")
        print(f"NFL rows: {len(nfl):,} | schedule: {len(sched):,} | injuries: {injury_count:,} | depth: {depth_count:,}")

if __name__ == "__main__":
    main()
