from __future__ import annotations
from datetime import date
import re
from functools import lru_cache
import pandas as pd
import requests
from public_odds import american_to_prob

HEADERS={"User-Agent":"SportsEdgeLab/1.0"}
MLB_EVENT_ALIASES={
    "ARI":"Arizona Diamondbacks","ATL":"Atlanta Braves","BAL":"Baltimore Orioles","BOS":"Boston Red Sox","CHC":"Chicago Cubs","CHW":"Chicago White Sox","CIN":"Cincinnati Reds","CLE":"Cleveland Guardians","COL":"Colorado Rockies","DET":"Detroit Tigers","HOU":"Houston Astros","KC":"Kansas City Royals","LAA":"Los Angeles Angels","LAD":"Los Angeles Dodgers","MIA":"Miami Marlins","MIL":"Milwaukee Brewers","MIN":"Minnesota Twins","NYM":"New York Mets","NYY":"New York Yankees","OAK":"Athletics","ATH":"Athletics","PHI":"Philadelphia Phillies","PIT":"Pittsburgh Pirates","SD":"San Diego Padres","SF":"San Francisco Giants","SEA":"Seattle Mariners","STL":"St. Louis Cardinals","TB":"Tampa Bay Rays","TEX":"Texas Rangers","TOR":"Toronto Blue Jays","WSH":"Washington Nationals",
}
NFL_EVENT_ALIASES={
    "ARI":"Arizona Cardinals","ATL":"Atlanta Falcons","BAL":"Baltimore Ravens","BUF":"Buffalo Bills","CAR":"Carolina Panthers","CHI":"Chicago Bears","CIN":"Cincinnati Bengals","CLE":"Cleveland Browns","DAL":"Dallas Cowboys","DEN":"Denver Broncos","DET":"Detroit Lions","GB":"Green Bay Packers","HOU":"Houston Texans","IND":"Indianapolis Colts","JAX":"Jacksonville Jaguars","KC":"Kansas City Chiefs","LV":"Las Vegas Raiders","LAC":"Los Angeles Chargers","LA":"Los Angeles Rams","MIA":"Miami Dolphins","MIN":"Minnesota Vikings","NE":"New England Patriots","NO":"New Orleans Saints","NYG":"New York Giants","NYJ":"New York Jets","PHI":"Philadelphia Eagles","PIT":"Pittsburgh Steelers","SF":"San Francisco 49ers","SEA":"Seattle Seahawks","TB":"Tampa Bay Buccaneers","TEN":"Tennessee Titans","WAS":"Washington Commanders",
}
NFL_FULL_TO_CODE={v:k for k,v in NFL_EVENT_ALIASES.items()}


def _norm_name(s:str)->str:
    s=re.sub(r"\([^)]*\)","",str(s));s=re.sub(r"[^a-zA-Z0-9 .'-]"," ",s)
    return re.sub(r"\s+"," ",s).strip()


def split_player_market(market:str,sport:str)->tuple[str,str]:
    m=_norm_name(market)
    phrases=["Hits + Runs + RBIs","Strikeouts Thrown","Pitching Outs","Hits Allowed","Earned Runs","Total Bases","Home Runs","Runs Scored","Stolen Bases","RBIs",
             "Passing Yards","Passing Touchdowns","Passing Attempts","Pass Completions","Interceptions Thrown","Rushing Yards","Rushing Attempts","Receiving Yards","Receptions","Receiving Touchdowns","Anytime Touchdown","First Touchdown"]
    for p in phrases:
        idx=m.lower().find(p.lower())
        if idx>0:return m[:idx].strip(),p
    return "",m


def parse_threshold(line:str)->tuple[str,float]|None:
    s=str(line).replace("−","-").strip()
    m=re.search(r"(\d+(?:\.\d+)?)\s*\+",s)
    if m:return ">=",float(m.group(1))
    m=re.search(r"\b(Over|Under)\s*(\d+(?:\.\d+)?)",s,re.I)
    if m:return (">" if m.group(1).lower()=="over" else "<"),float(m.group(2))
    m=re.search(r"\b([ou])\s*(\d+(?:\.\d+)?)",s,re.I)
    if m:return (">" if m.group(1).lower()=="o" else "<"),float(m.group(2))
    return None


