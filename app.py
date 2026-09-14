from __future__ import annotations
from datetime import date,timedelta
import pandas as pd
import streamlit as st
from database import init_db
from live_data import fetch_mlb_schedule,fetch_nfl_schedule,data_health
from public_odds import fetch_team_moneylines,fetch_public_props
from trend_analysis import analyze_prop
from team_analysis import analyze_mlb_moneyline
from demo_data import source_table

st.set_page_config(page_title="Sports Edge Lab",page_icon="📊",layout="wide",initial_sidebar_state="collapsed")
init_db()
st.markdown("""<style>
.block-container{padding-top:.55rem;padding-bottom:5rem;max-width:1100px}.pill{display:inline-block;padding:4px 10px;border-radius:999px;border:1px solid rgba(74,222,128,.45);font-size:.72rem;font-weight:700}.rating{display:inline-block;padding:5px 11px;border-radius:999px;border:1px solid rgba(128,128,128,.35);font-weight:800;margin-bottom:8px}.small{opacity:.72;font-size:.88rem}.verdict{font-size:1.05rem;font-weight:800;margin:.2rem 0 .8rem 0}@media(max-width:700px){.block-container{padding-left:1rem;padding-right:1rem}h1{font-size:2rem!important}h2{font-size:1.5rem!important}}
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


def _team_verdict_text(a):
    if a["rating"]=="BEST":return "Worth serious consideration at this price."
    if a["rating"]=="GOOD":return "Playable value if the listed lineup and starter hold."
    if a["rating"]=="BAD":return "I would pass even if the plus-money price looks attractive."
    return "Price and matchup are too close to call — PASS."


def show_team_lines(sport,schedule):
    st.markdown("### Main team betting lines")
    st.caption("Moneyline + total + run line/spread from a clean public odds board. MLB moneylines are graded against starter, recent team form and run differential — not just whether the odds are positive.")
    try:lines,meta=team_markets(sport)
    except Exception as exc:st.warning(f"Team lines unavailable right now: {exc}");return
    st.markdown(f"<span class='pill'>PUBLIC ODDS SOURCE · {meta['source']}</span>",unsafe_allow_html=True)
    if lines.empty:st.info("No clean team markets were exposed on the public board right now. Nothing is being guessed.");return
    for matchup,g in lines.groupby("matchup",sort=False):
        with st.expander(matchup,expanded=False):
            for _,r in g.iterrows():
                st.markdown(f"**{r['team']}**"+(f" · {r.get('pitcher','')}" if r.get('pitcher') else ""))
                c1,c2,c3=st.columns(3)
                c1.metric("Moneyline",r.get("moneyline") or "—");c2.metric("Total",r.get("total") or "—");c3.metric("Run line" if sport=="MLB" else "Spread",r.get("side") or "—")
                if sport=="MLB" and r.get("moneyline"):
                    try:a=analyze_mlb_moneyline(r.to_dict(),schedule)
                    except Exception:a=None
                    if a:
                        st.markdown(f"<span class='rating'>{a['rating']}</span>",unsafe_allow_html=True)
                        st.markdown(f"<div class='verdict'>{_team_verdict_text(a)}</div>",unsafe_allow_html=True)
                        x1,x2,x3=st.columns(3)
                        x1.metric("Estimated win chance",f"{a['model_probability']:.0%}")
                        x2.metric("Price implies",f"{a['implied_probability']:.0%}")
                        x3.metric("Estimated edge",f"{a['edge']:+.1%}")
                        s=a.get("starter") or {};rec=a.get("recent") or {}
                        st.markdown("**What supports it**")
                        for x in a.get("reasons",[]):st.markdown(f"- {x}")
                        st.markdown("**Why I might still pass**")
                        for x in a.get("risks",[]):st.markdown(f"- {x}")
                        if s.get("team_name") or s.get("opp_name"):
                            st.markdown("**Starter comparison**")
                            left=f"{s.get('team_name') or 'TBD'}"+(f" — ERA {s['team_era']:.2f}" if s.get('team_era') is not None else "")+(f", WHIP {s['team_whip']:.2f}" if s.get('team_whip') is not None else "")
                            right=f"{s.get('opp_name') or 'TBD'}"+(f" — ERA {s['opp_era']:.2f}" if s.get('opp_era') is not None else "")+(f", WHIP {s['opp_whip']:.2f}" if s.get('opp_whip') is not None else "")
                            st.markdown(f"- **{r['team']}:** {left}\n- **{a['opponent']}:** {right}")
                        st.caption(f"Recent 10-game win rates: {r['team']} {rec.get('team_win_rate',0):.0%} · {a['opponent']} {rec.get('opp_win_rate',0):.0%}. This is a transparent matchup heuristic, not a guarantee.")
                    else:st.caption("Moneyline is live, but the matchup model is missing enough clean starter/recent-game data to grade it safely.")
                st.divider()


def analysis_box(sport,r,a=None):
    a=a or prop_analysis(sport,str(r.get("event","")),str(r.get("market","")),str(r.get("line","")),str(r.get("odds","")))
    if not a:st.info("This row was not graded because the player/team/market could not be validated cleanly.");return
    st.markdown(f"<span class='rating'>{a['rating']}</span>",unsafe_allow_html=True)
    verdict={"BEST":"Strongest model-supported look on the board.","GOOD":"Good statistical support at this price.","PASS":"Mixed evidence — I would pass unless the line improves.","BAD":"The data does not support paying this price.","UNRATED":"Not enough validated data."}.get(a['rating'],a['rating'])
    st.markdown(f"<div class='verdict'>{a.get('side','')} · {verdict}</div>",unsafe_allow_html=True)
    c1,c2,c3=st.columns(3)
    c1.metric("Model trend chance",f"{a['trend_probability']:.0%}");c2.metric("Odds imply",f"{a['implied_probability']:.0%}" if a.get('implied_probability') is not None else "—");c3.metric("Estimated edge",f"{a['edge']:+.1%}" if a.get('edge') is not None else "—")
    st.markdown("**Recent performance vs this exact line**")
    st.markdown(f"- Last 3: **{a['last3']['hit_rate']:.0%}** hit · average **{a['last3']['avg']:.2f}** · results {', '.join(str(round(v,1)) for v in a['last3']['values'])}\n- Last 5: **{a['last5']['hit_rate']:.0%}** hit · average **{a['last5']['avg']:.2f}**\n- Last 10: **{a['last10']['hit_rate']:.0%}** hit · average **{a['last10']['avg']:.2f}**\n- Full tracked sample: **{a['season']['hit_rate']:.0%}** across **{a['season']['n']}** games")
    if a.get("opponent"):
        st.markdown(f"**History vs {a['opponent']}**")
        vo=a.get("vs_opponent")
        if vo:st.markdown(f"- Hit this side in **{vo['season']['hit_rate']:.0%}** of **{vo['season']['n']}** tracked games · average **{vo['season']['avg']:.2f}**")
        else:st.markdown("- Not enough direct opponent games for a trustworthy split; it is not being invented.")
    if sport=="MLB" and a.get("matchup"):
        m=a['matchup'];st.markdown("**Direct batter vs probable pitcher**")
        st.markdown(f"- vs **{m.get('pitcher','TBD')}**: **{m.get('hits',0)} hits in {m.get('ab',0)} AB**"+(f" · {m.get('hr',0)} HR" if m.get('hr') else "")+". This is shown as context and down-weighted when the sample is small.")
    if sport=="NFL" and a.get("defense_context"):
        d=a['defense_context'];st.markdown("**Opponent-defense context**")
        st.markdown(f"- {a['opponent']} allowed about **{d.get('avg_allowed',0):.1f}** {a['prop'].lower()} units per game to the comparison group last season"+(f" ({d.get('position')})" if d.get('position') else "")+".")
    st.markdown("**Why I like / dislike this side**")
    for x in a.get("reasons",[]):st.markdown(f"- {x}")
    if a.get("risks"):
        st.markdown("**What could make it fail**")
        for x in a['risks']:st.markdown(f"- {x}")
    st.caption("The grade blends recent results, a larger historical sample, the posted price and opponent context. Direct opponent/pitcher samples are deliberately down-weighted when small.")


def show_props(sport,filter_mode="ALL"):
    st.markdown("### Player props")
    st.caption("Only rows that pass player-to-game validation are shown. BEST / GOOD / PASS / BAD are based on actual player results plus opponent context — not simply on whether a prop exists.")
    props,meta=public_props(sport)
    if props.empty:
        st.info("No clean public player-prop rows were exposed right now. The board will retry after cache refresh.");return
    analyses={}
    with st.spinner("Validating players and grading props…"):
        for idx,r in props.head(160).iterrows():
            a=prop_analysis(sport,str(r.get("event","")),str(r.get("market","")),str(r.get("line","")),str(r.get("odds","")))
            if a:analyses[idx]=a
    # Critical safety/quality rule: do not show a prop if we cannot verify that the player belongs in this game.
    valid_ids=list(analyses.keys())
    if filter_mode!="ALL":valid_ids=[i for i in valid_ids if analyses[i]['rating']==filter_mode]
    if not valid_ids:
        st.info(f"No validated props currently grade as {filter_mode}." if filter_mode!="ALL" else "No player props passed the player/team/market validation rules right now.")
        with st.expander("Source status"):st.dataframe(pd.DataFrame(meta),use_container_width=True,hide_index=True)
        return
    rank={"BEST":0,"GOOD":1,"PASS":2,"BAD":3,"UNRATED":4}
    valid_ids.sort(key=lambda i:(rank.get(analyses[i]['rating'],9),-((analyses[i].get('edge') if analyses[i].get('edge') is not None else -99))))
    for idx in valid_ids[:80]:
        r=props.loc[idx];a=analyses[idx]
        title=f"{a['rating']} · {r.get('event','')} · {a.get('player','')} {a.get('prop','')} · {r.get('line','')} ({r.get('odds','')})"
        with st.expander(title):
            c1,c2,c3=st.columns(3);c1.metric("Book",r.get("book","—"));c2.metric("Line",r.get("line","—"));c3.metric("Odds",r.get("odds","—"));analysis_box(sport,r,a)
    with st.expander("Source status"):st.dataframe(pd.DataFrame(meta),use_container_width=True,hide_index=True)


def daily_board(sport,days):
    st.subheader(f"{sport} Betting Board · Next {days} Days");st.caption("Past dates roll off automatically; new games roll in.")
    sched=schedule_window(sport,days);show_games(sched,sport);show_team_lines(sport,sched)
    st.markdown("#### Prop quality filter")
    filt=st.radio("Show",["ALL","BEST","GOOD","PASS","BAD"],horizontal=True,label_visibility="collapsed")
    show_props(sport,filt)

st.title("Sports Edge Lab")
st.caption("Automatic MLB + NFL board • main lines + validated props • matchup-aware grading • $0 data cost")
sport=st.radio("Sport",["MLB","NFL"],horizontal=True)
days=st.selectbox("Rolling window",[2,3,4],index=1,format_func=lambda x:f"Next {x} days")
page=st.selectbox("Section",["Daily Betting Board","Best Bets","Data Health","Data Sources"],index=0)
if st.button("Refresh board",use_container_width=True):st.cache_data.clear();st.rerun()
if page=="Daily Betting Board":daily_board(sport,days)
elif page=="Best Bets":
    st.subheader(f"{sport} Best Bets");st.caption("Only props that pass game validation and the strongest thresholds appear here. It is okay for this list to be empty.")
    show_props(sport,"BEST");st.markdown("### Good secondary looks");show_props(sport,"GOOD")
elif page=="Data Health":
    st.subheader("Data Health")
    try:st.dataframe(data_health(),use_container_width=True,hide_index=True)
    except Exception as exc:st.error(str(exc))
    try:_,meta=team_markets(sport);st.json(meta)
    except Exception as exc:st.write({"team_lines":str(exc)})
elif page=="Data Sources":
    st.subheader("Free Data Sources");st.dataframe(source_table(),use_container_width=True,hide_index=True)
    st.markdown("- Public team-odds board: current moneyline / total / run line or spread.\n- Public player-prop rows: current listed markets when exposed.\n- MLB Stats API: schedule, probable starters, player game logs and opponent history.\n- nflverse/nflreadpy: player weekly results, team membership and opponent splits.\n- Ratings are generated by this site and are not sportsbook guarantees.")
