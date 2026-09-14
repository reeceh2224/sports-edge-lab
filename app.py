from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from config import DB_PATH
from database import init_db
from demo_data import mlb_board, nfl_board, source_table, mlb_bet_explorer, nfl_bet_explorer
from common import american_to_implied
from live_data import fetch_mlb_schedule, fetch_nfl_schedule, data_health
from research_cards import mlb_pitcher_research, nfl_team_research

st.set_page_config(page_title="Sports Edge Lab", page_icon="📊", layout="wide")
init_db()

st.markdown("""
<style>
.block-container {padding-top: 1.4rem; padding-bottom: 4rem;}
[data-testid="stMetric"] {border:1px solid rgba(128,128,128,.22); border-radius:12px; padding:10px 12px;}
.smallnote {opacity:.72; font-size:.88rem;}
.demo-pill {display:inline-block; padding:3px 8px; border-radius:999px; border:1px solid rgba(128,128,128,.35); font-size:.72rem; font-weight:700;}
</style>
""", unsafe_allow_html=True)

st.title("Sports Edge Lab")
st.caption("$0-data-cost MLB + NFL matchup intelligence • explainable signals • sample-size aware")
st.warning("Review build: example recommendations are DEMO data, not live betting picks. Live free-data adapters are included in the project and can populate the app when hosted with internet access.", icon="⚠️")

sport = st.sidebar.selectbox("Sport", ["MLB", "NFL"])
view = st.sidebar.radio("View", ["Today's board", "Live research", "Player & bet explorer", "Matchup lab", "Manual market test", "Model history", "Data health", "Data sources"])
board = mlb_board() if sport == "MLB" else nfl_board()


def fmt_pct(v):
    return "—" if pd.isna(v) else f"{v:.1%}"


def render_pick(row):
    st.markdown(f"### #{int(row['rank'])} · {row['selection']}  <span class='demo-pill'>{row['status']}</span>", unsafe_allow_html=True)
    odds = int(row['market_odds']) if float(row['market_odds']).is_integer() else row['market_odds']
    odds_text = f"+{odds}" if float(odds) > 0 else str(odds)
    line = row.get('bet_line', None)
    line_text = "—" if pd.isna(line) else f"{line:g}"
    book = row.get('sportsbook', 'Manual / unavailable')
    st.caption(f"{row['game']} · {row['market']} · Sample: {row['sample']} · {book}")
    c1,c2,c3,c4,c5,c6,c7 = st.columns(7)
    c1.metric("Bet line", line_text)
    c2.metric("Odds", odds_text)
    c3.metric("Projection", f"{row['projection']:.2f}")
    c4.metric("Model probability", fmt_pct(row['model_probability']))
    c5.metric("Market implied", fmt_pct(row['implied_probability']))
    c6.metric("Model edge", f"+{row['edge']:.1%}" if row['edge'] >= 0 else f"{row['edge']:.1%}")
    c7.metric("Confidence", f"{row['confidence']:.1f}/10")
    a,b = st.columns(2)
    with a:
        st.markdown("**Evidence for**")
        for x in row['evidence_for']:
            st.markdown(f"- {x}")
    with b:
        st.markdown("**Evidence against / uncertainty**")
        for x in row['evidence_against']:
            st.markdown(f"- {x}")
    with st.expander("Open detailed matchup lenses"):
        for k,v in row['details'].items():
            st.markdown(f"**{k}:** {v}")


if view == "Today's board":
    st.subheader(f"{sport} — ranked matchup board")
    st.caption("Designed to rank opportunities only after comparing a model probability with a market probability. No 'lock' language.")
    for _, row in board.iterrows():
        render_pick(row)
        st.divider()


