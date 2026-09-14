from __future__ import annotations

from datetime import date, timedelta
import pandas as pd
import streamlit as st

from database import init_db
from live_data import fetch_mlb_schedule, fetch_nfl_schedule, data_health
from public_odds import fetch_team_moneylines, fetch_public_props
from trend_analysis import analyze_prop
from demo_data import source_table

st.set_page_config(page_title="Sports Edge Lab", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")
init_db()

st.markdown("""
<style>
.block-container{padding-top:.55rem;padding-bottom:5rem;max-width:1100px}
.pill{display:inline-block;padding:4px 10px;border-radius:999px;border:1px solid rgba(74,222,128,.45);font-size:.72rem;font-weight:700}
.card{border:1px solid rgba(128,128,128,.25);border-radius:14px;padding:14px 15px;margin-bottom:12px}
.good{font-weight:800}.small{opacity:.72;font-size:.88rem}
@media(max-width:700px){.block-container{padding-left:1rem;padding-right:1rem}h1{font-size:2rem!important}h2{font-size:1.5rem!important}}
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=300, show_spinner=False)
def mlb_day(d): return fetch_mlb_schedule(d)

@st.cache_data(ttl=900, show_spinner=False)
def nfl_season(y): return fetch_nfl_schedule(y)

@st.cache_data(ttl=600, show_spinner=False)
def team_moneylines(sport): return fetch_team_moneylines(sport)

@st.cache_data(ttl=600, show_spinner=False)
def public_props(sport): return fetch_public_props(sport)

@st.cache_data(ttl=1800, show_spinner=False)
def prop_analysis(sport, market, line, odds): return analyze_prop(sport, market, line, odds)


def schedule_window(sport: str, days: int) -> pd.DataFrame:
    if sport == "MLB":
        frames=[]
        for i in range(days):
            d=(date.today()+timedelta(days=i)).isoformat()
            try:
                x=mlb_day(d)
                if x is not None and not x.empty:
                    x=x.copy(); x["board_date"]=d; frames.append(x)
            except Exception: pass
        return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    try:
        x=nfl_season(date.today().year)
        if x is None or x.empty: return pd.DataFrame()
        dc=next((c for c in ["gameday","game_date","date"] if c in x.columns),None)
        if not dc: return x.head(60)
        dd=pd.to_datetime(x[dc],errors="coerce").dt.date
        return x[(dd>=date.today()) & (dd<=date.today()+timedelta(days=days-1))].copy()
    except Exception:
        return pd.DataFrame()


def show_games(df: pd.DataFrame, sport: str):
    st.markdown("### Upcoming games")
    if df.empty:
        st.warning("Upcoming schedule is temporarily unavailable.")
        return
    if sport=="MLB":
        cols=[c for c in ["board_date","game_datetime","away_team","home_team","away_probable_pitcher","home_probable_pitcher"] if c in df.columns]
    else:
        cols=[c for c in ["gameday","gametime","away_team","home_team","game_type"] if c in df.columns]
    st.dataframe(df[cols] if cols else df, use_container_width=True, hide_index=True)


def show_team_lines(sport: str):
    st.markdown("### Team moneylines")
    st.caption("Clean prices only. Season records, ATS records, O/U records, ads and page headings are discarded.")
    try:
        lines,meta=team_moneylines(sport)
    except Exception as exc:
        st.warning(f"Team lines unavailable right now: {exc}")
        return
    st.markdown(f"<span class='pill'>PUBLIC ODDS SOURCE · {meta['source']}</span>", unsafe_allow_html=True)
    if lines.empty:
        st.info("The public odds page did not expose a clean moneyline table at this moment. No values are being guessed.")
        return
    for matchup, grp in lines.groupby("matchup", sort=False):
        with st.expander(matchup, expanded=False):
            for _,r in grp.iterrows():
                c1,c2,c3,c4=st.columns([2,1,1,1])
                c1.markdown(f"**{r['team']}**")
                c2.metric("DraftKings", r.get("draftkings") or "—")
                c3.metric("Consensus", r.get("consensus") or "—")
                c4.metric("Open", r.get("open") or "—")
    st.caption("Spread/run-line and total markets are hidden unless a source can be parsed cleanly. The site will not show standings records as betting lines again.")


def analysis_box(sport: str, r: pd.Series):
    a=prop_analysis(sport, str(r.get("market","")), str(r.get("line","")), str(r.get("odds","")))
    if not a:
        st.info("Line found, but there is not enough clean statistical data for this market yet. It is shown as an available prop — not a recommendation.")
        return
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Trend probability", f"{a['trend_probability']:.0%}")
    c2.metric("Odds imply", f"{a['implied_probability']:.0%}" if a.get("implied_probability") is not None else "—")
    c3.metric("Trend edge", f"{a['edge']:+.1%}" if a.get("edge") is not None else "—")
    c4.metric("Grade", a["grade"])
    st.markdown("**What the player has actually done**")
    st.markdown(
        f"- Last 5: **{a['last5']['hit_rate']:.0%}** hit rate, average **{a['last5']['avg']:.2f}**\n"
        f"- Last 10: **{a['last10']['hit_rate']:.0%}** hit rate, average **{a['last10']['avg']:.2f}**\n"
        f"- Season: **{a['season']['hit_rate']:.0%}** hit rate across **{a['season']['n']}** games"
    )
    if a["grade"] in {"STRONG LOOK","LEAN"}:
        st.markdown("**Why it is worth considering**")
        st.markdown("- Recent and season hit rates are being compared directly with the probability implied by the posted price.\n- The grade requires both a positive gap and a minimum sample; a line is not promoted just because it exists.")
    elif a["grade"] == "AVOID":
        st.markdown("**Why the model does not like it**")
        st.markdown("- The player's observed hit rate is below what the sportsbook price asks you to pay for.")
    else:
        st.markdown("**Why this is a pass**")
        st.markdown("- The observed advantage is too small or the sample is too thin to call it a worthwhile play.")
    st.caption("Trend probability is a recency-weighted statistical baseline, not yet the final opponent-adjusted model. Matchup, lineup, weather, pitch/coverage and injury adjustments are being kept separate so the site does not pretend they were analyzed when they were not.")


def show_props(sport: str, only_best: bool=False):
    st.markdown("### Player props")
    st.caption("DraftKings lines that are cleanly visible on the public DraftKings Network table. No malformed fallback tables.")
    props,meta=public_props(sport)
    if props.empty:
        st.info("No clean public player-prop rows were exposed right now. The board will retry after the cache refreshes.")
        return

    analyzed=[]
    with st.spinner("Checking recent player results against posted prices…"):
        for idx,r in props.head(80).iterrows():
            a=prop_analysis(sport, str(r.get("market","")), str(r.get("line","")), str(r.get("odds","")))
            if a:
                analyzed.append((idx,a))
    grades={idx:a for idx,a in analyzed}

    if only_best:
        picks=[]
        for idx,a in analyzed:
            if a["grade"] in {"STRONG LOOK","LEAN"}:
                picks.append((idx,a))
        picks=sorted(picks,key=lambda z:(z[1].get("edge") if z[1].get("edge") is not None else -99),reverse=True)
        if not picks:
            st.info("No props currently clear the minimum data + edge rules. That is a valid result — the site will not force a pick.")
            return
        st.markdown("#### Best data-backed looks right now")
        use_idx=[i for i,_ in picks[:12]]
        display=props.loc[use_idx]
    else:
        display=props.head(40)

    for idx,r in display.iterrows():
        a=grades.get(idx)
        grade=f" · {a['grade']}" if a else " · UNRATED"
        with st.expander(f"{r.get('event','')} · {r.get('market','')} · {r.get('line','')} ({r.get('odds','')}){grade}"):
            c1,c2,c3=st.columns(3)
            c1.metric("Book",r.get("book","—")); c2.metric("Line",r.get("line","—")); c3.metric("Odds",r.get("odds","—"))
            analysis_box(sport,r)

    with st.expander("See clean prop table"):
        st.dataframe(props.head(200), use_container_width=True, hide_index=True)
    with st.expander("Source status"):
        st.dataframe(pd.DataFrame(meta), use_container_width=True, hide_index=True)


def daily_board(sport: str, days: int):
    st.subheader(f"{sport} Betting Board · Next {days} Days")
    st.caption("The board rolls forward automatically. Past dates fall off; upcoming games are added.")
    show_games(schedule_window(sport,days),sport)
    show_team_lines(sport)
    show_props(sport,only_best=False)

st.title("Sports Edge Lab")
st.caption("Automatic MLB + NFL board • clean public lines • data-backed grading • $0 data cost")

sport=st.radio("Sport",["MLB","NFL"],horizontal=True)
days=st.selectbox("Rolling window",[2,3,4],index=1,format_func=lambda x:f"Next {x} days")
page=st.selectbox("Section",["Daily Betting Board","Best Bets","Data Health","Data Sources"],index=0)

if st.button("Refresh board",use_container_width=True):
    st.cache_data.clear(); st.rerun()

if page=="Daily Betting Board":
    daily_board(sport,days)
elif page=="Best Bets":
    st.subheader(f"{sport} Best Bets")
    st.caption("Only markets that clear the minimum statistical sample and edge rules appear here. No pick is better than a fake pick.")
    show_props(sport,only_best=True)
elif page=="Data Health":
    st.subheader("Data Health")
    try: st.dataframe(data_health(),use_container_width=True,hide_index=True)
    except Exception as exc: st.error(str(exc))
    try:
        _,meta=team_moneylines(sport); st.json(meta)
    except Exception as exc: st.write({"team_lines":str(exc)})
elif page=="Data Sources":
    st.subheader("Free Data Sources")
    st.dataframe(source_table(),use_container_width=True,hide_index=True)
    st.markdown("**Live line/stat sources used by this build**")
    st.markdown("- VegasInsider **odds** board: clean team moneyline prices when exposed, including DraftKings when the table identifies that column.\n- DraftKings Network player-props table: structured Event / Market / Betslip Line / Odds rows.\n- MLB Stats API: player game logs used for MLB trend hit rates.\n- nflverse via nflreadpy: weekly player stats used for NFL trend hit rates.\n\nThe app rejects rows that look like standings, ATS/O-U records, ads, headings or malformed page content. An available line is never automatically called a good bet.")
