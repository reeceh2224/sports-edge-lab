from __future__ import annotations
from datetime import date,timedelta
import pandas as pd
import streamlit as st
from database import init_db
from live_data import fetch_mlb_schedule,fetch_nfl_schedule,data_health
from public_odds import fetch_team_moneylines,fetch_public_props
from trend_analysis import analyze_prop
from demo_data import source_table

st.set_page_config(page_title="Sports Edge Lab",page_icon="📊",layout="wide",initial_sidebar_state="collapsed")
init_db()
st.markdown("""<style>
.block-container{padding-top:.55rem;padding-bottom:5rem;max-width:1100px}.pill{display:inline-block;padding:4px 10px;border-radius:999px;border:1px solid rgba(74,222,128,.45);font-size:.72rem;font-weight:700}.rating{display:inline-block;padding:5px 11px;border-radius:999px;border:1px solid rgba(128,128,128,.35);font-weight:800;margin-bottom:8px}.small{opacity:.72;font-size:.88rem}@media(max-width:700px){.block-container{padding-left:1rem;padding-right:1rem}h1{font-size:2rem!important}h2{font-size:1.5rem!important}}
</style>""",unsafe_allow_html=True)

@st.cache_data(ttl=300,show_spinner=False)
def mlb_day(d):return fetch_mlb_schedule(d)
@st.cache_data(ttl=900,show_spinner=False)
def nfl_season(y):return fetch_nfl_schedule(y)
@st.cache_data(ttl=300,show_spinner=False)
def team_markets(sport):return fetch_team_moneylines(sport)
@st.cache_data(ttl=300,show_spinner=False)
def public_props(sport):return fetch_public_props(sport)
@st.cache_data(ttl=1800,show_spinner=False)
def prop_analysis(sport,event,market,line,odds):return analyze_prop(sport,event,market,line,odds)

def schedule_window(sport,days):
    if sport=="MLB":
        fs=[]
        for i in range(days):
            d=(date.today()+timedelta(days=i)).isoformat()
            try:
                x=mlb_day(d)
                if x is not None and not x.empty:x=x.copy();x["board_date"]=d;fs.append(x)
            except Exception:pass
        return pd.concat(fs,ignore_index=True) if fs else pd.DataFrame()
    try:
        x=nfl_season(date.today().year)
        if x is None or x.empty:return pd.DataFrame()
        dc=next((c for c in ["gameday","game_date","date"] if c in x.columns),None)
        if not dc:return x.head(60)
        dd=pd.to_datetime(x[dc],errors="coerce").dt.date
        return x[(dd>=date.today())&(dd<=date.today()+timedelta(days=days-1))].copy()
    except Exception:return pd.DataFrame()

def show_games(df,sport):
    st.markdown("### Upcoming games")
    if df.empty:st.warning("Upcoming schedule is temporarily unavailable.");return
    cols=[c for c in (["board_date","game_datetime","away_team","home_team","away_probable_pitcher","home_probable_pitcher"] if sport=="MLB" else ["gameday","gametime","away_team","home_team","game_type"]) if c in df.columns]
    st.dataframe(df[cols] if cols else df,use_container_width=True,hide_index=True)

def show_team_lines(sport):
    st.markdown("### Main team betting lines")
    st.caption("Moneyline + total + run line/spread from a clean public odds board. No standings or ATS records are treated as prices.")
    try:lines,meta=team_markets(sport)
    except Exception as exc:st.warning(f"Team lines unavailable right now: {exc}");return
    st.markdown(f"<span class='pill'>PUBLIC ODDS SOURCE · {meta['source']}</span>",unsafe_allow_html=True)
    if lines.empty:st.info("No clean team markets were exposed on the public board right now. Nothing is being guessed.");return
    for matchup,g in lines.groupby("matchup",sort=False):
        with st.expander(matchup,expanded=False):
            for _,r in g.iterrows():
                st.markdown(f"**{r['team']}**"+(f" · {r.get('pitcher','')}" if r.get('pitcher') else ""))
                c1,c2,c3=st.columns(3)
                c1.metric("Moneyline",r.get("moneyline") or "—")
                c2.metric("Total",r.get("total") or "—")
                c3.metric("Run line" if sport=="MLB" else "Spread",r.get("side") or "—")
    st.caption("These are market prices only. Team bets are not promoted as picks until the model has enough team-level matchup data to grade them.")