elif view == "Live research":
    st.subheader(f"{sport} live research")
    st.caption("Pulls current free schedule data on demand. This section does not invent live sportsbook prices; use Manual market test for a line you see at your sportsbook.")
    refresh = st.button("Refresh free live data", type="primary")
    if refresh:
        try:
            if sport == "MLB":
                live = fetch_mlb_schedule()
                st.session_state["mlb_live"] = live
            else:
                live = fetch_nfl_schedule(datetime.now().year)
                st.session_state["nfl_live"] = live
            st.success(f"Loaded {len(live)} schedule rows.")
        except Exception as e:
            st.error(f"Live source could not be reached from this environment: {e}")

    if sport == "MLB":
        live = st.session_state.get("mlb_live", pd.DataFrame())
        if live.empty:
            st.info("Tap Refresh free live data after the app is hosted with internet access.")
        else:
            st.dataframe(live[[c for c in ["game_datetime","away_team","home_team","away_probable_pitcher","home_probable_pitcher","venue","status"] if c in live.columns]], use_container_width=True, hide_index=True)
            cards = mlb_pitcher_research(live)
            if not cards.empty:
                st.markdown("#### Probable-pitcher research cards")
                for _, r in cards.iterrows():
                    st.markdown(f"**{r['player']} — {r['team']} vs {r['opponent']}**")
                    st.write(r['summary'])
                    st.caption(r['data_state'])
    else:
        live = st.session_state.get("nfl_live", pd.DataFrame())
        if live.empty:
            st.info("Tap Refresh free live data after the app is hosted with internet access.")
        else:
            today = pd.Timestamp.now().date()
            date_col = next((c for c in ["gameday","game_date","date"] if c in live.columns), None)
            upcoming = live
            if date_col:
                parsed = pd.to_datetime(live[date_col], errors="coerce").dt.date
                upcoming = live[parsed >= today].sort_values(date_col).head(16)
            show_cols = [c for c in [date_col,"week","away_team","home_team","stadium","roof","surface","temp","wind"] if c and c in upcoming.columns]
            st.dataframe(upcoming[show_cols] if show_cols else upcoming.head(16), use_container_width=True, hide_index=True)
            tendency_path = Path("data/processed/nfl_team_tendencies.parquet")
            # config paths are relative to the project directory; use PROCESSED_DIR when available through project layout.
            from config import PROCESSED_DIR
            tp = PROCESSED_DIR / "nfl_team_tendencies.parquet"
            tendencies = pd.read_parquet(tp) if tp.exists() else pd.DataFrame()
            cards = nfl_team_research(upcoming, tendencies)
            if not cards.empty:
                st.markdown("#### Matchup tendency cards")
                for _, r in cards.head(24).iterrows():
                    st.markdown(f"**{r['team']} vs {r['opponent']}**")
                    st.write(r['summary'])
                    st.caption(r['data_state'])

elif view == "Data health":
    st.subheader("Data health")
    st.caption("Shows which free datasets have actually been cached locally. This helps distinguish live/current inputs from demo or unavailable inputs.")
    st.dataframe(data_health(), use_container_width=True, hide_index=True)
    st.markdown("**Green-light rule:** a live recommendation should only be generated when its required datasets are current enough for that market. Missing inputs are shown as missing rather than guessed.")

elif view == "Player & bet explorer":
    st.subheader(f"{sport} player & bet explorer")
    st.caption("Review every modeled market for a game or drill into one player. Demo markets show the intended experience; live values populate when the hosted data pipeline is connected.")
    explorer = mlb_bet_explorer() if sport == "MLB" else nfl_bet_explorer()
    mode = st.radio("Explore by", ["Game", "Player"], horizontal=True)
    if mode == "Game":
        chosen_game = st.selectbox("Game", explorer["game"].drop_duplicates().tolist())
        shown = explorer[explorer["game"] == chosen_game].copy()
    else:
        players = [x for x in explorer["player"].drop_duplicates().tolist() if x != "Game"]
        chosen_player = st.selectbox("Player", players)
        shown = explorer[explorer["player"] == chosen_player].copy()

    verdict_filter = st.multiselect("Verdict filter", shown["verdict"].drop_duplicates().tolist(), default=shown["verdict"].drop_duplicates().tolist())
    shown = shown[shown["verdict"].isin(verdict_filter)]

    for _, r in shown.iterrows():
        st.markdown(f"### {r['market']} · {r['selection']}")
        st.caption(f"{r['game']} · {r['category']} · Verdict: {r['verdict']} · Sample: {r['sample']}")
        c1,c2,c3,c4 = st.columns(4)
        projection = r['projection']
        if r['market'] in ['Moneyline']:
            c1.metric("Projection", fmt_pct(projection))
        else:
            c1.metric("Projection", f"{projection:.2f}")
        c2.metric("Model probability", fmt_pct(r['model_probability']))
        c3.metric("Confidence", f"{r['confidence']:.1f}/10")
        c4.metric("Model verdict", r['verdict'])
        a,b = st.columns(2)
        with a:
            st.markdown("**Why it could be good**")
            for x in r['why_good']:
                st.markdown(f"- {x}")
        with b:
            st.markdown("**Why it may be a bad bet / what could go wrong**")
            for x in r['why_bad']:
                st.markdown(f"- {x}")
        st.divider()