def _hit(v,op,t):return v>=t if op==">=" else v>t if op==">" else v<t

def _chunk(vals,op,t,n):
    x=vals[-n:] if len(vals)>=n else vals
    return {"n":len(x),"avg":sum(x)/len(x),"hit_rate":sum(_hit(v,op,t) for v in x)/len(x),"values":x}

def _trend_summary(values,op,t):
    vals=[float(v) for v in values if pd.notna(v)]
    if len(vals)<3:return None
    return {"last3":_chunk(vals,op,t,3),"last5":_chunk(vals,op,t,5),"last10":_chunk(vals,op,t,10),"season":_chunk(vals,op,t,len(vals)),"games":len(vals)}


def _rating(edge,games,l3,l5,l10,opp_rate=None):
    if edge is None or games<4:return "UNRATED"
    support=.42*l5+.28*l10+.20*l3+.10*(opp_rate if opp_rate is not None else l10)
    if edge>=.11 and games>=8 and support>=.60:return "BEST"
    if edge>=.045 and games>=6 and support>=.54:return "GOOD"
    if edge<=-.055 or support<=.40:return "BAD"
    return "PASS"


def _event_teams(event,sport):
    aliases=MLB_EVENT_ALIASES if sport=="MLB" else NFL_EVENT_ALIASES
    parts=re.split(r"\s+@\s+",str(event))
    if len(parts)!=2:return None,None
    def expand(p):
        p=p.strip()
        if p in aliases:return aliases[p]
        for _,full in aliases.items():
            if p.lower()==full.lower():return full
        return p
    return expand(parts[0]),expand(parts[1])


def _f(v,default=None):
    try:return float(v)
    except Exception:return default


@lru_cache(maxsize=256)
def _mlb_people_search(name):
    r=requests.get("https://statsapi.mlb.com/api/v1/people/search",params={"names":name},headers=HEADERS,timeout=15);r.raise_for_status()
    x=r.json().get("people",[]);return x[0] if x else None

@lru_cache(maxsize=1024)
def _mlb_game_log(pid,group,season):
    r=requests.get(f"https://statsapi.mlb.com/api/v1/people/{pid}/stats",params={"stats":"gameLog","group":group,"season":season},headers=HEADERS,timeout=20);r.raise_for_status()
    out=[]
    for b in r.json().get("stats",[]):out.extend(b.get("splits",[]))
    return out

@lru_cache(maxsize=256)
def _mlb_vs_player(pid,opp_pid,season):
    try:
        r=requests.get(f"https://statsapi.mlb.com/api/v1/people/{pid}/stats",params={"stats":"vsPlayer","group":"hitting","season":season,"opposingPlayerId":opp_pid},headers=HEADERS,timeout=15);r.raise_for_status()
        for b in r.json().get("stats",[]):
            if b.get("splits"):return b["splits"][0].get("stat",{})
    except Exception:pass
    return None

@lru_cache(maxsize=64)
def _mlb_schedule(day):
    r=requests.get("https://statsapi.mlb.com/api/v1/schedule",params={"sportId":1,"date":day,"hydrate":"team,probablePitcher"},headers=HEADERS,timeout=15);r.raise_for_status()
    rows=[]
    for d in r.json().get("dates",[]):
        for g in d.get("games",[]):
            a=g.get("teams",{}).get("away",{});h=g.get("teams",{}).get("home",{})
            rows.append({"away":(a.get("team") or {}).get("name"),"home":(h.get("team") or {}).get("name"),"away_pid":(a.get("probablePitcher") or {}).get("id"),"home_pid":(h.get("probablePitcher") or {}).get("id"),"away_pitcher":(a.get("probablePitcher") or {}).get("fullName"),"home_pitcher":(h.get("probablePitcher") or {}).get("fullName")})
    return rows


