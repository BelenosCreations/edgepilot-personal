"""Persisted, read-only market observation diagnostics for EdgePilot.

A worker heartbeat proves only that a poller is alive. This journal separately
records completed scan attempts and verified broker quote outcomes. No broker
credentials, account identifiers, order commands or money movements are stored.
"""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

STATES={'OK','PARTIAL','NO_DATA','MARKET_CLOSED','CALENDAR_UNKNOWN','ERROR'}
SESSIONS={'OPEN','CLOSED','UNKNOWN','NOT_APPLICABLE'}
MODES={'observe','paper'}
MAX_RECENT=200


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def _db(path):
    con=sqlite3.connect(str(path),timeout=30)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA busy_timeout=30000')
    return con


def setup(path):
    with _db(path) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS observation_cycles(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            completed_at TEXT NOT NULL,
            mode TEXT NOT NULL,
            state TEXT NOT NULL,
            market_session TEXT NOT NULL,
            symbols_json TEXT NOT NULL,
            quotes_accepted INTEGER NOT NULL,
            quotes_rejected INTEGER NOT NULL,
            quote_age_seconds INTEGER,
            issue TEXT)""")
        con.execute('CREATE INDEX IF NOT EXISTS idx_observation_cycles_time ON observation_cycles(completed_at)')


def record_cycle(path,*,mode,state,market_session='NOT_APPLICABLE',symbols=(),
                 accepted=0,rejected=0,quote_age_seconds=None,issue=None):
    if mode not in MODES or state not in STATES or market_session not in SESSIONS:
        raise ValueError('Invalid observation cycle metadata')
    if not isinstance(accepted,int) or isinstance(accepted,bool) or accepted<0:
        raise ValueError('Invalid accepted quote count')
    if not isinstance(rejected,int) or isinstance(rejected,bool) or rejected<0:
        raise ValueError('Invalid rejected quote count')
    if quote_age_seconds is not None:
        if not isinstance(quote_age_seconds,int) or not 0<=quote_age_seconds<=86400:
            raise ValueError('Invalid quote age')
    unique=list(dict.fromkeys(symbols))
    if len(unique)>10 or any(not isinstance(x,str) or not x.isascii() or
                             len(x)>15 or not x or not all(c.isalnum() or c in '.-' for c in x)
                             for x in unique):
        raise ValueError('Invalid observation symbol metadata')
    note=str(issue)[:160] if issue else None
    with _db(path) as con:
        con.execute('BEGIN IMMEDIATE')
        con.execute("""INSERT INTO observation_cycles
            (completed_at,mode,state,market_session,symbols_json,
             quotes_accepted,quotes_rejected,quote_age_seconds,issue)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (utc_now(),mode,state,market_session,json.dumps(unique),accepted,
             rejected,quote_age_seconds,note))
        con.execute("""DELETE FROM observation_cycles WHERE id NOT IN
            (SELECT id FROM observation_cycles ORDER BY id DESC LIMIT ?)""",(MAX_RECENT,))


def report(path):
    with _db(path) as con:
        latest=con.execute('SELECT * FROM observation_cycles ORDER BY id DESC LIMIT 1').fetchone()
        success=con.execute("""SELECT completed_at FROM observation_cycles
            WHERE quotes_accepted>0 ORDER BY id DESC LIMIT 1""").fetchone()
        after=(datetime.now(timezone.utc)-timedelta(hours=24)).isoformat()
        recent=con.execute("""SELECT COUNT(*) AS cycles,
           COALESCE(SUM(quotes_accepted),0) AS accepted,
           COALESCE(SUM(quotes_rejected),0) AS rejected,
           COALESCE(SUM(CASE WHEN quotes_accepted>0 THEN 1 ELSE 0 END),0) AS with_quotes
           FROM observation_cycles WHERE completed_at>=?""",(after,)).fetchone()
    if latest:
        symbols=json.loads(latest['symbols_json'])
        cycle={'completedAt':latest['completed_at'],'mode':latest['mode'],
               'state':latest['state'],'marketSession':latest['market_session'],
               'symbols':symbols,'quotesAccepted':latest['quotes_accepted'],
               'quotesRejected':latest['quotes_rejected'],
               'quoteAgeSeconds':latest['quote_age_seconds'],'issue':latest['issue']}
    else:
        cycle=None
    return {'lastCycle':cycle,
            'lastSuccessfulScanAt':success['completed_at'] if success else None,
            'last24h':{'cycles':recent['cycles'],'cyclesWithVerifiedQuotes':recent['with_quotes'],
                       'quotesAccepted':recent['accepted'],'quotesRejected':recent['rejected']},
            'scope':'Read-only verified Public equity quotes per worker cycle; paper results not broker fills',
            'note':'Heartbeat only confirms worker activity. Last successful scan requires a validated quote; after-hours quote data does not mean the stock session is open.'}
