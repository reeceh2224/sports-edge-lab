from __future__ import annotations
from datetime import date
import re
from functools import lru_cache
import pandas as pd
import requests
from public_odds import american_to_prob

HEADERS={"User-Agent":"SportsEdgeLab/1.0"}

MLB_EVENT_ALIASES={
    "ARI":"Arizona Diamondbacks","ATL":"Atlanta Braves","BAL":"Baltimore Orioles","BOS":"Boston Red Sox","CHC":"Chicago Cubs","CHW":"Chicago White Sox",
    "CIN":"Cincinnati Reds","CLE":"Cleveland Guardians","COL":"Colorado Rockies","DET":"Detroit Tigers","HOU":"Houston Astros","KC":"Kansas City Royals",
    "LAA":"Los Angeles Angels","LAD":"Los Angeles Dodgers","MIA":"Miami Marlins","MIL":"Milwaukee Brewers","MIN":"Minnesota Twins","NYM":"New York Mets",
    "NYY":"New York Yankees","OAK":"Athletics","ATH":"Athletics","PHI":"Philadelphia Phillies","PIT":"Pittsburgh Pirates","SD":"San Diego Padres",
    "SF":"San Francisco Giants","SEA":"Seattle Mariners","STL":"St. Louis Cardinals","TB":"Tampa Bay Rays","TEX":"Texas Rangers","TOR":"Toronto Blue Jays","WSH":"Washington Nationals",
}
NFL_EVENT_ALIASES={
    "ARI":"Arizona Cardinals","ATL":"Atlanta Falcons","BAL":"Baltimore Ravens","BUF":"Buffalo Bills","CAR":"Carolina Panthers","CHI":"Chicago Bears","CIN":"Cincinnati Bengals",
    "CLE":"Cleveland Browns","DAL":"Dallas Cowboys","DEN":"Denver Broncos","DET":"Detroit Lions","GB":"Green Bay Packers","HOU":"Houston Texans","IND":"Indianapolis Colts",
    "JAX":"Jacksonville Jaguars","KC":"Kansas City Chiefs","LV":"Las Vegas Raiders","LAC":"Los Angeles Chargers","LA":"Los Angeles Rams","MIA":"Miami Dolphins",
    "MIN":"Minnesota Vikings","NE":"New England Patriots","NO":"New Orleans Saints","NYG":"New York Giants","NYJ":"New York Jets","PHI":"Philadelphia Eagles",
    "PIT":"Pittsburgh Steelers","SF":"San Francisco 49ers","SEA":"Seattle Seahawks","TB":"Tampa Bay Buccaneers","TEN":"Tennessee Titans","WAS":"Washington Commanders",
}

def _norm_name(s:str)->str:
    s=re.sub(r"\([^)]*\)","",str(s)); s=re.sub(r"[^a-zA-Z0-9 .'-]"," ",s)
    return re.sub(r"\s+"," ",s).strip()

def split_player_market(market:str,sport:str)->tuple[str,str]:
    m=_norm_name(market)
    phrases=["Hits + Runs + RBIs","Strikeouts Thrown","Total Bases","Home Runs","Runs Scored","Stolen Bases","RBIs",
             "Passing Yards","Passing Touchdowns","Passing Attempts","Pass Completions","Rushing Yards","Rushing Attempts","Receiving Yards","Receptions","Receiving Touchdowns","Anytime Touchdown","First Touchdown"]
    for p in phrases:
        idx=m.lower().find(p.lower())
        if idx>0: return m[:idx].strip(),p
    # TD markets sometimes have the player in the line rather than market field.
    return "",m

def parse_threshold(line:str)->tuple[str,float]|None:
    s=str(line).replace("−","-").strip()
    m=re.search(r"(\d+(?:\.\d+)?)\s*\+",s)
    if m:return ">=",float(m.group(1))
    m=re.search(r"\b(Over|Under)\s*(\d+(?:\.\d+)?)",s,re.I)
    if m:return (">" if m.group(1).lower()=="over" else "<"),float(m.group(2))
    return None

def _hit(v:float,op:str,t:float)->bool:
    return v>=t if op==">=" else v>t if op==">" else v<t if op=="<" else False

