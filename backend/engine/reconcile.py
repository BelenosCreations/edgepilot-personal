# Read-only broker reconciliation journal. Never infer order attribution from history.
# Transaction history records are NOT unique confirmed broker fills.
import json, sqlite3, hashlib
from datetime import datetime, timezone
from decimal import Decimal

def dec(v):
    x=Decimal(str(v));
    if not x.is_finite(): raise ValueError('non-finite')
    return x

def db(path):
    c=sqlite3.connect(path, timeout=30);c.row_factory=sqlite3.Row
    c.execute('PRAGMA busy_timeout=30000')
    return c

def setup(path):
    with db(path) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS sync_snapshots (
          id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT NOT NULL, ts TEXT NOT NULL,
          account_value TEXT NOT NULL, cash TEXT NOT NULL,
          positions_json TEXT NOT NULL, orders_json TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS sync_transactions (
          account TEXT NOT NULL, tx_id TEXT NOT NULL, timestamp TEXT NOT NULL,
          symbol TEXT, side TEXT, type TEXT, subtype TEXT,
          raw_json TEXT NOT NULL, first_seen TEXT NOT NULL,
          PRIMARY KEY(account, tx_id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS sync_alerts (
          id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT NOT NULL, kind TEXT NOT NULL,
          fingerprint TEXT NOT NULL, message TEXT NOT NULL, detail_json TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'OPEN', created TEXT NOT NULL,
          UNIQUE(account, fingerprint))''')
        c.execute('''CREATE TABLE IF NOT EXISTS sync_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT NOT NULL, ts TEXT NOT NULL,
          status TEXT NOT NULL, imported_count INTEGER NOT NULL, pages INTEGER NOT NULL,
          message TEXT NOT NULL)''')

def _alert(c, account, kind, fingerprint, message, detail, now):
    c.execute('INSERT OR IGNORE INTO sync_alerts(account,kind,fingerprint,message,detail_json,created) VALUES(?,?,?,?,?,?)',
             (account,kind,fingerprint,message,json.dumps(detail,sort_keys=True,default=str),now))

def _holdings(positions):
    out={}
    for p in positions:
        sym=str((p.get('instrument') or {}).get('symbol') or p.get('symbol') or '').strip()
        if sym:
            out[sym]=out.get(sym,Decimal(0))+dec(p.get('quantity') or '0')
    return out

def reconcile(path, account, portfolio, transactions, *, pages=1, complete=True):
    # Commit complete broker response only; uncertainty stays unclassified.
    if not complete: raise ValueError('Incomplete history pagination: no changes committed')
    if not isinstance(portfolio,dict) or not isinstance(transactions,list):raise ValueError('Invalid broker response')
    if 'positions' not in portfolio or 'orders' not in portfolio or 'totalAccountValue' not in portfolio:
        raise ValueError('Missing required portfolio fields; fail closed')
    if not isinstance(portfolio['positions'],list) or not isinstance(portfolio['orders'],list): raise ValueError('Malformed portfolio arrays')
    now=datetime.now(timezone.utc).isoformat()
    with db(path) as c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT positions_json,orders_json FROM sync_snapshots WHERE account=? ORDER BY id DESC LIMIT 1',(account,)).fetchone()
        previously=_holdings(json.loads(old['positions_json'])) if old else {}
        latest=_holdings(portfolio['positions'])
        # Do not classify sales as manual solely from position change. Could be corporate action,
        # fractional adjustment, transfers, split or async order settlement.
        for symbol,oldq in previously.items():
            newq=latest.get(symbol,Decimal('0'))
            if newq < oldq:
                signature=f'holding-decrease:{symbol}:{oldq}:{newq}:{now}'
                _alert(c,account,'POSITION_DECREASE',signature,
                       f'{symbol} holdings decreased from {oldq} to {newq}; review broker history before classifying.',
                       {'symbol':symbol,'before':str(oldq),'after':str(newq),'manualSaleConfirmed':False},now)
        new_count=0
        for t in transactions:
            if not isinstance(t,dict):raise ValueError('Malformed transaction')
            txid=str(t.get('id') or '').strip()
            if not txid: raise ValueError('Transaction missing stable broker ID; fail closed')
            raw=json.dumps(t,sort_keys=True,separators=(',',':'),default=str)
            oldtx=c.execute('SELECT raw_json FROM sync_transactions WHERE account=? AND tx_id=?',(account,txid)).fetchone()
            if oldtx:
                # Broker history can be amended. Do not silently overwrite previously seen data.
                if oldtx['raw_json'] != raw:
                    _alert(c,account,'CHANGED_TRANSACTION',f'changed-tx:{txid}',
                           f'Public transaction {txid} changed since earlier synchronization.',{'transactionId':txid},now)
                continue
            c.execute('''INSERT INTO sync_transactions(account,tx_id,timestamp,symbol,side,type,subtype,raw_json,first_seen)
                         VALUES(?,?,?,?,?,?,?,?,?)''',
                      (account,txid,str(t.get('timestamp') or ''),str(t.get('symbol') or ''),str(t.get('side') or ''),
                       str(t.get('type') or ''),str(t.get('subType') or ''),raw,now))
            new_count+=1
            # Trade in broker history has no order ID: never post as EdgePilot execution.
            # Surface for human classification only when attributable inventory is present,
            # and never treat cash deposit/withdrawal as a trading fill.
            if str(t.get('side') or '').upper()=='SELL' and str(t.get('type') or '').upper()=='TRADE':
                _alert(c,account,'UNATTRIBUTED_SELL',f'sell-tx:{txid}',
                       f'Sale of {t.get("symbol") or "unknown instrument"} detected in Public; origin unverified.',
                       {'transactionId':txid,'symbol':str(t.get('symbol') or ''),'source':'UNKNOWN','repurchaseAllowed':False},now)
        c.execute('''INSERT INTO sync_snapshots(account,ts,account_value,cash,positions_json,orders_json) VALUES(?,?,?,?,?,?)''',
                  (account,now,str(dec(portfolio['totalAccountValue'])),str(dec(portfolio.get('cash') or '0')),
                   json.dumps(portfolio['positions'],sort_keys=True),json.dumps(portfolio['orders'],sort_keys=True)))
        c.execute('INSERT INTO sync_runs(account,ts,status,imported_count,pages,message) VALUES(?,?,?,?,?,?)',
                 (account,now,'READ_ONLY_COMPLETE',new_count,pages,'Broker history captured; no attribution or fills inferred'))
        count=c.execute("SELECT count(*) FROM sync_alerts WHERE account=? AND state='OPEN'",(account,)).fetchone()[0]
    return {'status':'READ_ONLY_COMPLETE','importedTransactions':new_count,'pages':pages,
            'openAlerts':count,'attributionVerified':False,'liveTradingAvailable':False,
            'note':'Transactions collected; do not equate transaction history with individual confirmed execution IDs.'}

def overview(path,account):
    with db(path) as c:
        run=c.execute('SELECT * FROM sync_runs WHERE account=? ORDER BY id DESC LIMIT 1',(account,)).fetchone()
        alerts=c.execute("SELECT id,kind,message,detail_json,created FROM sync_alerts WHERE account=? AND state='OPEN' ORDER BY id DESC LIMIT 50",(account,)).fetchall()
        count=c.execute('SELECT count(*) FROM sync_transactions WHERE account=?',(account,)).fetchone()[0]
        return {'lastSync':dict(run) if run else None,'totalTransactionsCaptured':count,
                'alerts':[{'id':r['id'],'kind':r['kind'],'message':r['message'],'detail':json.loads(r['detail_json']),'created':r['created']} for r in alerts],
                'verifiedAttribution':False,'liveTradingAvailable':False}

def dismiss(path, account, alert_id):
    with db(path) as c:
        n=c.execute("UPDATE sync_alerts SET state='ACKNOWLEDGED' WHERE id=? AND account=? AND state='OPEN'",(alert_id,account)).rowcount
        return bool(n)
