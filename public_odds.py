from __future__ import annotations

from io import StringIO
from datetime import datetime, timezone
import re
from typing import Iterable

import pandas as pd
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1",
    "Accept-Language": "en-US,en;q=0.9",
}

# ScoresAndOdds exposes a compact public board with Moneyline / Total / Runline (MLB)
# and Moneyline / Total / Spread (NFL). It is much easier to validate than generic
# matchup/trends tables because each row is one team and each market has its own column.
TEAM_URLS = {
    "MLB": "https://www.scoresandodds.com/mlb",
    "NFL": "https://www.scoresandodds.com/nfl",
}

# DraftKings Network's public props tool uses event-group ids. Using the sport-specific
# ids fixes the prior bug where the NFL page could return MLB rows from the default view.
PROP_URLS = {
    "MLB": "https://dknetwork.draftkings.com/draftkings-sportsbook-player-props/?tb_edate=n7days&tb_eg=84240&tb_view=2",
    "NFL": "https://dknetwork.draftkings.com/draftkings-sportsbook-player-props/?tb_edate=n7days&tb_eg=88808&tb_view=2",
}

ROTOWIRE_PROP_URLS = {
    "MLB": "https://www.rotowire.com/betting/mlb/player-props.php?book=draftkings",
    "NFL": "https://www.rotowire.com/betting/nfl/player-props.php?book=draftkings",
}

ROTOWIRE_MARKETS = {
    "MLB": ["Strikeouts","Total Bases","Hits","Runs Scored","Earned Runs","RBIs","Stolen Bases","Home Runs"],
    "NFL": ["Passing Yards","Rushing Yards","Receiving Yards","Receptions","Passing Touchdowns","Rushing Attempts","Passing Attempts"],
}

MLB_SHORT = {
    "Diamondbacks":"Arizona Diamondbacks","D-backs":"Arizona Diamondbacks","Dodgers":"Los Angeles Dodgers",
    "Angels":"Los Angeles Angels","Athletics":"Athletics","Yankees":"New York Yankees","Mets":"New York Mets",
    "White Sox":"Chicago White Sox","Red Sox":"Boston Red Sox","Guardians":"Cleveland Guardians","Nationals":"Washington Nationals",
    "Braves":"Atlanta Braves","Orioles":"Baltimore Orioles","Cubs":"Chicago Cubs","Reds":"Cincinnati Reds",
    "Rockies":"Colorado Rockies","Tigers":"Detroit Tigers","Astros":"Houston Astros","Royals":"Kansas City Royals",
    "Marlins":"Miami Marlins","Brewers":"Milwaukee Brewers","Twins":"Minnesota Twins","Phillies":"Philadelphia Phillies",
    "Pirates":"Pittsburgh Pirates","Padres":"San Diego Padres","Giants":"San Francisco Giants","Mariners":"Seattle Mariners",
    "Cardinals":"St. Louis Cardinals","Rays":"Tampa Bay Rays","Rangers":"Texas Rangers","Blue Jays":"Toronto Blue Jays",
}
NFL_SHORT = {
    "Cardinals":"Arizona Cardinals","Falcons":"Atlanta Falcons","Ravens":"Baltimore Ravens","Bills":"Buffalo Bills",
    "Panthers":"Carolina Panthers","Bears":"Chicago Bears","Bengals":"Cincinnati Bengals","Browns":"Cleveland Browns",
    "Cowboys":"Dallas Cowboys","Broncos":"Denver Broncos","Lions":"Detroit Lions","Packers":"Green Bay Packers",
    "Texans":"Houston Texans","Colts":"Indianapolis Colts","Jaguars":"Jacksonville Jaguars","Chiefs":"Kansas City Chiefs",
    "Raiders":"Las Vegas Raiders","Chargers":"Los Angeles Chargers","Rams":"Los Angeles Rams","Dolphins":"Miami Dolphins",
    "Vikings":"Minnesota Vikings","Patriots":"New England Patriots","Saints":"New Orleans Saints","Giants":"New York Giants",
    "Jets":"New York Jets","Eagles":"Philadelphia Eagles","Steelers":"Pittsburgh Steelers","49ers":"San Francisco 49ers",
    "Seahawks":"Seattle Seahawks","Buccaneers":"Tampa Bay Buccaneers","Titans":"Tennessee Titans","Commanders":"Washington Commanders",
}