def _mlb_value(prop,stat):
    try:
        if prop=="Strikeouts Thrown":return _f(stat.get("strikeOuts"))
        if prop=="Pitching Outs":return _f(stat.get("outs"),_f(stat.get("inningsPitched"),0)*3)
        if prop=="Hits Allowed":return _f(stat.get("hits"))
        if prop=="Earned Runs":return _f(stat.get("earnedRuns"))
        if prop=="Home Runs":return _f(stat.get("homeRuns"))
        if prop=="Total Bases":return _f(stat.get("totalBases"))
        if prop=="Runs Scored":return _f(stat.get("runs"))
        if prop=="Stolen Bases":return _f(stat.get("stolenBases"))
        if prop=="RBIs":return _f(stat.get("rbi"))
        if prop=="Hits + Runs + RBIs":return _f(stat.get("hits"),0)+_f(stat.get("runs"),0)+_f(stat.get("rbi"),0)
        if prop.lower().startswith("hits"):return _f(stat.get("hits"))
    except Exception:return None
    return None


def _current_probable_pitcher(event,player_team):
    away,home=_event_teams(event,"MLB")
    if not away or not home:return None,None
    for offset in range(0,3):
        day=(date.today()+pd.Timedelta(days=offset)).isoformat()
        for g in _mlb_schedule(day):
            if {str(g.get("away")),str(g.get("home"))}=={away,home}:
                if player_team==away:return g.get("home_pid"),g.get("home_pitcher")
                if player_team==home:return g.get("away_pid"),g.get("away_pitcher")
    return None,None


