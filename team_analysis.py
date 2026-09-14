from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
import math
import re
import pandas as pd
import requests

from public_odds import american_to_prob

HEADERS={"User-Agent":"SportsEdgeLab/1.0"}
MLB_BASE="https://statsapi.mlb.com/api/v1"


def _clip(x, lo, hi): return max(lo,min(hi,x))
def _f(v, default=None):
    try:return float(v)
    except Exception:return default

@lru_cache(maxsize=2)
def _mlb_teams():
    r=requests.get(f"{MLB_BASE}/teams",params={"sportId":1},headers=HEADERS,timeout=15);r.raise_for_status()
    return {x.get("name"):int(x.get("id")) for x in r.json().get("teams",[]) if x.get("name") and x.get("id")}

@lru_cache(maxsize=128)
def _recent_team_games(team_id:int, end_day:str, days:int=32):
    end=pd.to_datetime(end_day).date(); start=end-timedelta(days=days)
    r=requests.get(f"{MLB_BASE}/schedule",params={"sportId":1,"teamId":team_id,"startDate":start.isoformat(),"endDate":end.isoformat()},headers=HEADERS,timeout=20);r.raise_for_status()
    rows=[]
    for d in r.json().get("dates",[]):
        for g in d.get("games",[]):
            if g.get("status",{}).get("abstractGameState")!="Final":continue
            a=g.get("teams",{}).get("away",{});h=g.get("teams",{}).get("home",{})
            away_id=(a.get("team") or {}).get("id");home_id=(h.get("team") or {}).get("id")
            if team_id not in (away_id,home_id):continue
            is_home=home_id==team_id; rf=(h if is_home else a).get("score");ra=(a if is_home else h).get("score")
            if rf is None or ra is None:continue
            rows.append({"date":d.get("date"),"rf":float(rf),"ra":float(ra),"win":float(rf)>float(ra)})
    return sorted(rows,key=lambda x:x["date"])

@lru_cache(maxsize=256)
def _pitcher_season(pid:int, season:int):
    if not pid:return None
    r=requests.get(f"{MLB_BASE}/people/{pid}/stats",params={"stats":"season","group":"pitching","season":season},headers=HEADERS,timeout=15);r.raise_for_status()
    for b in r.json().get("stats",[]):
        s=b.get("splits",[])
        if s:return s[0].get("stat",{})
    return None

def _starter_score(stat):
    if not stat:return 0.0
    era=_f(stat.get("era"));whip=_f(stat.get("whip"));ip=_f(stat.get("inningsPitched"),0)
    score=0.0
    if era is not None:score+=_clip((4.25-era)/1.5,-1.25,1.25)
    if whip is not None:score+=_clip((1.30-whip)/0.35,-1,1)
    if ip and ip<20:score*=.55
    return score

def _find_game(schedule,team):
    if schedule is None or schedule.empty:return None
    if "away_team" not in schedule.columns or "home_team" not in schedule.columns:return None
    candidates={str(team).lower()}
    code=NFL_FULL_TO_CODE.get(str(team)) if "NFL_FULL_TO_CODE" in globals() else None
    if code:candidates.add(str(code).lower())
    away=schedule["away_team"].astype(str).str.lower();home=schedule["home_team"].astype(str).str.lower()
    mask=away.isin(candidates)|home.isin(candidates)
    x=schedule[mask];return x.iloc[0].to_dict() if not x.empty else None