def _get(url: str, timeout: int = 25) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def _flatten_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [" ".join(str(x) for x in c if str(x) != "nan").strip() for c in out.columns]
    else:
        out.columns = [str(c).strip() for c in out.columns]
    return out


def _tables_from_html(html: str) -> list[pd.DataFrame]:
    try:
        return [_flatten_cols(t) for t in pd.read_html(StringIO(html))]
    except Exception:
        return []


def _clean_text(v) -> str:
    if pd.isna(v):
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()


def _american(v) -> str | None:
    s = _clean_text(v).replace("−", "-")
    if s.lower() == "even": return "+100"
    m = re.search(r"(?<!\d)([+-]\d{2,4})(?!\d)", s)
    return m.group(1) if m else None


def _market_text(v) -> str | None:
    """Validate a total/spread/runline cell like o8 -109, +1.5 -131, -3 -110."""
    s = _clean_text(v).replace("−", "-").lower()
    if not s: return None
    s = re.sub(r"\beven\b", "+100", s)
    # Total: o/u + number + American price
    mt = re.search(r"\b([ou])\s*(\d+(?:\.\d+)?)\s*([+-]\d{2,4})", s, re.I)
    if mt:
        return f"{mt.group(1).upper()}{mt.group(2)} {mt.group(3)}"
    # Spread/runline: signed line + American price
    ms = re.search(r"(?<!\d)([+-]\d+(?:\.\d+)?)\s+([+-]\d{2,4})(?!\d)", s)
    if ms:
        return f"{ms.group(1)} {ms.group(2)}"
    return None


def _team_name(cell: str, sport: str) -> str | None:
    text = _clean_text(cell)
    aliases = MLB_SHORT if sport == "MLB" else NFL_SHORT
    for short, full in sorted(aliases.items(), key=lambda kv: len(kv[0]), reverse=True):
        if re.search(rf"\b{re.escape(short)}\b", text, re.I):
            return full
    return None


def _first_matching_col(cols: Iterable[str], needle: str) -> str | None:
    for c in cols:
        if needle.lower() in str(c).lower(): return c
    return None


def _clean_scoresandodds_table(t: pd.DataFrame, sport: str) -> pd.DataFrame:
    if t.empty or len(t.columns) < 4: return pd.DataFrame()
    cols = list(t.columns)
    ml_col = _first_matching_col(cols, "moneyline")
    total_col = _first_matching_col(cols, "total")
    side_col = _first_matching_col(cols, "runline") if sport == "MLB" else _first_matching_col(cols, "spread")
    open_col = _first_matching_col(cols, "open")
    if not ml_col or not total_col or not side_col: return pd.DataFrame()

    team_col = cols[0]
    rows=[]
    for _, row in t.iterrows():
        raw_team = _clean_text(row.get(team_col, ""))
        team = _team_name(raw_team, sport)
        if not team: continue
        ml = _american(row.get(ml_col, ""))
        total = _market_text(row.get(total_col, ""))
        side = _market_text(row.get(side_col, ""))
        opened = _clean_text(row.get(open_col, "")) if open_col else ""
        if not any([ml,total,side]): continue
        # Extract pitcher label after team for MLB when present; useful context in UI.
        pitcher=""
        if sport=="MLB":
            short = next((s for s,f in MLB_SHORT.items() if f==team and re.search(rf"\b{re.escape(s)}\b", raw_team, re.I)), None)
            if short:
                tail=re.split(rf"\b{re.escape(short)}\b", raw_team, maxsplit=1, flags=re.I)[-1].strip()
                pitcher=re.sub(r"^\s*", "", tail)
        rows.append({"team":team,"moneyline":ml,"total":total,"side":side,"open":opened,"pitcher":pitcher})

    if not rows: return pd.DataFrame()
    out=pd.DataFrame(rows).drop_duplicates(subset=["team","moneyline","total","side"])
    # Pair the board's consecutive away/home rows. We never fabricate a price; pairing is display-only.
    matchup=[]
    for i in range(0,len(out),2):
        pair=out.iloc[i:i+2]
        label=" @ ".join(pair["team"].tolist()) if len(pair)==2 else pair.iloc[0]["team"]
        matchup.extend([label]*len(pair))
    out.insert(0,"matchup",matchup)
    return out.reset_index(drop=True)


