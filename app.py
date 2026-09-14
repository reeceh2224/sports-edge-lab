from __future__ import annotations

from datetime import date, timedelta
import pandas as pd
import streamlit as st

from database import init_db
from live_data import fetch_mlb_schedule, fetch_nfl_schedule, data_health
from public_odds import fetch_team_market_tables, fetch_public_props, rank_public_props
from demo_data import source_table

st.set_page_config(page_title='Sports Edge Lab', page_icon='📊', layout='wide', initial_sidebar_state='collapsed')
init_db()

st.markdown('''
<style>
.block-container{padding-top:.65rem;padding-bottom:5rem;max-width:1200px}
.pill{display:inline-block;padding:3px 9px;border-radius:999px;border:1px solid rgba(74,222,128,.45);font-size:.72rem;font-weight:700}
.card{border:1px solid rgba(128,128,128,.22);border-radius:14px;padding:12px 14px;margin-bottom:10px}
.small{opacity:.72;font-size:.88rem}
@media(max-width:700px){.block-container{padding-left:1rem;padding-right:1rem}h1{font-size:2rem!important}h2{font-size:1.45rem!important}}
</style>
''', unsafe_allow_html=True)

@st.cache_data(ttl=300, show_spinner=False)
def mlb_day(d): return fetch_mlb_schedule(d)

@st.cache_data(ttl=900, show_spinner=False)
def nfl_season(y): return fetch_nfl_schedule(y)

@st.cache_data(ttl=600, show_spinner=False)
def team_market_tables(sport): return fetch_team_market_tables(sport)

@st.cache_data(ttl=600, show_spinner=False)
def public_props(sport): return fetch_public_props(sport)


def schedule_window(sport: str, days: int) -> pd.DataFrame:
    if sport == 'MLB':
        frames=[]
        for i in range(days):
            try:
                x=mlb_day((date.today()+timedelta(days=i)).isoformat())
                if x is not None and not x.empty:
                    x=x.copy(); x['board_date']=(date.today()+timedelta(days=i)).isoformat(); frames.append(x)
            except Exception: pass
        return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    try:
        x=nfl_season(date.today().year)
        if x is None or x.empty: return pd.DataFrame()
        dc=next((c for c in ['gameday','game_date','date'] if c in x.columns),None)
        if not dc: return x.head(60)
        dd=pd.to_datetime(x[dc],errors='coerce').dt.date
        return x[(dd>=date.today()) & (dd<=date.today()+timedelta(days=days-1))].copy()
    except Exception:
        return pd.DataFrame()


def show_games(df: pd.DataFrame, sport: str):
    if df.empty:
        st.warning('Upcoming schedule is temporarily unavailable.')
        return
    if sport=='MLB':
        cols=[c for c in ['game_datetime','away_team','home_team','away_probable_pitcher','home_probable_pitcher','venue','status'] if c in df.columns]
    else:
        cols=[c for c in ['gameday','gametime','away_team','home_team','game_type','stadium'] if c in df.columns]
    st.dataframe(df[cols] if cols else df, use_container_width=True, hide_index=True)


def show_team_lines(sport: str):
    st.markdown('### Team betting lines')
    st.caption('Free public consensus/opening lines. No paid API and no invented prices.')
    try:
        tables,meta=team_market_tables(sport)
        st.markdown(f"<span class='pill'>LIVE PUBLIC SOURCE · {meta['source']}</span>",unsafe_allow_html=True)
        if not tables:
            st.info('The public odds page did not expose a usable table right now.')
            return
        for i,t in enumerate(tables[:4]):
            with st.expander('Moneyline / spread / total board' if i==0 else f'Additional market table {i+1}', expanded=(i==0)):
                st.dataframe(t.head(80),use_container_width=True,hide_index=True)
    except Exception as exc:
        st.warning(f'Team lines unavailable from the free public source right now: {exc}')


def show_props(sport: str):
    st.markdown('### Player props')
    st.caption('Automatically collected from free public prop pages when they expose lines. Availability changes as books post markets.')
    try:
        props,meta=public_props(sport)
    except Exception as exc:
        st.warning(f'Player props unavailable right now: {exc}')
        return
    if props.empty:
        st.info('No usable public player-prop lines were exposed at this moment. The board will retry automatically after the cache refreshes.')
        return
    ranked=rank_public_props(props)
    st.markdown('#### Best prop candidates on the public board')
    st.caption('Sorted by a transparent price/market-quality heuristic. This is a shortlist for analysis, not a guaranteed-win probability.')
    for _,r in ranked.head(12).iterrows():
        with st.expander(f"{r.get('event','')} · {r.get('market','')} · {r.get('line','')} · {r.get('odds','')}"):
            c1,c2,c3=st.columns(3)
            c1.metric('Book',r.get('book','—'))
            c2.metric('Line',r.get('line','—'))
            c3.metric('Odds',r.get('odds','—'))
            st.markdown('**Why it is worth looking at**')
            st.markdown('- The line is currently visible on a free public odds/prop source.\n- Standard volume/stat markets are prioritized over extreme long-shot props.\n- It is surfaced automatically so you do not have to search player-by-player.')
            st.markdown('**Why you might pass**')
            st.markdown('- Public-page availability can lag a sportsbook.\n- A posted price alone is not enough to prove positive expected value.\n- Injury, lineup, weather and role changes can move a prop quickly.')
    with st.expander('See all public props'):
        st.dataframe(ranked.head(300),use_container_width=True,hide_index=True)
    with st.expander('Prop source status'):
        st.dataframe(pd.DataFrame(meta),use_container_width=True,hide_index=True)


def daily_board(sport: str, days: int):
    st.subheader(f'{sport} Betting Board · Next {days} Days')
    st.caption('This rolls forward automatically each day. Finished dates fall off and new upcoming games appear.')
    games=schedule_window(sport,days)
    show_games(games,sport)
    show_team_lines(sport)
    show_props(sport)

st.title('Sports Edge Lab')
st.caption('Automatic MLB + NFL betting board • team lines + player props • free public data only')

sport=st.radio('Sport',['MLB','NFL'],horizontal=True)
days=st.selectbox('Rolling window',[2,3,4],index=1,format_func=lambda x:f'Next {x} days')
page=st.selectbox('Section',['Daily Betting Board','Top Prop Candidates','Data Health','Data Sources'],index=0)

if st.button('Refresh board',use_container_width=True):
    st.cache_data.clear(); st.rerun()

if page=='Daily Betting Board':
    daily_board(sport,days)
elif page=='Top Prop Candidates':
    show_props(sport)
elif page=='Data Health':
    st.subheader('Data Health')
    try: st.dataframe(data_health(),use_container_width=True,hide_index=True)
    except Exception as exc: st.error(str(exc))
    try:
        _,meta=team_market_tables(sport); st.json(meta)
    except Exception as exc: st.write({'team_lines':str(exc)})
elif page=='Data Sources':
    st.subheader('Free Data Sources')
    st.dataframe(source_table(),use_container_width=True,hide_index=True)
    st.markdown('**Additional live line sources in this build**')
    st.markdown('- VegasInsider public matchup/consensus pages: team moneyline, spread/run line, totals when exposed.\n- DraftKings Network public player-props page: publicly displayed popular prop lines.\n- RotoWire public player-prop pages: additional public prop tables when exposed to non-subscribers.\n\nNo paid odds API key is required. If a page blocks automated access or does not expose a market, the website says unavailable instead of fabricating a number.')