def analyze_mlb_moneyline(row:dict,schedule:pd.DataFrame)->dict|None:
    team=str(row.get("team") or "");price=row.get("moneyline");implied=american_to_prob(price)
    if not team or implied is None:return None
    game=_find_game(schedule,team)
    if not game:return None
    away=str(game.get("away_team") or "");home=str(game.get("home_team") or "");opponent=home if team==away else away;team_home=team==home
    teams=_mlb_teams();tid=teams.get(team);oid=teams.get(opponent)
    if not tid or not oid:return None
    today=str(game.get("game_date") or game.get("board_date") or date.today().isoformat())[:10]
    tg=_recent_team_games(tid,today);og=_recent_team_games(oid,today);t10=tg[-10:];o10=og[-10:]
    if len(t10)<4 or len(o10)<4:return None
    tw=sum(x["win"] for x in t10)/len(t10);ow=sum(x["win"] for x in o10)/len(o10);trd=sum(x["rf"]-x["ra"] for x in t10)/len(t10);ord_=sum(x["rf"]-x["ra"] for x in o10)/len(o10)
    season=date.today().year;tpid=game.get("away_probable_pitcher_id") if team==away else game.get("home_probable_pitcher_id");opid=game.get("home_probable_pitcher_id") if team==away else game.get("away_probable_pitcher_id")
    ts=_pitcher_season(int(tpid),season) if pd.notna(tpid) and tpid else None;os=_pitcher_season(int(opid),season) if pd.notna(opid) and opid else None
    starter_adv=_starter_score(ts)-_starter_score(os);recent_adv=(tw-ow)*1.6+_clip((trd-ord_)/3,-.9,.9);home_adv=.18 if team_home else -.02
    z=starter_adv*.55+recent_adv*.50+home_adv;p=_clip(1/(1+math.exp(-z)),.18,.82);edge=p-implied
    rating="BEST" if edge>=.08 else "GOOD" if edge>=.035 else "BAD" if edge<=-.05 else "PASS"
    reasons=[];risks=[]
    if starter_adv>.35:reasons.append("Probable-starter matchup favors this side based on season ERA/WHIP.")
    elif starter_adv<-.35:risks.append("Probable-starter matchup favors the opponent based on season ERA/WHIP.")
    if tw-ow>.15:reasons.append(f"Recent form is stronger: {tw:.0%} win rate over the last {len(t10)} versus {ow:.0%} for the opponent.")
    elif ow-tw>.15:risks.append(f"Opponent owns the stronger recent form: {ow:.0%} win rate over the last {len(o10)} versus {tw:.0%}.")
    if trd-ord_>1:reasons.append(f"Recent run differential is better by about {trd-ord_:.1f} runs per game.")
    elif ord_-trd>1:risks.append(f"Recent run differential favors the opponent by about {ord_-trd:.1f} runs per game.")
    if team_home:reasons.append("Home field adds a small positive to the matchup model.")
    if price and str(price).startswith("+") and edge<=0:risks.insert(0,f"The +{str(price).lstrip('+')} payout looks attractive, but plus money is not value by itself; the matchup model does not clear the price.")
    if not reasons:reasons.append("No major matchup advantage was found beyond the listed price.")
    if not risks:risks.append("Baseball moneylines are high-variance and lineup/bullpen changes can erase a small edge.")
    tname=game.get("away_probable_pitcher") if team==away else game.get("home_probable_pitcher");oname=game.get("home_probable_pitcher") if team==away else game.get("away_probable_pitcher")
    return {"team":team,"opponent":opponent,"price":price,"implied_probability":implied,"model_probability":p,"edge":edge,"rating":rating,"recent":{"team_win_rate":tw,"opp_win_rate":ow,"team_run_diff":trd,"opp_run_diff":ord_},"starter":{"team_name":tname,"opp_name":oname,"team_era":_f((ts or {}).get("era")),"opp_era":_f((os or {}).get("era")),"team_whip":_f((ts or {}).get("whip")),"opp_whip":_f((os or {}).get("whip"))},"reasons":reasons,"risks":risks}

# NFL analysis uses free nflverse schedules. It intentionally blends prior-season form
# with current-season results so Week 1/2 does not have an empty model.
@lru_cache(maxsize=3)
def _nfl_games():
    frames=[]
    for yr in [date.today().year-1,date.today().year]:
        try:
            u=f"https://github.com/nflverse/nfldata/raw/master/data/games.csv"
            x=pd.read_csv(u);x=x[pd.to_numeric(x.get("season"),errors="coerce").eq(yr)].copy();frames.append(x)
        except Exception:pass
    return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()

NFL_FULL_TO_CODE={"Arizona Cardinals":"ARI","Atlanta Falcons":"ATL","Baltimore Ravens":"BAL","Buffalo Bills":"BUF","Carolina Panthers":"CAR","Chicago Bears":"CHI","Cincinnati Bengals":"CIN","Cleveland Browns":"CLE","Dallas Cowboys":"DAL","Denver Broncos":"DEN","Detroit Lions":"DET","Green Bay Packers":"GB","Houston Texans":"HOU","Indianapolis Colts":"IND","Jacksonville Jaguars":"JAX","Kansas City Chiefs":"KC","Las Vegas Raiders":"LV","Los Angeles Chargers":"LAC","Los Angeles Rams":"LA","Miami Dolphins":"MIA","Minnesota Vikings":"MIN","New England Patriots":"NE","New Orleans Saints":"NO","New York Giants":"NYG","New York Jets":"NYJ","Philadelphia Eagles":"PHI","Pittsburgh Steelers":"PIT","San Francisco 49ers":"SF","Seattle Seahawks":"SEA","Tampa Bay Buccaneers":"TB","Tennessee Titans":"TEN","Washington Commanders":"WAS"}

