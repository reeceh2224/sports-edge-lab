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

# Use the actual odds boards, not the matchup-trends pages. The matchup pages mix
# standings/ATS/O-U records with market values and were the source of the confusing table.
TEAM_URLS = {
    "MLB": "https://www.vegasinsider.com/mlb/odds/las-vegas/",
    "NFL": "https://www.vegasinsider.com/nfl/odds/las-vegas/",
}
PROP_URLS = {
    "MLB": "https://dknetwork.draftkings.com/draftkings-sportsbook-player-props/?tb_edate=today",
    "NFL": "https://dknetwork.draftkings.com/draftkings-sportsbook-player-props/?tb_edate=today",
}

MLB_TEAMS = [
    "Arizona Diamondbacks", "Athletics", "Atlanta Braves", "Baltimore Orioles", "Boston Red Sox",
    "Chicago Cubs", "Chicago White Sox", "Cincinnati Reds", "Cleveland Guardians", "Colorado Rockies",
    "Detroit Tigers", "Houston Astros", "Kansas City Royals", "Los Angeles Angels", "Los Angeles Dodgers",
    "Miami Marlins", "Milwaukee Brewers", "Minnesota Twins", "New York Mets", "New York Yankees",
    "Philadelphia Phillies", "Pittsburgh Pirates", "San Diego Padres", "San Francisco Giants", "Seattle Mariners",
    "St. Louis Cardinals", "Tampa Bay Rays", "Texas Rangers", "Toronto Blue Jays", "Washington Nationals",
]
NFL_TEAMS = [
    "Arizona Cardinals", "Atlanta Falcons", "Baltimore Ravens", "Buffalo Bills", "Carolina Panthers",
    "Chicago Bears", "Cincinnati Bengals", "Cleveland Browns", "Dallas Cowboys", "Denver Broncos",
    "Detroit Lions", "Green Bay Packers", "Houston Texans", "Indianapolis Colts", "Jacksonville Jaguars",
    "Kansas City Chiefs", "Las Vegas Raiders", "Los Angeles Chargers", "Los Angeles Rams", "Miami Dolphins",
    "Minnesota Vikings", "New England Patriots", "New Orleans Saints", "New York Giants", "New York Jets",
    "Philadelphia Eagles", "Pittsburgh Steelers", "San Francisco 49ers", "Seattle Seahawks", "Tampa Bay Buccaneers",
    "Tennessee Titans", "Washington Commanders",
]

ODDS_RE = re.compile(r"^(?:[+\-−]\d{2,4}|EVEN|even)$")


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
    if s.lower() == "even":
        return "+100"
    m = re.search(r"(?<!\d)([+-]\d{2,4})(?!\d)", s)
    return m.group(1) if m else None


def _team_from_cell(value: str, sport: str) -> str | None:
    s = _clean_text(value).lower()
    teams = MLB_TEAMS if sport == "MLB" else NFL_TEAMS
    # Longest first avoids "New York" style overlaps in any future aliases.
    for team in sorted(teams, key=len, reverse=True):
        if team.lower() in s:
            return team
    # VegasInsider often shortens some names. Keep a few safe aliases.
    aliases = {
        "diamondbacks": "Arizona Diamondbacks", "d-backs": "Arizona Diamondbacks",
        "dodgers": "Los Angeles Dodgers", "angels": "Los Angeles Angels", "athletics": "Athletics",
        "yankees": "New York Yankees", "mets": "New York Mets", "white sox": "Chicago White Sox",
        "red sox": "Boston Red Sox", "guardians": "Cleveland Guardians", "nationals": "Washington Nationals",
        "commanders": "Washington Commanders", "49ers": "San Francisco 49ers", "chiefs": "Kansas City Chiefs",
        "broncos": "Denver Broncos", "chargers": "Los Angeles Chargers", "rams": "Los Angeles Rams",
    }
    for k, v in aliases.items():
        if k in s:
            return v
    return None


def _find_col(columns: Iterable[str], *needles: str) -> str | None:
    for c in columns:
        lc = str(c).lower()
        if all(n.lower() in lc for n in needles):
            return c
    return None


