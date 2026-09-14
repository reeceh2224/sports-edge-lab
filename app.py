from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from config import DB_PATH, PROCESSED_DIR
from database import init_db
from demo_data import (
    mlb_board,
    nfl_board,
    source_table,
    mlb_bet_explorer,
    nfl_bet_explorer,
)
from common import american_to_implied
from live_data import (
    fetch_mlb_schedule,
    fetch_nfl_schedule,
    fetch_nfl_injuries,
    fetch_nfl_depth_charts,
    data_health,
)
from research_cards import mlb_pitcher_research, nfl_team_research

st.set_page_config(
    page_title="Sports Edge Lab",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)
init_db()

st.markdown(
    """
<style>
.block-container {padding-top: .9rem; padding-bottom: 5rem; max-width: 1200px;}
[data-testid="stMetric"] {border:1px solid rgba(128,128,128,.22); border-radius:12px; padding:10px 12px;}
.smallnote {opacity:.72; font-size:.88rem;}
.demo-pill {display:inline-block; padding:3px 8px; border-radius:999px; border:1px solid rgba(128,128,128,.35); font-size:.72rem; font-weight:700;}
.live-pill {display:inline-block; padding:3px 8px; border-radius:999px; border:1px solid rgba(74,222,128,.45); font-size:.72rem; font-weight:700;}
section[data-testid="stSidebar"] {min-width: 0px;}
@media (max-width: 700px) {
  .block-container {padding-left: 1rem; padding-right: 1rem; padding-top: .65rem;}
  h1 {font-size: 2.2rem !important;}
  h2 {font-size: 1.65rem !important;}
  h3 {font-size: 1.25rem !important;}
}
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=300, show_spinner=False)
def cached_mlb_schedule(day_iso: str) -> pd.DataFrame:
    return fetch_mlb_schedule(day_iso)


@st.cache_data(ttl=900, show_spinner=False)
def cached_nfl_schedule(season: int) -> pd.DataFrame:
    return fetch_nfl_schedule(season)


@st.cache_data(ttl=1800, show_spinner=False)
def cached_nfl_injuries(season: int) -> pd.DataFrame:
    return fetch_nfl_injuries(season)


@st.cache_data(ttl=1800, show_spinner=False)
def cached_nfl_depth(season: int) -> pd.DataFrame:
    return fetch_nfl_depth_charts(season)


def fmt_pct(v):
    return "—" if pd.isna(v) else f"{v:.1%}"


def odds_text(value):
    try:
        f = float(value)
    except Exception:
        return "—"
    i = int(f) if f.is_integer() else f
    return f"+{i}" if f > 0 else str(i)


def render_pick(row):
    st.markdown(
        f"### #{int(row['rank'])} · {row['selection']}  <span class='demo-pill'>{row['status']}</span>",
        unsafe_allow_html=True,
    )
    line = row.get("bet_line", None)
    line_text = "—" if pd.isna(line) else f"{line:g}"
    book = row.get("sportsbook", "Manual / unavailable")
    st.caption(f"{row['game']} · {row['market']} · Sample: {row['sample']} · {book}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Bet line", line_text)
    c2.metric("Odds", odds_text(row["market_odds"]))
    c3.metric("Projection", f"{row['projection']:.2f}")
    c4.metric("Confidence", f"{row['confidence']:.1f}/10")
    c1, c2, c3 = st.columns(3)
    c1.metric("Model probability", fmt_pct(row["model_probability"]))
    c2.metric("Market implied", fmt_pct(row["implied_probability"]))
    c3.metric("Model edge", f"{row['edge']:+.1%}")
    a, b = st.columns(2)
    with a:
        st.markdown("**Evidence for**")
        for x in row["evidence_for"]:
            st.markdown(f"- {x}")
    with b:
        st.markdown("**Evidence against / uncertainty**")
        for x in row["evidence_against"]:
            st.markdown(f"- {x}")
    with st.expander("Open detailed matchup lenses"):
        for k, v in row["details"].items():
            st.markdown(f"**{k}:** {v}")


def load_live_schedule(sport: str, force: bool = False) -> tuple[pd.DataFrame, str]:
    """Return current schedule and a human-readable state. Never substitutes demo data."""
    try:
        if sport == "MLB":
            day_iso = date.today().isoformat()
            if force:
                cached_mlb_schedule.clear()
            live = cached_mlb_schedule(day_iso)
            return live, f"MLB schedule · {day_iso}"
        season = date.today().year
        if force:
            cached_nfl_schedule.clear()
        live = cached_nfl_schedule(season)
        if live.empty:
            return live, f"NFL {season} schedule"
        date_col = next((c for c in ["gameday", "game_date", "date"] if c in live.columns), None)
        if date_col:
            today = pd.Timestamp.now().date()
            parsed = pd.to_datetime(live[date_col], errors="coerce").dt.date
            # Show roughly the next two weeks / 24 games rather than the full season.
            live = live[parsed >= today].sort_values(date_col).head(24).copy()
        return live, f"NFL {season} upcoming schedule"
    except Exception as exc:
        return pd.DataFrame(), f"Live source unavailable: {exc}"


def render_live_home(sport: str):
    st.subheader(f"{sport} Live Home")
    st.caption("Current matchup information from free public sources. No sportsbook price is invented when a live price is unavailable.")

    left, right = st.columns([1, 2])
    with left:
        refresh = st.button("Refresh live data", type="primary", use_container_width=True)
    with right:
        st.caption("Schedules are cached briefly to keep the free site fast. Refresh forces a new pull.")

    with st.spinner("Loading current matchups…"):
        live, state = load_live_schedule(sport, force=refresh)

    if live.empty:
        st.warning(state)
        st.info("The demo/model sandbox is still available below, but it will never be labeled as a live pick.")
        return

    st.markdown("<span class='live-pill'>LIVE SOURCE</span>", unsafe_allow_html=True)
    st.caption(state)

    if sport == "MLB":
        cols = [
            c
            for c in [
                "game_datetime",
                "away_team",
                "home_team",
                "away_probable_pitcher",
                "home_probable_pitcher",
                "venue",
                "status",
            ]
            if c in live.columns
        ]
        st.dataframe(live[cols], use_container_width=True, hide_index=True)
        cards = mlb_pitcher_research(live)
        if not cards.empty:
            st.markdown("#### Probable starters")
            for _, r in cards.iterrows():
                with st.expander(f"{r['player']} · {r['team']} vs {r['opponent']}"):
                    st.write(r["summary"])
                    st.caption(r["data_state"])
    else:
        date_col = next((c for c in ["gameday", "game_date", "date"] if c in live.columns), None)
        show_cols = [
            c
            for c in [date_col, "week", "away_team", "home_team", "stadium", "roof", "surface", "temp", "wind"]
            if c and c in live.columns
        ]
        st.dataframe(live[show_cols] if show_cols else live, use_container_width=True, hide_index=True)
        tp = PROCESSED_DIR / "nfl_team_tendencies.parquet"
        tendencies = pd.read_parquet(tp) if tp.exists() else pd.DataFrame()
        cards = nfl_team_research(live, tendencies)
        if not cards.empty:
            st.markdown("#### Matchup tendency cards")
            for _, r in cards.head(24).iterrows():
                with st.expander(f"{r['team']} vs {r['opponent']}"):
                    st.write(r["summary"])
                    st.caption(r["data_state"])

        with st.expander("Load current NFL injuries + depth charts"):
            st.caption("These are larger free nflverse files, so they load only when requested.")
            if st.button("Load NFL roster context"):
                try:
                    season = date.today().year
                    injuries = cached_nfl_injuries(season)
                    depth = cached_nfl_depth(season)
                    st.success(f"Loaded {len(injuries):,} injury rows and {len(depth):,} depth-chart rows.")
                    st.dataframe(injuries.tail(100), use_container_width=True, hide_index=True)
                except Exception as exc:
                    st.error(f"NFL roster context could not be loaded: {exc}")


st.title("Sports Edge Lab")
st.caption("$0-data-cost MLB + NFL matchup intelligence • explainable signals • sample-size aware")

sport = st.radio("Sport", ["MLB", "NFL"], horizontal=True, label_visibility="collapsed")
page = st.selectbox(
    "Section",
    [
        "Live Home",
        "Sportsbook Lines",
        "Player & Bet Explorer",
        "Matchup Lab",
        "Demo Model Board",
        "Model History",
        "Data Health",
        "Data Sources",
    ],
    index=0,
)

board = mlb_board() if sport == "MLB" else nfl_board()

if page == "Live Home":
    render_live_home(sport)

elif page == "Sportsbook Lines":
    st.subheader("Sportsbook Lines")
    st.caption("Enter a current DraftKings or Fliff line you can see. Sports Edge Lab calculates implied probability and model-vs-market difference without scraping either sportsbook.")
    book = st.selectbox("Sportsbook", ["DraftKings", "Fliff"])
    c1, c2 = st.columns(2)
    with c1:
        market_name = st.text_input("Market", placeholder="e.g. Bobby Witt Jr. total bases")
        bet_line = st.number_input("Bet line", value=1.5, step=0.5)
    with c2:
        american_odds = st.number_input("American odds", value=-110, step=5)
        model_pct = st.slider("Your/model probability", 1.0, 99.0, 56.0, 0.1) / 100
    implied = american_to_implied(american_odds)
    diff = model_pct - implied
    c1, c2, c3 = st.columns(3)
    c1.metric("Market implied", fmt_pct(implied))
    c2.metric("Model probability", fmt_pct(model_pct))
    c3.metric("Difference", f"{diff:+.1%}")
    if market_name:
        st.info(f"{book}: {market_name} · line {bet_line:g} · {odds_text(american_odds)}")
    st.caption("Positive model-vs-market difference is not a guarantee of profit. Calibration and sample quality still matter.")

elif page == "Player & Bet Explorer":
    st.subheader(f"{sport} Player & Bet Explorer")
    st.warning("This explorer currently demonstrates the modeled market layout. Values marked as demo are not live sportsbook picks.", icon="⚠️")
    explorer = mlb_bet_explorer() if sport == "MLB" else nfl_bet_explorer()
    mode = st.radio("Explore by", ["Game", "Player"], horizontal=True)
    if mode == "Game":
        chosen_game = st.selectbox("Game", explorer["game"].drop_duplicates().tolist())
        shown = explorer[explorer["game"] == chosen_game].copy()
    else:
        players = [x for x in explorer["player"].drop_duplicates().tolist() if x != "Game"]
        chosen_player = st.selectbox("Player", players)
        shown = explorer[explorer["player"] == chosen_player].copy()

    verdict_filter = st.multiselect(
        "Verdict filter",
        shown["verdict"].drop_duplicates().tolist(),
        default=shown["verdict"].drop_duplicates().tolist(),
    )
    shown = shown[shown["verdict"].isin(verdict_filter)]
    for _, r in shown.iterrows():
        st.markdown(f"### {r['market']} · {r['selection']}")
        st.caption(f"{r['game']} · {r['category']} · Verdict: {r['verdict']} · Sample: {r['sample']} · DEMO")
        c1, c2, c3 = st.columns(3)
        projection = r["projection"]
        c1.metric("Projection", fmt_pct(projection) if r["market"] == "Moneyline" else f"{projection:.2f}")
        c2.metric("Model probability", fmt_pct(r["model_probability"]))
        c3.metric("Confidence", f"{r['confidence']:.1f}/10")
        a, b = st.columns(2)
        with a:
            st.markdown("**Why it could be good**")
            for x in r["why_good"]:
                st.markdown(f"- {x}")
        with b:
            st.markdown("**Why it may be a bad bet / what could go wrong**")
            for x in r["why_bad"]:
                st.markdown(f"- {x}")
        st.divider()

elif page == "Matchup Lab":
    st.subheader(f"{sport} Matchup Lab")
    st.caption("Research checklist used to build a market view. The example card below is demo data until the full live feature pipeline is populated.")
    selected = st.selectbox("Example matchup", board["selection"].tolist())
    row = board.loc[board["selection"] == selected].iloc[0]
    render_pick(row)
    st.markdown("#### What the engine is designed to inspect")
    if sport == "MLB":
        buckets = {
            "Starting pitcher": "Pitch mix, velocity/spin/movement trends, K/BB, whiff/CSW proxies, batted-ball quality, platoon splits, times through order, prior opponent/hitter history.",
            "Hitter": "Pitch-type results, handedness, rolling EV/barrels/contact, chase/whiff where available, lineup slot, park context, direct pitcher history with sample shrinkage.",
            "Bullpen": "Reliever quality, handedness mix, recent pitches/appearances and likely availability.",
            "Catcher & running game": "Catcher throwing/pop-time context when available, caught-stealing results, runner speed/attempt/success and pitcher runner-control context.",
            "Defense": "Statcast defensive value/range where available, arm strength and position context.",
            "Environment": "Park, home/road, day/night, weather hook, travel/rest and lineup confirmation.",
        }
    else:
        buckets = {
            "Offense": "EPA/play, success, explosives, early-down tendencies, neutral pass rate, red zone, pace and usage proxies.",
            "Defense": "EPA/success allowed, run/pass funnel, explosive suppression, pressure/sacks and down-distance behavior.",
            "Coordinators": "OC/DC tenure, prior meetings, QB-vs-DC and offense-vs-DC samples with recency and continuity weighting.",
            "Players": "QB dropbacks/scrambles, RB opportunity, WR/TE targets/air yards/red-zone usage, defensive matchup context and injuries.",
            "Trenches": "Pressure created/allowed, sacks, rushing efficiency and line-level outcome proxies supported by free datasets.",
            "Environment": "Home/road, rest, travel, surface, weather and expected game script.",
        }
    for k, v in buckets.items():
        st.markdown(f"**{k}** — {v}")

elif page == "Demo Model Board":
    st.subheader(f"{sport} Demo Model Board")
    st.warning("Everything on this page is example/demo data. It is here to show how a finished ranked board will look.", icon="⚠️")
    for _, row in board.iterrows():
        render_pick(row)
        st.divider()

elif page == "Model History":
    st.subheader("Prediction Audit Trail")
    st.write("Every future live prediction is designed to be timestamped before the game with its projection, probability, market odds, evidence and eventual result.")
    try:
        con = sqlite3.connect(DB_PATH)
        hist = pd.read_sql_query(
            "SELECT created_at,sport,market,selection,model_probability,market_odds,edge,confidence,result FROM predictions ORDER BY id DESC LIMIT 250",
            con,
        )
        con.close()
    except Exception:
        hist = pd.DataFrame()
    if hist.empty:
        st.info("No live predictions logged yet. Demo cards are intentionally not written to the audit table.")
    else:
        st.dataframe(hist, use_container_width=True, hide_index=True)
    st.markdown("**Calibration goal:** when the model labels a large group of comparable events as 60%, roughly 60% should occur.")

elif page == "Data Health":
    st.subheader("Data Health")
    st.caption("Shows which free datasets have actually been cached. Missing inputs stay missing rather than being guessed.")
    st.dataframe(data_health(), use_container_width=True, hide_index=True)

else:
    st.subheader("$0 Data-Source Architecture")
    st.dataframe(source_table(), use_container_width=True, hide_index=True)
    st.markdown("**Rule:** if a metric cannot be obtained reliably and legitimately at $0, the engine derives a defensible proxy from free raw data or marks it unavailable.")
    st.markdown("**Sportsbook odds:** current DraftKings/Fliff lines are entered manually because the site does not scrape those services.")

st.divider()
st.caption("Sports Edge Lab is an analysis tool. Probabilities express uncertainty; they are not guarantees.")