def fetch_team_moneylines(sport: str) -> tuple[pd.DataFrame, dict]:
    """Compatibility name: now returns all primary team markets, not only moneylines."""
    url=TEAM_URLS[sport]
    r=_get(url)
    frames=[]
    for t in _tables_from_html(r.text):
        x=_clean_scoresandodds_table(t,sport)
        if not x.empty: frames.append(x)
    out=pd.concat(frames,ignore_index=True).drop_duplicates() if frames else pd.DataFrame(
        columns=["matchup","team","moneyline","total","side","open","pitcher"]
    )
    return out,{"source":"ScoresAndOdds public board","url":url,"fetched_at":datetime.now(timezone.utc).isoformat(),"rows":len(out)}


def _normalize_dk_table(t: pd.DataFrame, sport: str) -> pd.DataFrame:
    cols={str(c).lower().strip():c for c in t.columns}
    required=["event","event date","market","betslip line","odds"]
    if not all(x in cols for x in required): return pd.DataFrame()
    out=pd.DataFrame({
        "event":t[cols["event"]].map(_clean_text),"event_date":t[cols["event date"]].map(_clean_text),
        "market":t[cols["market"]].map(_clean_text),"line":t[cols["betslip line"]].map(_clean_text),"odds":t[cols["odds"]].map(_clean_text),
    })
    out["odds"]=out["odds"].str.replace("−","-",regex=False)
    out=out[out["odds"].str.match(r"^(?:[+-]\d{2,4}|even)$",case=False,na=False)]
    if sport=="MLB":
        mask=out["market"].str.contains(r"home runs?|hits?(?:\s|$)|total bases|runs? scored|rbi|strikeouts? thrown|stolen bases?|hits \+ runs \+ rbis",case=False,regex=True,na=False)
    else:
        mask=out["market"].str.contains(r"passing|rushing|receiving|receptions|touchdowns?|anytime td|first td|interceptions|completions|attempts",case=False,regex=True,na=False)
    out=out[mask].copy()
    # Guard against wrong-sport rows even if DK changes its query behavior.
    if sport=="NFL":
        mlb_names="|".join(re.escape(x) for x in ["Dodgers","Yankees","Mets","Braves","Cubs","Reds","Phillies","Brewers","Orioles","Twins","Tigers","Guardians","Astros","Mariners","Padres","Giants","Diamondbacks","Marlins","Blue Jays","White Sox","Red Sox"])
        out=out[~out["event"].str.contains(mlb_names,case=False,regex=True,na=False)]
    out["book"]="DraftKings"; out["source"]="DraftKings Network"
    return out.drop_duplicates().reset_index(drop=True)


def _clean_player_name(v: str) -> str:
    s=_clean_text(v)
    # RotoWire sometimes renders "L. Lars Nootbaar"; remove the duplicate initial.
    m=re.match(r"^[A-Z]\.\s+([A-Za-z][A-Za-z'.-]+\s+.+)$",s)
    return m.group(1).strip() if m else s