def _trend_summary(values:list[float],op:str,t:float)->dict|None:
    vals=[float(v) for v in values if pd.notna(v)]
    if len(vals)<3:return None
    def chunk(n):
        x=vals[-n:] if len(vals)>=n else vals
        return {"n":len(x),"avg":sum(x)/len(x),"hit_rate":sum(_hit(v,op,t) for v in x)/len(x)}
    return {"last5":chunk(5),"last10":chunk(10),"season":chunk(len(vals)),"games":len(vals)}

def _rating(edge:float|None,games:int,l5:float,l10:float)->str:
    if edge is None or games<4:return "UNRATED"
    # BEST requires both price value and repeated recent success; GOOD is a milder edge.
    if edge>=.12 and games>=8 and l5>=.60 and l10>=.55:return "BEST"
    if edge>=.06 and games>=6 and (l5>=.60 or l10>=.60):return "GOOD"
    if edge<=-.06 or (l5<=.40 and l10<=.45):return "BAD"
    return "PASS"

def _event_teams(event:str,sport:str)->tuple[str|None,str|None]:
    aliases=MLB_EVENT_ALIASES if sport=="MLB" else NFL_EVENT_ALIASES
    txt=str(event)
    # Expand abbreviations and retain raw names when full names are present.
    parts=re.split(r"\s+@\s+",txt)
    if len(parts)!=2:return None,None
    def expand(p):
        p=p.strip()
        if p in aliases:return aliases[p]
        for abbr,full in aliases.items():
            if p.lower()==full.lower():return full
        return p
    return expand(parts[0]),expand(parts[1])

@lru_cache(maxsize=256)
def _mlb_people_search(name:str)->dict|None:
    r=requests.get("https://statsapi.mlb.com/api/v1/people/search",params={"names":name},headers=HEADERS,timeout=15); r.raise_for_status()
    x=r.json().get("people",[]); return x[0] if x else None

@lru_cache(maxsize=512)
def _mlb_game_log(pid:int,group:str,season:int)->list[dict]:
    r=requests.get(f"https://statsapi.mlb.com/api/v1/people/{pid}/stats",params={"stats":"gameLog","group":group,"season":season},headers=HEADERS,timeout=20); r.raise_for_status()
    out=[]
    for block in r.json().get("stats",[]):out.extend(block.get("splits",[]))
    return out

def _mlb_value(prop:str,stat:dict)->float|None:
    try:
        if prop=="Strikeouts Thrown":return float(stat.get("strikeOuts",0))
        if prop=="Home Runs":return float(stat.get("homeRuns",0))
        if prop=="Total Bases":return float(stat.get("totalBases",0))
        if prop=="Runs Scored":return float(stat.get("runs",0))
        if prop=="Stolen Bases":return float(stat.get("stolenBases",0))
        if prop=="RBIs":return float(stat.get("rbi",0))
        if prop=="Hits + Runs + RBIs":return float(stat.get("hits",0))+float(stat.get("runs",0))+float(stat.get("rbi",0))
        if prop.lower().startswith("hits"):return float(stat.get("hits",0))
    except Exception:return None
    return None

def analyze_mlb_prop(event:str,market:str,line:str,odds:str)->dict|None:
    player,prop=split_player_market(market,"MLB"); parsed=parse_threshold(line)
    if not player or not parsed:return None
    op,t=parsed; person=_mlb_people_search(player)
    if not person:return None
    pitching=prop=="Strikeouts Thrown"; logs=_mlb_game_log(int(person["id"]),"pitching" if pitching else "hitting",date.today().year)
    vals=[]; opp_vals=[]; away,home=_event_teams(event,"MLB")
    # Infer player's opponent from game-log team in the most recent split when available.
    player_team=None
    for g in reversed(logs):
        team=(g.get("team") or {}).get("name")
        if team: player_team=team; break
    opponent=home if player_team and away and player_team.lower()==away.lower() else away if player_team and home and player_team.lower()==home.lower() else None
    for g in logs:
        v=_mlb_value(prop,g.get("stat",{}) or {})
        if v is None:continue
        vals.append(v)
        opp=(g.get("opponent") or {}).get("name","")
        if opponent and opp.lower()==opponent.lower():opp_vals.append(v)
    trend=_trend_summary(vals,op,t)
    if not trend:return None
    p=.50*trend["last5"]["hit_rate"]+.30*trend["last10"]["hit_rate"]+.20*trend["season"]["hit_rate"]
    implied=american_to_prob(odds); edge=p-implied if implied is not None else None
    opp=_trend_summary(opp_vals,op,t) if len(opp_vals)>=2 else None
    rating=_rating(edge,trend["games"],trend["last5"]["hit_rate"],trend["last10"]["hit_rate"])
    return {"player":player,"prop":prop,"trend_probability":p,"implied_probability":implied,"edge":edge,"rating":rating,
            "opponent":opponent,"vs_opponent":opp,"player_team":player_team,**trend}