def analyze_mlb_prop(event,market,line,odds):
    player,prop=split_player_market(market,"MLB");parsed=parse_threshold(line)
    if not player or not parsed:return None
    op,t=parsed;person=_mlb_people_search(player)
    if not person:return None
    pitching=prop in {"Strikeouts Thrown","Pitching Outs","Hits Allowed","Earned Runs"};group="pitching" if pitching else "hitting"
    logs=[]
    for yr in [date.today().year-1,date.today().year]:
        try:logs.extend(_mlb_game_log(int(person["id"]),group,yr))
        except Exception:pass
    if not logs:return None
    logs=sorted(logs,key=lambda g:str(g.get("date","")))
    player_team=None
    for g in reversed(logs):
        team=(g.get("team") or {}).get("name")
        if team:player_team=team;break
    away,home=_event_teams(event,"MLB")
    if player_team and away and home and player_team not in {away,home}:return None
    opponent=home if player_team==away else away if player_team==home else None
    vals=[];opp_vals=[]
    for g in logs:
        v=_mlb_value(prop,g.get("stat",{}) or {})
        if v is None:continue
        vals.append(v)
        if opponent and (g.get("opponent") or {}).get("name","").lower()==opponent.lower():opp_vals.append(v)
    trend=_trend_summary(vals,op,t)
    if not trend:return None
    opp_summary=_trend_summary(opp_vals,op,t) if len(opp_vals)>=2 else None
    opp_rate=(opp_summary or {}).get("season",{}).get("hit_rate")
    p=.35*trend["last3"]["hit_rate"]+.30*trend["last5"]["hit_rate"]+.20*trend["last10"]["hit_rate"]+.15*trend["season"]["hit_rate"]
    if opp_rate is not None:p=.82*p+.18*opp_rate
    implied=american_to_prob(odds);edge=p-implied if implied is not None else None
    rating=_rating(edge,trend["games"],trend["last3"]["hit_rate"],trend["last5"]["hit_rate"],trend["last10"]["hit_rate"],opp_rate)
    matchup={}
    if not pitching and player_team:
        opp_pid,opp_name=_current_probable_pitcher(event,player_team)
        if opp_pid:
            vs=_mlb_vs_player(int(person["id"]),int(opp_pid),date.today().year)
            if vs:
                ab=int(_f(vs.get("atBats"),0));hits=int(_f(vs.get("hits"),0));hr=int(_f(vs.get("homeRuns"),0));so=int(_f(vs.get("strikeOuts"),0))
                matchup={"pitcher":opp_name,"pa":int(_f(vs.get("plateAppearances"),ab)),"ab":ab,"hits":hits,"hr":hr,"so":so,"avg":_f(vs.get("avg"))}
    reasons=[];risks=[]
    side="OVER" if op in {">",">="} else "UNDER"
    if trend["last3"]["hit_rate"]>=.67:reasons.append(f"Recent form supports the {side}: it hit in {round(trend['last3']['hit_rate']*trend['last3']['n'])} of the last {trend['last3']['n']} games.")
    elif trend["last3"]["hit_rate"]<=.33:risks.append(f"Very recent form is against the {side}: only {round(trend['last3']['hit_rate']*trend['last3']['n'])} of the last {trend['last3']['n']} hit.")
    if trend["last10"]["hit_rate"]>=.60:reasons.append(f"The side has hit {trend['last10']['hit_rate']:.0%} over the last {trend['last10']['n']} games.")
    elif trend["last10"]["hit_rate"]<=.40:risks.append(f"It has hit only {trend['last10']['hit_rate']:.0%} over the last {trend['last10']['n']} games.")
    if opp_summary:
        txt=f"Against {opponent}, this side hit {opp_summary['season']['hit_rate']:.0%} in {opp_summary['season']['n']} tracked games (average {opp_summary['season']['avg']:.2f})."
        (reasons if opp_summary['season']['hit_rate']>=.55 else risks).append(txt)
    if matchup and matchup.get("ab",0)>=3:
        reasons.append(f"Direct matchup vs {matchup['pitcher']}: {matchup['hits']} hits in {matchup['ab']} AB"+(f", {matchup['hr']} HR" if matchup['hr'] else "")+". Small samples are down-weighted.")
    if edge is not None and edge<0:risks.append("The sportsbook price requires a higher hit probability than this trend model estimates.")
    if not reasons:reasons.append("The strongest support comes from the combined recent/season hit-rate model rather than one standout split.")
    if not risks:risks.append("No major statistical red flag was found, but prop outcomes remain high-variance.")
    return {"player":player,"prop":prop,"trend_probability":p,"implied_probability":implied,"edge":edge,"rating":rating,"opponent":opponent,"vs_opponent":opp_summary,"player_team":player_team,"matchup":matchup,"side":side,"reasons":reasons,"risks":risks,**trend}


@lru_cache(maxsize=6)
def _nfl_player_stats_one(season):
    import nflreadpy as nfl
    return nfl.load_player_stats(seasons=season,summary_level="week").to_pandas()

@lru_cache(maxsize=2)
def _nfl_stats_combined():
    frames=[]
    for yr in [date.today().year-1,date.today().year]:
        try:
            x=_nfl_player_stats_one(yr).copy();x["_season"]=yr;frames.append(x)
        except Exception:pass
    return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()

@lru_cache(maxsize=2)
def _nfl_roster():
    yr=date.today().year
    url=f"https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{yr}.parquet"
    try:return pd.read_parquet(url)
    except Exception:return pd.DataFrame()


def _find_nfl_player(df,player):
    if df.empty:return df
    nc="player_display_name" if "player_display_name" in df.columns else "player_name" if "player_name" in df.columns else None
    if not nc:return df.iloc[0:0]
    norm=_norm_name(player).lower();s=df[nc].astype(str).map(lambda z:_norm_name(z).lower())
    x=df[s.eq(norm)]
    if x.empty:
        toks=norm.split()
        if toks:x=df[s.str.contains(re.escape(toks[-1]),na=False)]
    return x.copy()