def _team_code_from_cell(v: str, sport: str) -> str | None:
    s=_clean_text(v).replace("@","").strip().upper()
    if not s:return None
    aliases=MLB_SHORT if sport=="MLB" else NFL_SHORT
    # If table already uses codes, keep them.
    if re.fullmatch(r"[A-Z]{2,3}",s):return s
    full=_team_name(s,sport)
    if not full:return None
    if sport=="MLB":
        rev={"Arizona Diamondbacks":"ARI","Atlanta Braves":"ATL","Baltimore Orioles":"BAL","Boston Red Sox":"BOS","Chicago Cubs":"CHC","Chicago White Sox":"CHW","Cincinnati Reds":"CIN","Cleveland Guardians":"CLE","Colorado Rockies":"COL","Detroit Tigers":"DET","Houston Astros":"HOU","Kansas City Royals":"KC","Los Angeles Angels":"LAA","Los Angeles Dodgers":"LAD","Miami Marlins":"MIA","Milwaukee Brewers":"MIL","Minnesota Twins":"MIN","New York Mets":"NYM","New York Yankees":"NYY","Athletics":"ATH","Philadelphia Phillies":"PHI","Pittsburgh Pirates":"PIT","San Diego Padres":"SD","San Francisco Giants":"SF","Seattle Mariners":"SEA","St. Louis Cardinals":"STL","Tampa Bay Rays":"TB","Texas Rangers":"TEX","Toronto Blue Jays":"TOR","Washington Nationals":"WSH"}
    else:
        rev={v:k for k,v in {"ARI":"Arizona Cardinals","ATL":"Atlanta Falcons","BAL":"Baltimore Ravens","BUF":"Buffalo Bills","CAR":"Carolina Panthers","CHI":"Chicago Bears","CIN":"Cincinnati Bengals","CLE":"Cleveland Browns","DAL":"Dallas Cowboys","DEN":"Denver Broncos","DET":"Detroit Lions","GB":"Green Bay Packers","HOU":"Houston Texans","IND":"Indianapolis Colts","JAX":"Jacksonville Jaguars","KC":"Kansas City Chiefs","LV":"Las Vegas Raiders","LAC":"Los Angeles Chargers","LA":"Los Angeles Rams","MIA":"Miami Dolphins","MIN":"Minnesota Vikings","NE":"New England Patriots","NO":"New Orleans Saints","NYG":"New York Giants","NYJ":"New York Jets","PHI":"Philadelphia Eagles","PIT":"Pittsburgh Steelers","SF":"San Francisco 49ers","SEA":"Seattle Seahawks","TB":"Tampa Bay Buccaneers","TEN":"Tennessee Titans","WAS":"Washington Commanders"}.items()}
    return rev.get(full)


def _parse_rotowire_table(t: pd.DataFrame, sport: str) -> pd.DataFrame:
    if t.empty:return pd.DataFrame()
    x=_flatten_cols(t)
    cols=list(x.columns)
    player_col=next((c for c in cols if re.search(r"\bplayer\b",str(c),re.I)),None)
    team_col=next((c for c in cols if re.search(r"(^|\s)team($|\s)",str(c),re.I)),None)
    opp_col=next((c for c in cols if re.search(r"(^|\s)opp($|\s)",str(c),re.I)),None)
    if not player_col or not team_col or not opp_col:return pd.DataFrame()

    table_blob=" ".join(map(str,cols)).lower()
    market=next((m for m in ROTOWIRE_MARKETS[sport] if m.lower() in table_blob),None)
    if not market:return pd.DataFrame()

    # Prefer DraftKings-specific columns when present. On some tables the header is only
    # "Under" / "Over" because the sportsbook is selected in the page query.
    line_col=next((c for c in cols if market.lower() in str(c).lower() and "under" not in str(c).lower() and "over" not in str(c).lower()),None)
    over_cols=[c for c in cols if "over" in str(c).lower()]
    under_cols=[c for c in cols if "under" in str(c).lower()]
    dk_over=next((c for c in over_cols if "draftkings" in str(c).lower()), over_cols[0] if over_cols else None)
    dk_under=next((c for c in under_cols if "draftkings" in str(c).lower()), under_cols[0] if under_cols else None)
    if not line_col or not (dk_over or dk_under):return pd.DataFrame()

    rows=[]
    market_name={"Strikeouts":"Strikeouts Thrown","Home Runs":"Home Runs","RBIs":"RBIs"}.get(market,market)
    for _,r in x.iterrows():
        player=_clean_player_name(r.get(player_col,""));tc=_team_code_from_cell(r.get(team_col,""),sport);oc=_team_code_from_cell(r.get(opp_col,""),sport)
        if not player or not tc or not oc:continue
        raw_line=_clean_text(r.get(line_col,""))
        lm=re.search(r"(\d+(?:\.\d+)?)",raw_line)
        if not lm:continue
        threshold=lm.group(1);event=f"{tc} @ {oc}" if "@" not in _clean_text(r.get(opp_col,"")) else f"{tc} @ {oc}"
        for side,col in [("Over",dk_over),("Under",dk_under)]:
            if not col:continue
            cell=_clean_text(r.get(col,""))
            price=_american(cell)
            # Some cells look like o75.5-116; recover threshold from that cell when available.
            cm=re.search(r"[ou]?\s*(\d+(?:\.\d+)?)\s*([+-]\d{2,4})",cell,re.I)
            th=cm.group(1) if cm else threshold
            if cm and not price:price=cm.group(2)
            if not price:continue
            rows.append({"event":event,"event_date":"","market":f"{player} {market_name}","line":f"{side} {th}","odds":price,"book":"DraftKings","source":"RotoWire public odds table"})
    return pd.DataFrame(rows).drop_duplicates() if rows else pd.DataFrame()


