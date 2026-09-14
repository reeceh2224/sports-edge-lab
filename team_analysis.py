from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
import math
import re

import pandas as pd
import requests

from public_odds import american_to_prob

HEADERS={"User-Agent":"SportsEdgeLab/1.0"}
BASE="https://statsapi.mlb.com/api/v1"


def _clip(x, lo, hi):
    return max(lo,min(hi,x))


def _norm(s):
    return re.sub(r"\s+"," ",str(s or "")).strip().lower()


@lru_cache(maxsize=2)
def _mlb_teams():
    r=requests.get(f"{BASE}/teams",params={"sportId":1},headers=HEADERS,timeout=15);r.raise_for_status()
    return {x.get("name"):int(x.get("id")) for x in r.json().get("teams",[]) if x.get("name") and x.get("id")}


@lru_cache(maxsize=128)
def _recent_team_games(team_id:int, end_day:str, days:int=24):
    end=pd.to_datetime(end_day).date()
    start=end-timedelta(days=days)
    r=requests.get(f"{BASE}/schedule",params={"sportId":1,"teamId":team_id,"startDate":start.isoformat(),"endDate":end.isoformat()},headers=HEADERS,timeout=20);r.raise_for_status()
    rows=[]
    for d in r.json().get("dates",[]):
        for g in d.get("games",[]):
            if g.get("status",{}).get("abstractGameState")!="Final":continue
            a=g.get("teams",{}).get("away",{});h=g.get("teams",{}).get("home",{})
            away_id=(a.get("team") or {}).get("id");home_id=(h.get("team") or {}).get("id")
            if team_id not in (away_id,home_id):continue
            is_home=home_id==team_id
            rf=(h if is_home else a).get("score");ra=(a if is_home else h).get("score")
            if rf is None or ra is None:continue
            rows.append({"date":d.get("date"),"rf":float(rf),"ra":float(ra),"win":float(rf)>float(ra)})
    rows=sorted(rows,key=lambda x:x["date"])
    return rows


@lru_cache(maxsize=256)
def _pitcher_season(pid:int, season:int):
    if not pid:return None
    r=requests.get(f"{BASE}/people/{pid}/stats",params={"stats":"season","group":"pitching","season":season},headers=HEADERS,timeout=15);r.raise_for_status()
    for b in r.json().get("stats",[]):
        splits=b.get("splits",[])
        if splits:return splits[0].get("stat",{})
    return None


def _f(v, default=None):
    try:return float(v)
    except Exception:return default


def _starter_score(stat):
    if not stat:return 0.0
    era=_f(stat.get("era"));whip=_f(stat.get("whip"));ip=_f(stat.get("inningsPitched"),0)
    score=0.0
    if era is not None: score += _clip((4.25-era)/1.5,-1.25,1.25)
    if whip is not None: score += _clip((1.30-whip)/0.35,-1.0,1.0)
    if ip and ip<20: score*=0.55
    return score


def _find_game(schedule:pd.DataFrame, team:str):
    if schedule is None or schedule.empty:return None
    mask=schedule["away_team"].astype(str).str.lower().eq(team.lower())|schedule["home_team"].astype(str).str.lower().eq(team.lower())
    x=schedule[mask]
    return x.iloc[0].to_dict() if not x.empty else None


def analyze_mlb_moneyline(row:dict, schedule:pd.DataFrame)->dict|None:
    team=str(row.get("team") or "");price=row.get("moneyline")
    implied=american_to_prob(price)
    if not team or implied is None:return None
    game=_find_game(schedule,team)
    if not game:return None
    away=str(game.get("away_team") or "");home=str(game.get("home_team") or "")
    opponent=home if team==away else away
    team_home=team==home
    teams=_mlb_teams();tid=teams.get(team);oid=teams.get(opponent)
    if not tid or not oid:return None
    today=str(game.get("game_date") or date.today().isoformat())
    tg=_recent_team_games(tid,today);og=_recent_team_games(oid,today)
    t10=tg[-10:];o10=og[-10:]
    if len(t10)<4 or len(o10)<4:return None
    tw=sum(x["win"] for x in t10)/len(t10);ow=sum(x["win"] for x in o10)/len(o10)
    trd=sum(x["rf"]-x["ra"] for x in t10)/len(t10);ord_=sum(x["rf"]-x["ra"] for x in o10)/len(o10)
    season=date.today().year
    tpid=game.get("away_probable_pitcher_id") if team==away else game.get("home_probable_pitcher_id")
    opid=game.get("home_probable_pitcher_id") if team==away else game.get("away_probable_pitcher_id")
    ts=_pitcher_season(int(tpid),season) if pd.notna(tpid) and tpid else None
    os=_pitcher_season(int(opid),season) if pd.notna(opid) and opid else None
    starter_adv=_starter_score(ts)-_starter_score(os)
    recent_adv=(tw-ow)*1.6 + _clip((trd-ord_)/3,-0.9,0.9)
    home_adv=0.18 if team_home else -0.02
    z=starter_adv*0.55+recent_adv*0.50+home_adv
    p=1/(1+math.exp(-z))
    p=_clip(p,.18,.82)
    edge=p-implied
    if edge>=.08:rating="BEST"
    elif edge>=.035:rating="GOOD"
    elif edge<=-.05:rating="BAD"
    else:rating="PASS"
    reasons=[];risks=[]
    if starter_adv>0.35:reasons.append("Probable-starter matchup favors this side.")
    elif starter_adv<-0.35:risks.append("Probable-starter matchup favors the opponent.")
    if tw-ow>.15:reasons.append(f"Recent form is stronger: {int(round(tw*10))}-{10-int(round(tw*10))} type pace over the last 10 versus {int(round(ow*10))}-{10-int(round(ow*10))} for the opponent.")
    elif ow-tw>.15:risks.append("Opponent has the stronger recent win rate over the last 10 games.")
    if trd-ord_>1.0:reasons.append(f"Recent run differential is better by about {(trd-ord_):.1f} runs per game.")
    elif ord_-trd>1.0:risks.append(f"Recent run differential favors the opponent by about {(ord_-trd):.1f} runs per game.")
    if team_home:reasons.append("Home-field is a small positive in the model.")
    if not reasons:reasons.append("The model does not find a large matchup advantage beyond the price itself.")
    if not risks:risks.append("Baseball moneylines are high-variance; a small estimated edge can disappear quickly with lineup or bullpen changes.")
    tname=game.get("away_probable_pitcher") if team==away else game.get("home_probable_pitcher")
    oname=game.get("home_probable_pitcher") if team==away else game.get("away_probable_pitcher")
    return {
        "team":team,"opponent":opponent,"price":price,"implied_probability":implied,"model_probability":p,"edge":edge,"rating":rating,
        "recent":{"team_win_rate":tw,"opp_win_rate":ow,"team_run_diff":trd,"opp_run_diff":ord_},
        "starter":{"team_name":tname,"opp_name":oname,"team_era":_f((ts or {}).get("era")),"opp_era":_f((os or {}).get("era")),"team_whip":_f((ts or {}).get("whip")),"opp_whip":_f((os or {}).get("whip"))},
        "reasons":reasons,"risks":risks,
    }