def _nfl_current_team(player,x):
    roster=_nfl_roster()
    if not roster.empty:
        nc=next((c for c in ["full_name","player_name","player_display_name"] if c in roster.columns),None)
        tc=next((c for c in ["team","team_abbr","recent_team"] if c in roster.columns),None)
        if nc and tc:
            s=roster[nc].astype(str).map(lambda z:_norm_name(z).lower())
            z=roster[s.eq(_norm_name(player).lower())]
            if not z.empty:return str(z.iloc[-1][tc])
    for tc in ["recent_team","team"]:
        if tc in x.columns and not x.empty:
            y=x[x[tc].notna()]
            if not y.empty:return str(y.iloc[-1][tc])
    return None


def _nfl_defense_context(df,opp_code,stat_col,position=None):
    if df.empty or "opponent_team" not in df.columns or stat_col not in df.columns:return None
    hist=df[(df["opponent_team"].astype(str).str.upper()==str(opp_code).upper()) & (df["_season"]==date.today().year-1)].copy()
    if position and "position" in hist.columns:hist=hist[hist["position"].astype(str).str.upper()==position.upper()]
    elif position and "position_group" in hist.columns:hist=hist[hist["position_group"].astype(str).str.upper()==position.upper()]
    if hist.empty:return None
    weekcols=[c for c in ["season","week"] if c in hist.columns]
    vals=pd.to_numeric(hist[stat_col],errors="coerce")
    if len(weekcols)==2:
        per=hist.assign(_v=vals).groupby(weekcols,dropna=False)["_v"].sum()
        avg=float(per.mean()) if len(per) else None
        return {"avg_allowed":avg,"games":int(len(per)),"position":position}
    return {"avg_allowed":float(vals.mean()),"games":int(vals.notna().sum()),"position":position}


