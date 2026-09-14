import sqlite3
from contextlib import contextmanager
from config import DB_PATH

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    sport TEXT NOT NULL,
    game_id TEXT,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    line REAL,
    market_odds INTEGER,
    implied_probability REAL,
    model_probability REAL,
    edge REAL,
    confidence REAL,
    projection REAL,
    evidence_for TEXT,
    evidence_against TEXT,
    result TEXT
);

CREATE TABLE IF NOT EXISTS coach_history (
    sport TEXT NOT NULL,
    coach_name TEXT NOT NULL,
    role TEXT NOT NULL,
    team TEXT NOT NULL,
    season INTEGER NOT NULL,
    start_date TEXT,
    end_date TEXT,
    PRIMARY KEY (sport, coach_name, role, team, season)
);

CREATE TABLE IF NOT EXISTS games (
    sport TEXT NOT NULL,
    game_id TEXT NOT NULL,
    game_date TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_score INTEGER,
    away_score INTEGER,
    PRIMARY KEY (sport, game_id)
);

CREATE TABLE IF NOT EXISTS source_health (
    source_name TEXT PRIMARY KEY,
    last_success TEXT,
    last_failure TEXT,
    status TEXT,
    note TEXT
);
"""

@contextmanager
def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()

def init_db():
    with connect() as con:
        con.executescript(SCHEMA)