def _fetch_rotowire_props(sport: str) -> tuple[pd.DataFrame,dict]:
    url=ROTOWIRE_PROP_URLS[sport]
    try:
        r=_get(url);frames=[]
        for t in _tables_from_html(r.text):
            z=_parse_rotowire_table(t,sport)
            if not z.empty:frames.append(z)
        out=pd.concat(frames,ignore_index=True).drop_duplicates() if frames else pd.DataFrame(columns=["event","event_date","market","line","odds","book","source"])
        return out,{"source":"RotoWire public props","url":url,"rows":len(out),"ok":True}
    except Exception as exc:
        return pd.DataFrame(columns=["event","event_date","market","line","odds","book","source"]),{"source":"RotoWire public props","url":url,"rows":0,"ok":False,"error":str(exc)}


def fetch_public_props(sport: str) -> tuple[pd.DataFrame,list[dict]]:
    """Try multiple free public sources. Never invent rows.

    DraftKings Network is tried first because it exposes sportsbook-branded rows when its
    table is server-rendered. RotoWire is a fallback because its public comparison tables
    often remain visible when the DK Network tool is rendered client-side.
    """
    meta=[];frames=[]
    url=PROP_URLS[sport]
    try:
        r=_get(url);dk=[]
        for t in _tables_from_html(r.text):
            z=_normalize_dk_table(t,sport)
            if not z.empty:dk.append(z)
        dko=pd.concat(dk,ignore_index=True).drop_duplicates() if dk else pd.DataFrame()
        meta.append({"source":"DraftKings Network","url":url,"rows":len(dko),"ok":True})
        if not dko.empty:frames.append(dko)
    except Exception as exc:
        meta.append({"source":"DraftKings Network","url":url,"rows":0,"ok":False,"error":str(exc)})

    rw,rmeta=_fetch_rotowire_props(sport);meta.append(rmeta)
    if not rw.empty:frames.append(rw)
    if not frames:return pd.DataFrame(columns=["event","event_date","market","line","odds","book","source"]),meta
    out=pd.concat(frames,ignore_index=True).drop_duplicates(subset=["event","market","line","odds","book"])
    return out.reset_index(drop=True),meta

def american_to_prob(value) -> float | None:
    if value is None: return None
    s=str(value).replace("−","-").strip().lower()
    if s=="even": return .5
    m=re.search(r"([+-]?\d+)",s)
    if not m: return None
    a=int(m.group(1))
    if a==0: return None
    return 100/(a+100) if a>0 else (-a)/((-a)+100)