def analysis_box(sport,r,a=None):
    a=a or prop_analysis(sport,str(r.get("event","")),str(r.get("market","")),str(r.get("line","")),str(r.get("odds","")))
    if not a:st.info("Line found, but there is not enough clean statistical data to grade this prop yet.");return
    st.markdown(f"<span class='rating'>{a['rating']}</span>",unsafe_allow_html=True)
    c1,c2,c3=st.columns(3)
    c1.metric("Trend probability",f"{a['trend_probability']:.0%}")
    c2.metric("Odds imply",f"{a['implied_probability']:.0%}" if a.get('implied_probability') is not None else "—")
    c3.metric("Trend edge",f"{a['edge']:+.1%}" if a.get('edge') is not None else "—")
    st.markdown("**Recent form**")
    st.markdown(f"- Last 5: **{a['last5']['hit_rate']:.0%}** hit rate · **{a['last5']['avg']:.2f}** average\n- Last 10: **{a['last10']['hit_rate']:.0%}** hit rate · **{a['last10']['avg']:.2f}** average\n- Season: **{a['season']['hit_rate']:.0%}** hit rate across **{a['season']['n']}** games")
    if a.get("opponent"):
        st.markdown(f"**Matchup vs {a['opponent']}**")
        vo=a.get("vs_opponent")
        if vo:st.markdown(f"- This season vs this opponent: **{vo['season']['hit_rate']:.0%}** hit rate in **{vo['season']['n']}** games · average **{vo['season']['avg']:.2f}**")
        else:st.markdown("- Not enough same-opponent games this season for a trustworthy opponent-specific rate.")
    st.markdown("**Why the grade looks this way**")
    if a['rating']=="BEST":st.markdown("- The posted price is meaningfully below the player's recency-weighted hit rate.\n- The trend is supported by both recent games and a usable season sample.\n- This clears the site's strictest value + consistency threshold.")
    elif a['rating']=="GOOD":st.markdown("- There is a positive gap versus the sportsbook's implied probability.\n- Recent performance supports the side, but it is not strong enough for the BEST tier.")
    elif a['rating']=="BAD":st.markdown("- The recent/season results do not justify the probability you are paying for at this price.\n- The site would rather fade or avoid this prop than force a recommendation.")
    else:st.markdown("- The numbers are mixed or the estimated edge is too small. This is a PASS, not a recommendation.")
    st.caption("Grades weight recent form, season form, price and sample size. Opponent history is shown separately so a tiny head-to-head sample cannot overpower the larger data set.")

def show_props(sport,filter_mode="ALL"):
    st.markdown("### Player props")
    st.caption("DraftKings Network public prop rows, then graded with player results. Use the filter to jump straight to BEST / GOOD / BAD.")
    props,meta=public_props(sport)
    if props.empty:
        st.info("No clean public player-prop rows were exposed right now. For NFL, the site now uses the NFL-specific DraftKings Network feed and will retry after cache refresh.");return
    analyses={}
    with st.spinner("Grading props and checking matchup history…"):
        for idx,r in props.head(100).iterrows():
            a=prop_analysis(sport,str(r.get("event","")),str(r.get("market","")),str(r.get("line","")),str(r.get("odds","")))
            if a:analyses[idx]=a
    if filter_mode!="ALL":
        ids=[i for i,a in analyses.items() if a['rating']==filter_mode]
        display=props.loc[ids] if ids else props.iloc[0:0]
    else:display=props.head(60)
    if display.empty:st.info(f"No props currently grade as {filter_mode}.");return
    rank={"BEST":0,"GOOD":1,"PASS":2,"BAD":3,"UNRATED":4}
    ids=list(display.index);ids.sort(key=lambda i:(rank.get((analyses.get(i) or {}).get('rating','UNRATED'),9),-((analyses.get(i) or {}).get('edge') or -99)))
    for idx in ids:
        r=props.loc[idx];a=analyses.get(idx);rating=a['rating'] if a else "UNRATED"
        with st.expander(f"{rating} · {r.get('event','')} · {r.get('market','')} · {r.get('line','')} ({r.get('odds','')})"):
            c1,c2,c3=st.columns(3);c1.metric("Book",r.get("book","—"));c2.metric("Line",r.get("line","—"));c3.metric("Odds",r.get("odds","—"));analysis_box(sport,r,a)
    with st.expander("Source status"):st.dataframe(pd.DataFrame(meta),use_container_width=True,hide_index=True)

def daily_board(sport,days):
    st.subheader(f"{sport} Betting Board · Next {days} Days");st.caption("Past dates roll off automatically; new games roll in.")
    show_games(schedule_window(sport,days),sport);show_team_lines(sport)
    st.markdown("#### Prop quality filter")
    filt=st.radio("Show",["ALL","BEST","GOOD","BAD"],horizontal=True,label_visibility="collapsed")
    show_props(sport,filt)

st.title("Sports Edge Lab")
st.caption("Automatic MLB + NFL board • main lines + props • matchup-aware grading • $0 data cost")
sport=st.radio("Sport",["MLB","NFL"],horizontal=True)
days=st.selectbox("Rolling window",[2,3,4],index=1,format_func=lambda x:f"Next {x} days")
page=st.selectbox("Section",["Daily Betting Board","Best Bets","Data Health","Data Sources"],index=0)
if st.button("Refresh board",use_container_width=True):st.cache_data.clear();st.rerun()
if page=="Daily Betting Board":daily_board(sport,days)
elif page=="Best Bets":
    st.subheader(f"{sport} Best Bets");st.caption("Only the strongest graded player props appear here. A blank list is allowed if nothing clears the rules.")
    show_props(sport,"BEST");st.markdown("### Good secondary looks");show_props(sport,"GOOD")
elif page=="Data Health":
    st.subheader("Data Health")
    try:st.dataframe(data_health(),use_container_width=True,hide_index=True)
    except Exception as exc:st.error(str(exc))
    try:_,meta=team_markets(sport);st.json(meta)
    except Exception as exc:st.write({"team_lines":str(exc)})
elif page=="Data Sources":
    st.subheader("Free Data Sources");st.dataframe(source_table(),use_container_width=True,hide_index=True)
    st.markdown("- ScoresAndOdds public board: main team moneyline / total / run line or spread.\n- DraftKings Network: sport-specific MLB/NFL public player-prop rows.\n- MLB Stats API: player game logs and opponent splits.\n- nflverse: NFL weekly player results and opponent fields when available.\n\nNo paid API key is required.")
