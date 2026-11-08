"""Read-only Public daily equity history with strict validation and SQLite cache.

Caches broker-provided OHLC rows, never artificial/synthetic prices. Research only.
"""
import json, re, math, sqlite3
from datetime import date, datetime, timezone, timedelta
from urllib.parse import quote

SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")
PERIODS = {"YEAR", "FIVE_YEARS", "TEN_YEARS", "ALL"}
AGGREGATION = "ONE_DAY"
MAX_BARS = 5000

def setup(db_path):
    with sqlite3.connect(db_path) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS public_history_cache
          (symbol TEXT NOT NULL, period TEXT NOT NULL, fetched_at TEXT NOT NULL,
           history_json TEXT NOT NULL, PRIMARY KEY(symbol,period))""")

def clean_symbol(symbol):
    if not isinstance(symbol,str) or not SYMBOL.fullmatch(symbol.strip().upper()):
        raise ValueError('Provide a valid equity ticker (1–15 characters)')
    return symbol.strip().upper()

def normalize(payload):
    if not isinstance(payload,dict): raise ValueError('Broker history response must be an object')
    section=payload.get('regularMarket')
    if not isinstance(section,dict) or not isinstance(section.get('bars'),list):
        raise ValueError('Public returned no regular-market daily bar series')
    raw=section['bars']
    if len(raw)>MAX_BARS: raise ValueError('Too many history bars')
    if len(raw)<50: raise ValueError('Fewer than 50 regular-market daily bars; cannot backtest')
    bars=[];previous=None
    for row in raw:
        if not isinstance(row,dict):raise ValueError('Malformed historical bar')
        stamp=row.get('timestamp')
        if not isinstance(stamp,str):raise ValueError('Historical bar is missing its timestamp')
        try:
            # ISO-8601 timestamp from the broker: convert to local calendar date as represented by broker.
            d=date.fromisoformat(stamp[:10]); o=float(row.get('open'));c=float(row.get('close'))
            high=float(row['high']) if row.get('high') not in (None,'') else None
            low=float(row['low']) if row.get('low') not in (None,'') else None
            vol=float(row['volume']) if row.get('volume') not in (None,'') else None
        except (ValueError,TypeError,OverflowError,KeyError):raise ValueError('Invalid price or date in Public bar')
        if d>datetime.now(timezone.utc).date()+timedelta(days=1):raise ValueError('Future bar timestamp')
        if any(not math.isfinite(v) for v in (o,c,*([high] if high is not None else []),*([low] if low is not None else []),*([vol] if vol is not None else []))):raise ValueError('Non-finite historical price/volume')
        if o<=0 or c<=0 or (high is not None and high<max(o,c)) or (low is not None and low>min(o,c)) or (high is not None and low is not None and low>high) or (vol is not None and vol<0):raise ValueError('Invalid OHLCV data')
        if previous is not None and d<=previous:raise ValueError('Historical data unsorted or duplicated')
        bars.append({'date':d.isoformat(),'open':o,'close':c,'high':high,'low':low,'volume':vol})
        previous=d
    return bars

def fetch_history(db_path, pub, symbol, period='YEAR', refresh=False, ttl_seconds=21600):
    symbol=clean_symbol(symbol)
    if period not in PERIODS: raise ValueError('Unsupported history period')
    now=datetime.now(timezone.utc)
    with sqlite3.connect(db_path) as c:
        if not refresh:
            row=c.execute('SELECT fetched_at,history_json FROM public_history_cache WHERE symbol=? AND period=?',(symbol,period)).fetchone()
            if row:
                ts=datetime.fromisoformat(row[0]); age=(now-ts).total_seconds()
                if 0<=age<=ttl_seconds:
                    bars=json.loads(row[1]); return {'symbol':symbol,'period':period,'bars':bars,'fetchedAt':row[0],'cacheHit':True}
    path='/userapigateway/historicdata/EQUITY/'+quote(symbol,safe='')+'/'+period+'/ONE_DAY?tradingSessionToggle=REGULAR_HOURS'
    data=pub('GET',path)
    returned=data.get('symbol') if isinstance(data,dict) else None
    if returned and str(returned).upper()!=symbol:raise ValueError('Broker history symbol mismatch')
    bars=normalize(data)
    with sqlite3.connect(db_path) as c:
        c.execute('INSERT OR REPLACE INTO public_history_cache(symbol,period,fetched_at,history_json) VALUES (?,?,?,?)', (symbol,period,now.isoformat(),json.dumps(bars,separators=(',',':'))))
    return {'symbol':symbol,'period':period,'bars':bars,'fetchedAt':now.isoformat(),'cacheHit':False}