elif view == "Matchup lab":
    st.subheader(f"{sport} matchup lab")
    selected = st.selectbox("Example matchup", board["selection"].tolist())
    row = board.loc[board["selection"] == selected].iloc[0]
    render_pick(row)
    st.markdown("#### What the full engine is designed to inspect")
    if sport == "MLB":
        buckets = {
            "Starting pitcher": "Pitch mix, velocity/spin/movement trends, K/BB, whiff/CSW proxies, batted-ball quality, platoon splits, times through order, prior opponent/hitter history.",
            "Hitter": "Pitch-type results, handedness, rolling EV/barrels/contact, chase/whiff where available, lineup slot, park context, direct pitcher history with sample shrinkage.",
            "Bullpen": "Reliever quality, handedness mix, recent pitches/appearances and likely availability.",
            "Catcher & running game": "Catcher throwing/pop-time context when available, caught-stealing results, runner speed/attempt/success, pitcher handedness and runner-control context.",
            "Defense": "Statcast defensive value/range where available, arm strength and position context.",
            "Environment": "Park, home/road, day/night, weather hook, travel/rest and lineup confirmation."
        }
    else:
        buckets = {
            "Offense": "EPA/play, success, explosives, early-down tendencies, neutral pass rate, red zone, pace, personnel/usage proxies and game-state splits.",
            "Defense": "EPA/success allowed, run/pass funnel, explosive suppression, pressure/sacks, down-distance behavior and position/receiver target outcomes.",
            "Coordinators": "OC/DC tenure, prior meetings, QB-vs-DC and offense-vs-DC samples, with recency and scheme/personnel continuity weighting.",
            "Players": "QB dropbacks/scrambles, RB opportunity, WR/TE targets/air yards/red-zone usage, defensive matchup context and injuries.",
            "Trenches": "Pressure created/allowed, sacks, rushing efficiency and line-level outcome proxies supported by free datasets.",
            "Environment": "Home/road, rest, travel, surface, weather and expected game script."
        }
    for k,v in buckets.items():
        st.markdown(f"**{k}** — {v}")

elif view == "Manual market test":
    st.subheader("Manual odds + model probability check")
    st.caption("This keeps v1 at $0 because you can enter a sportsbook line manually while the statistical engine stays free.")
    odds = st.number_input("American odds", value=-110, step=5)
    model_pct = st.slider("Model probability", 1.0, 99.0, 56.0, 0.1) / 100
    implied = american_to_implied(odds)
    edge = model_pct - implied
    c1,c2,c3 = st.columns(3)
    c1.metric("Market implied", fmt_pct(implied))
    c2.metric("Model probability", fmt_pct(model_pct))
    c3.metric("Difference", f"{edge:+.1%}")
    st.info("A positive difference is not a guarantee of profit. The model still has to be calibrated on predictions saved before games begin.")

elif view == "Model history":
    st.subheader("Prediction audit trail")
    st.write("Every live prediction is designed to be timestamped before the game with its projection, probability, market odds, evidence and eventual result.")
    try:
        con = sqlite3.connect(DB_PATH)
        hist = pd.read_sql_query("SELECT created_at,sport,market,selection,model_probability,market_odds,edge,confidence,result FROM predictions ORDER BY id DESC LIMIT 250", con)
        con.close()
    except Exception:
        hist = pd.DataFrame()
    if hist.empty:
        st.info("No live predictions logged yet. Demo cards are intentionally not written to the audit table.")
    else:
        st.dataframe(hist, use_container_width=True, hide_index=True)
    st.markdown("**Calibration goal:** when the model labels a large group of comparable events as 60%, roughly 60% should occur. This is more important than a flashy short winning streak.")

else:
    st.subheader("$0 data-source architecture")
    st.dataframe(source_table(), use_container_width=True, hide_index=True)
    st.markdown("**Rule:** if a metric cannot be obtained reliably and legitimately at $0, the engine either derives a defensible proxy from free raw data or marks it unavailable. It does not silently invent the input.")
    st.markdown("**Odds in v1:** manual entry avoids dependence on a paid odds feed. Free sportsbook-web data can be explored later only where terms and reliability allow it.")

st.divider()
st.caption("Sports Edge Lab is an analysis tool. Probabilities express uncertainty; they are not guarantees.")