def _clean_moneyline_table(t: pd.DataFrame, sport: str) -> pd.DataFrame:
    """Extract only actual team moneyline prices from a VegasInsider odds table.

    The old build dumped raw HTML tables, which included SU/O-U/ATS records and ad text.
    This deliberately rejects anything that is not a recognizable team + American price.
    """
    if t.empty or len(t.columns) < 2:
        return pd.DataFrame()

    cols = list(t.columns)
    team_col = cols[0]
    open_col = _find_col(cols, "open")
    dk_col = _find_col(cols, "draftkings")
    consensus_col = _find_col(cols, "consensus")

    # Some image-based headers can become Unnamed. Infer the likely DK column only if
    # the page clearly contains the word draftkings in a column label; otherwise leave blank.
    records = []
    for _, row in t.iterrows():
        team = _team_from_cell(row.get(team_col, ""), sport)
        if not team:
            continue
        open_price = _american(row.get(open_col, "")) if open_col else None
        dk_price = _american(row.get(dk_col, "")) if dk_col else None
        consensus = _american(row.get(consensus_col, "")) if consensus_col else None

        # A valid odds row must contain at least one actual American price.
        if not any([open_price, dk_price, consensus]):
            continue
        records.append({
            "team": team,
            "open": open_price,
            "draftkings": dk_price,
            "consensus": consensus,
        })

    if not records:
        return pd.DataFrame()

    out = pd.DataFrame(records).drop_duplicates(subset=["team", "open", "draftkings", "consensus"])
    # Pair sequential teams from the board into matchups. If the source order is odd,
    # individual team rows are still accurate and no matchup is fabricated.
    matchups = []
    for i in range(0, len(out), 2):
        pair = out.iloc[i:i+2]
        matchup = " @ ".join(pair["team"].tolist()) if len(pair) == 2 else pair.iloc[0]["team"]
        matchups.extend([matchup] * len(pair))
    out.insert(0, "matchup", matchups)
    return out.reset_index(drop=True)


def fetch_team_moneylines(sport: str) -> tuple[pd.DataFrame, dict]:
    url = TEAM_URLS[sport]
    r = _get(url)
    tables = _tables_from_html(r.text)
    cleaned = []
    for t in tables:
        c = _clean_moneyline_table(t, sport)
        if not c.empty:
            cleaned.append(c)
    if cleaned:
        out = pd.concat(cleaned, ignore_index=True).drop_duplicates()
    else:
        out = pd.DataFrame(columns=["matchup", "team", "open", "draftkings", "consensus"])
    return out, {
        "source": "VegasInsider odds board",
        "url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "rows": len(out),
    }


def _normalize_dk_table(t: pd.DataFrame, sport: str) -> pd.DataFrame:
    cols = {str(c).lower().strip(): c for c in t.columns}
    required = ["event", "event date", "market", "betslip line", "odds"]
    if not all(x in cols for x in required):
        return pd.DataFrame()
    out = pd.DataFrame({
        "event": t[cols["event"]].map(_clean_text),
        "event_date": t[cols["event date"]].map(_clean_text),
        "market": t[cols["market"]].map(_clean_text),
        "line": t[cols["betslip line"]].map(_clean_text),
        "odds": t[cols["odds"]].map(_clean_text),
    })
    out["odds"] = out["odds"].str.replace("−", "-", regex=False)
    out = out[out["odds"].str.match(r"^(?:[+-]\d{2,4}|even)$", case=False, na=False)]
    if sport == "MLB":
        mask = out["market"].str.contains(
            r"home runs?|hits?(?:\s|$)|total bases|runs? scored|rbi|strikeouts? thrown|stolen bases?|hits \+ runs \+ rbis",
            case=False, regex=True, na=False,
        )
    else:
        mask = out["market"].str.contains(
            r"passing|rushing|receiving|receptions|touchdowns?|anytime td|interceptions|completions|attempts",
            case=False, regex=True, na=False,
        )
    out = out[mask].copy()
    out["book"] = "DraftKings"
    out["source"] = "DraftKings Network"
    return out.drop_duplicates().reset_index(drop=True)


def fetch_public_props(sport: str) -> tuple[pd.DataFrame, list[dict]]:
    """Return only structured DraftKings Network rows.

    We intentionally removed the loose RotoWire table fallback because it was turning page
    headings/ads into fake prop rows. If a clean table is unavailable, the UI says unavailable.
    """
    url = PROP_URLS[sport]
    meta = []
    try:
        r = _get(url)
        tables = _tables_from_html(r.text)
        frames = []
        for t in tables:
            x = _normalize_dk_table(t, sport)
            if not x.empty:
                frames.append(x)
        if not frames:
            meta.append({"source": "DraftKings Network", "url": url, "rows": 0, "ok": True})
            return pd.DataFrame(columns=["event", "event_date", "market", "line", "odds", "book", "source"]), meta
        out = pd.concat(frames, ignore_index=True).drop_duplicates()
        meta.append({"source": "DraftKings Network", "url": url, "rows": len(out), "ok": True})
        return out, meta
    except Exception as exc:
        meta.append({"source": "DraftKings Network", "url": url, "rows": 0, "ok": False, "error": str(exc)})
        return pd.DataFrame(columns=["event", "event_date", "market", "line", "odds", "book", "source"]), meta


def american_to_prob(value) -> float | None:
    s = _clean_text(value).replace("−", "-")
    if s.lower() == "even":
        return 0.5
    try:
        o = float(re.sub(r"[^0-9.\-]", "", s))
    except Exception:
        return None
    if o == 0:
        return None
    return (-o) / ((-o) + 100) if o < 0 else 100 / (o + 100)