def analyze_nfl_prop(event,market,line,odds):
    player,prop=split_player_market(market,"NFL");parsed=parse_threshold(line)
    if not player and ("touchdown" in market.lower() or "td" in market.lower()):
        player=_norm_name(line);prop="Anytime Touchdown";parsed=(">=",1.0)
    if not player or not parsed:return None
    df=_nfl_stats_combined();x=_find_nfl_player(df,player)
    if x.empty:return None
    team_code=_nfl_current_team(player,x)
    away,home=_event_teams(event,"NFL")
    allowed_codes={NFL_FULL_TO_CODE.get(away,away),NFL_FULL_TO_CODE.get(home,home)}
    if team_code and str(team_code).upper() not in {str(c).upper() for c in allowed_codes}:return None
    opponent=home if str(team_code).upper()==str(NFL_FULL_TO_CODE.get(away,away)).upper() else away if str(team_code).upper()==str(NFL_FULL_TO_CODE.get(home,home)).upper() else None
    stat_map={"Passing Yards":"passing_yards","Passing Touchdowns":"passing_tds","Passing Attempts":"attempts","Pass Completions":"completions","Interceptions Thrown":"interceptions","Rushing Yards":"rushing_yards","Rushing Attempts":"carries","Receiving Yards":"receiving_yards","Receptions":"receptions","Receiving Touchdowns":"receiving_tds"}
    if prop in {"Anytime Touchdown","First Touchdown"}:
        for c in ["rushing_tds","receiving_tds"]:
            if c not in x.columns:x[c]=0
        x=x.copy();x["_tds"]=pd.to_numeric(x["rushing_tds"],errors="coerce").fillna(0)+pd.to_numeric(x["receiving_tds"],errors="coerce").fillna(0);col="_tds"
    else:col=stat_map.get(prop)
    if not col or col not in x.columns:return None
    sortcols=[c for c in ["_season","week"] if c in x.columns]
    if sortcols:x=x.sort_values(sortcols)
    vals=pd.to_numeric(x[col],errors="coerce").dropna().tolist();op,t=parsed;trend=_trend_summary(vals,op,t)
    if not trend:return None
    opp_summary=None
    if opponent and "opponent_team" in x.columns:
        opp_code=NFL_FULL_TO_CODE.get(opponent,opponent)
        xo=x[x["opponent_team"].astype(str).str.upper()==str(opp_code).upper()]
        ov=pd.to_numeric(xo[col],errors="coerce").dropna().tolist()
        if len(ov)>=2:opp_summary=_trend_summary(ov,op,t)
    opp_rate=(opp_summary or {}).get("season",{}).get("hit_rate")
    p=.30*trend["last3"]["hit_rate"]+.30*trend["last5"]["hit_rate"]+.25*trend["last10"]["hit_rate"]+.15*trend["season"]["hit_rate"]
    if opp_rate is not None:p=.85*p+.15*opp_rate
    implied=american_to_prob(odds);edge=p-implied if implied is not None else None
    rating=_rating(edge,trend["games"],trend["last3"]["hit_rate"],trend["last5"]["hit_rate"],trend["last10"]["hit_rate"],opp_rate)
    pos=None
    for pc in ["position","position_group"]:
        if pc in x.columns and x[pc].notna().any():pos=str(x[x[pc].notna()].iloc[-1][pc]);break
    dcol="receiving_yards" if prop in {"Receiving Yards","Receptions"} else "rushing_yards" if prop in {"Rushing Yards","Rushing Attempts"} else "passing_yards" if prop.startswith("Passing") or prop=="Pass Completions" else "_tds" if prop in {"Anytime Touchdown","First Touchdown","Receiving Touchdowns"} else col
    dctx=None
    if opponent:
        odf=df.copy()
        if dcol=="_tds":
            for c in ["rushing_tds","receiving_tds"]:
                if c not in odf.columns:odf[c]=0
            odf["_tds"]=pd.to_numeric(odf["rushing_tds"],errors="coerce").fillna(0)+pd.to_numeric(odf["receiving_tds"],errors="coerce").fillna(0)
        dctx=_nfl_defense_context(odf,NFL_FULL_TO_CODE.get(opponent,opponent),dcol,pos if prop in {"Receiving Yards","Receptions","Receiving Touchdowns"} else None)
    side="OVER" if op in {">",">="} else "UNDER"
    reasons=[];risks=[]
    if trend["last5"]["hit_rate"]>=.60:reasons.append(f"The {side} hit in {trend['last5']['hit_rate']:.0%} of the last {trend['last5']['n']} tracked games.")
    elif trend["last5"]["hit_rate"]<=.40:risks.append(f"The {side} hit in only {trend['last5']['hit_rate']:.0%} of the last {trend['last5']['n']} tracked games.")
    if opp_summary:
        msg=f"In prior meetings with {opponent}, this side hit {opp_summary['season']['hit_rate']:.0%} in {opp_summary['season']['n']} tracked games (average {opp_summary['season']['avg']:.1f})."
        (reasons if opp_summary['season']['hit_rate']>=.55 else risks).append(msg)
    if dctx and dctx.get("avg_allowed") is not None:
        reasons.append(f"Matchup context: {opponent} allowed about {dctx['avg_allowed']:.1f} {prop.lower()} units per game to the comparison group last season"+(f" ({pos})" if dctx.get('position') else "")+".")
    if edge is not None and edge<0:risks.append("The posted price asks you to pay for a higher probability than the historical trend model estimates.")
    if not reasons:reasons.append("The grade is driven by the blended recent/season hit rate and price rather than one dominant split.")
    if not risks:risks.append("NFL usage can change quickly with injuries, depth-chart movement and game script, especially early in the season.")
    return {"player":player,"prop":prop,"trend_probability":p,"implied_probability":implied,"edge":edge,"rating":rating,"opponent":opponent,"vs_opponent":opp_summary,"player_team":NFL_EVENT_ALIASES.get(str(team_code),team_code),"position":pos,"defense_context":dctx,"side":side,"reasons":reasons,"risks":risks,**trend}


def analyze_prop(sport,event,market,line,odds):
    try:return analyze_mlb_prop(event,market,line,odds) if sport=="MLB" else analyze_nfl_prop(event,market,line,odds)
    except Exception:return None