@lru_cache(maxsize=4)
def _nfl_player_stats(season:int)->pd.DataFrame:
    import nflreadpy as nfl
    return nfl.load_player_stats(seasons=season,summary_level="week").to_pandas()

def analyze_nfl_prop(event:str,market:str,line:str,odds:str)->dict|None:
    player,prop=split_player_market(market,"NFL"); parsed=parse_threshold(line)
    # For TD scorer rows, DK sometimes puts player name in line and generic market label.
    if not player and ("touchdown" in market.lower() or "td" in market.lower()):
        player=_norm_name(line); prop="Receiving Touchdowns"; parsed=(">=",1.0)
    if not player or not parsed:return None
    op,t=parsed; df=_nfl_player_stats(date.today().year)
    name_col="player_display_name" if "player_display_name" in df.columns else "player_name"
    x=df[df[name_col].astype(str).str.lower()==player.lower()].copy()
    if x.empty:x=df[df[name_col].astype(str).str.lower().str.contains(re.escape(player.lower()),regex=True,na=False)].copy()
    if x.empty:return None
    stat_map={"Passing Yards":"passing_yards","Passing Touchdowns":"passing_tds","Passing Attempts":"attempts","Pass Completions":"completions",
              "Rushing Yards":"rushing_yards","Rushing Attempts":"carries","Receiving Yards":"receiving_yards","Receptions":"receptions","Receiving Touchdowns":"receiving_tds"}
    col=stat_map.get(prop)
    if not col or col not in x.columns:return None
    if "week" in x.columns:x=x.sort_values("week")
    vals=pd.to_numeric(x[col],errors="coerce").dropna().tolist(); trend=_trend_summary(vals,op,t)
    if not trend:return None
    p=.50*trend["last5"]["hit_rate"]+.30*trend["last10"]["hit_rate"]+.20*trend["season"]["hit_rate"]
    implied=american_to_prob(odds); edge=p-implied if implied is not None else None
    away,home=_event_teams(event,"NFL"); opponent=None; opp=None
    # nflverse commonly includes recent_team/opponent_team. Use it when present.
    if "recent_team" in x.columns:
        team=str(x.iloc[-1].get("recent_team","")); aliases=NFL_EVENT_ALIASES
        team_full=aliases.get(team,team)
        opponent=home if away and team_full.lower()==away.lower() else away if home and team_full.lower()==home.lower() else None
    if opponent and "opponent_team" in x.columns:
        inv={v:k for k,v in NFL_EVENT_ALIASES.items()}; opp_code=inv.get(opponent,opponent)
        xo=x[x["opponent_team"].astype(str).str.upper()==str(opp_code).upper()]
        if not xo.empty:opp=_trend_summary(pd.to_numeric(xo[col],errors="coerce").dropna().tolist(),op,t)
    rating=_rating(edge,trend["games"],trend["last5"]["hit_rate"],trend["last10"]["hit_rate"])
    return {"player":player,"prop":prop,"trend_probability":p,"implied_probability":implied,"edge":edge,"rating":rating,"opponent":opponent,"vs_opponent":opp,**trend}

def analyze_prop(sport:str,event:str,market:str,line:str,odds:str)->dict|None:
    try:return analyze_mlb_prop(event,market,line,odds) if sport=="MLB" else analyze_nfl_prop(event,market,line,odds)
    except Exception:return None