def _recent_nfl(team_code,n=10):
    df=_nfl_games()
    if df.empty:return []
    rows=[]
    for _,g in df.iterrows():
        if str(g.get("game_type","REG")) not in {"REG","POST"}:continue
        h=str(g.get("home_team"));a=str(g.get("away_team"));hs=_f(g.get("home_score"));as_=_f(g.get("away_score"))
        if hs is None or as_ is None or team_code not in {h,a}:continue
        is_home=h==team_code;pf=hs if is_home else as_;pa=as_ if is_home else hs
        rows.append({"gameday":str(g.get("gameday","")),"win":pf>pa,"pf":pf,"pa":pa})
    return sorted(rows,key=lambda z:z["gameday"])[-n:]

def analyze_nfl_moneyline(row:dict,schedule:pd.DataFrame)->dict|None:
    team=str(row.get("team") or "");price=row.get("moneyline");implied=american_to_prob(price)
    code=NFL_FULL_TO_CODE.get(team)
    if not code or implied is None:return None
    game=_find_game(schedule,team)
    if not game:return None
    away_raw=str(game.get("away_team") or "");home_raw=str(game.get("home_team") or "")
    code_to_full={v:k for k,v in NFL_FULL_TO_CODE.items()}
    away=code_to_full.get(away_raw,away_raw);home=code_to_full.get(home_raw,home_raw)
    opp=home if team==away else away if team==home else None
    opp_code=NFL_FULL_TO_CODE.get(opp) if opp else None
    if not opp_code:return None
    tr=_recent_nfl(code,10);orr=_recent_nfl(opp_code,10)
    if len(tr)<4 or len(orr)<4:return None
    tw=sum(x["win"] for x in tr)/len(tr);ow=sum(x["win"] for x in orr)/len(orr);td=sum(x["pf"]-x["pa"] for x in tr)/len(tr);od=sum(x["pf"]-x["pa"] for x in orr)/len(orr)
    home_adv=.18 if team==home else -.02;z=(tw-ow)*1.8+_clip((td-od)/10,-1,1)+home_adv;p=_clip(1/(1+math.exp(-z)),.16,.84);edge=p-implied
    rating="BEST" if edge>=.08 else "GOOD" if edge>=.035 else "BAD" if edge<=-.05 else "PASS"
    reasons=[];risks=[]
    if tw-ow>.15:reasons.append(f"Recent results favor {team}: {tw:.0%} win rate across the last {len(tr)} tracked games versus {ow:.0%} for {opp}.")
    elif ow-tw>.15:risks.append(f"Recent results favor {opp}: {ow:.0%} win rate versus {tw:.0%} for {team}.")
    if td-od>3:reasons.append(f"Recent scoring margin is better by about {td-od:.1f} points per game.")
    elif od-td>3:risks.append(f"Recent scoring margin favors {opp} by about {od-td:.1f} points per game.")
    if team==home:reasons.append("Home field gives this side a modest model boost.")
    if price and str(price).startswith("+") and edge<=0:risks.insert(0,"The underdog payout is attractive, but the model does not estimate enough win probability to make the plus price worthwhile.")
    if not reasons:reasons.append("The matchup is close; there is no dominant team-form signal.")
    if not risks:risks.append("NFL prices can move quickly with injuries and inactive lists, especially early in the season.")
    return {"team":team,"opponent":opp,"price":price,"implied_probability":implied,"model_probability":p,"edge":edge,"rating":rating,"recent":{"team_win_rate":tw,"opp_win_rate":ow,"team_margin":td,"opp_margin":od},"reasons":reasons,"risks":risks}

def analyze_team_moneyline(sport,row,schedule):
    return analyze_mlb_moneyline(row,schedule) if sport=="MLB" else analyze_nfl_moneyline(row,schedule)
