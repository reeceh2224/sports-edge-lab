from __future__ import annotations

from io import StringIO
from datetime import datetime, timezone
import re
import pandas as pd
import requests

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1',
    'Accept-Language': 'en-US,en;q=0.9',
}

TEAM_URLS = {
    'MLB': 'https://www.vegasinsider.com/mlb/matchups/',
    'NFL': 'https://www.vegasinsider.com/nfl/matchups/',
}
PROP_URLS = {
    'MLB': [
        'https://dknetwork.draftkings.com/draftkings-sportsbook-player-props/',
        'https://www.rotowire.com/betting/mlb/player-props.php',
    ],
    'NFL': [
        'https://dknetwork.draftkings.com/draftkings-sportsbook-player-props/',
        'https://www.rotowire.com/betting/nfl/player-props.php',
    ],
}


def _get(url: str, timeout: int = 20) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def _flatten_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [' '.join(str(x) for x in c if str(x) != 'nan').strip() for c in out.columns]
    else:
        out.columns = [str(c).strip() for c in out.columns]
    return out


def _tables_from_html(html: str) -> list[pd.DataFrame]:
    try:
        return [_flatten_cols(t) for t in pd.read_html(StringIO(html))]
    except Exception:
        return []


def fetch_team_market_tables(sport: str) -> tuple[list[pd.DataFrame], dict]:
    url = TEAM_URLS[sport]
    r = _get(url)
    tables = _tables_from_html(r.text)
    useful = []
    for t in tables:
        text = ' '.join(map(str, t.columns)).lower() + ' ' + ' '.join(t.astype(str).head(5).fillna('').agg(' '.join, axis=1).tolist()).lower()
        if any(k in text for k in ['moneyline','spread','runline','total','consensus','open']):
            useful.append(t)
    return useful or tables[:8], {
        'source': 'VegasInsider', 'url': url, 'fetched_at': datetime.now(timezone.utc).isoformat(),
        'tables': len(tables), 'usable_tables': len(useful),
    }


def _normalize_dk_table(t: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower().strip(): c for c in t.columns}
    required = ['event','event date','market','betslip line','odds']
    if not all(x in cols for x in required):
        return pd.DataFrame()
    out = pd.DataFrame({
        'event': t[cols['event']].astype(str),
        'event_date': t[cols['event date']].astype(str),
        'market': t[cols['market']].astype(str),
        'line': t[cols['betslip line']].astype(str),
        'odds': t[cols['odds']].astype(str),
    })
    out['book'] = 'DraftKings'
    out['source'] = 'DraftKings Network'
    return out


def _looks_like_prop_table(t: pd.DataFrame) -> bool:
    text = ' '.join(map(str, t.columns)).lower()
    return any(k in text for k in ['draftkings','player','team','opp','prop','odds','anytime td','receptions','yards'])


def fetch_public_props(sport: str) -> tuple[pd.DataFrame, list[dict]]:
    frames = []
    meta = []
    for url in PROP_URLS[sport]:
        try:
            r = _get(url, 25)
            tables = _tables_from_html(r.text)
            got = 0
            for t in tables:
                dk = _normalize_dk_table(t)
                if not dk.empty:
                    # DraftKings Network page mixes sports. Keep rows that look relevant to this sport when possible.
                    if sport == 'MLB':
                        mask = dk['market'].str.contains('home run|hit|base|rbi|run|strikeout', case=False, regex=True, na=False)
                    else:
                        mask = dk['market'].str.contains('pass|rush|receiv|reception|touchdown|td|tackle|field goal', case=False, regex=True, na=False)
                    dk = dk[mask]
                    if not dk.empty:
                        frames.append(dk)
                        got += len(dk)
                elif 'rotowire.com' in url and _looks_like_prop_table(t):
                    raw = t.copy()
                    raw.columns = [str(c) for c in raw.columns]
                    raw['source'] = 'RotoWire'
                    raw['book'] = 'Multiple books'
                    raw['event'] = ''
                    raw['event_date'] = ''
                    raw['market'] = raw.columns[-3] if len(raw.columns) >= 3 else 'Player prop'
                    raw['line'] = ''
                    raw['odds'] = ''
                    keep = ['event','event_date','market','line','odds','book','source']
                    frames.append(raw[keep].head(200))
                    got += min(len(raw), 200)
            meta.append({'source': 'DraftKings Network' if 'dknetwork' in url else 'RotoWire', 'url': url, 'rows': got, 'ok': True})
        except Exception as exc:
            meta.append({'source': 'DraftKings Network' if 'dknetwork' in url else 'RotoWire', 'url': url, 'rows': 0, 'ok': False, 'error': str(exc)})
    if not frames:
        return pd.DataFrame(columns=['event','event_date','market','line','odds','book','source']), meta
    out = pd.concat(frames, ignore_index=True).drop_duplicates()
    return out, meta


def american_to_prob(value):
    try:
        s = str(value).replace('−','-').replace('+','').strip()
        o = float(re.sub(r'[^0-9.\-]', '', s))
    except Exception:
        return None
    if o == 0: return None
    return (-o)/((-o)+100) if o < 0 else 100/(o+100)


def prop_interest_score(row: pd.Series) -> float:
    """Transparent heuristic for sorting public props when a full statistical model is unavailable.
    This is not presented as a win probability.
    """
    p = american_to_prob(row.get('odds'))
    score = 0.0
    if p is not None:
        # Prefer normal, bettable price ranges over extreme longshots or huge juice.
        score += max(0.0, 1.0 - abs(p - 0.50) * 2.2)
    market = str(row.get('market','')).lower()
    if any(k in market for k in ['strikeout','total bases','hits','receiving yards','rushing yards','passing yards','receptions']):
        score += 0.35
    if any(k in market for k in ['home run','first td','3+ td']):
        score -= 0.15
    return round(score, 3)


def rank_public_props(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    d = df.copy()
    d['interest_score'] = d.apply(prop_interest_score, axis=1)
    return d.sort_values(['interest_score','event'], ascending=[False, True]).reset_index(drop=True)
