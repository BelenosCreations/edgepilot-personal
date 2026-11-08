'''SQLite-backed, single-user accounting. Broker fills are the ONLY acceptable source
for ledger ingestion. Never infer executed trades from submitted orders or quotes.
This module has no ability to submit trades or transfer money.
'''
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone

def dec(v):
    x=Decimal(str(v))
    if not x.is_finite(): raise ValueError('Non-finite decimal')
    return x

def money(v): return str(dec(v).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

def open_db(path):
    c=sqlite3.connect(path,timeout=30)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA busy_timeout=30000')
    c.execute('PRAGMA foreign_keys=ON')
    return c

def setup(path):
    with open_db(path) as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('''CREATE TABLE IF NOT EXISTS broker_fills (
          id TEXT PRIMARY KEY, account TEXT NOT NULL, symbol TEXT NOT NULL,
          side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
          quantity TEXT NOT NULL, price TEXT NOT NULL, fee TEXT NOT NULL,
          source TEXT NOT NULL CHECK(source IN ('EDGEPILOT','EXTERNAL')),
          timestamp TEXT NOT NULL, recorded_at TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS attributed_positions (
          account TEXT NOT NULL, symbol TEXT NOT NULL, quantity TEXT NOT NULL,
          cost_basis TEXT NOT NULL, realized_pnl TEXT NOT NULL,
          PRIMARY KEY(account,symbol))''')
        c.execute('''CREATE TABLE IF NOT EXISTS interventions (
          id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT NOT NULL,
          symbol TEXT NOT NULL, fill_id TEXT NOT NULL UNIQUE,
          reason TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'AWAITING_DECISION',
          created_at TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS ledger_meta (
          k TEXT PRIMARY KEY, v TEXT NOT NULL)''')

def ingest_fill(path, *, fill_id, account, symbol, side, quantity, price, fee, source, timestamp):
    '''Exactly-once per broker execution ID, not per order ID.
    Only transactions attributable to EdgePilot holdings affect allocated P&L.
    An outside sale of an attributed holding creates a repurchase decision.
    Suspicious/unattributable sell quantities fail closed and roll back.
    '''
    if not all(isinstance(s,str) and 0<len(s)<=180 for s in (fill_id,account,symbol,timestamp)):
        raise ValueError('Invalid fill identifiers')
    if side not in ('BUY','SELL') or source not in ('EDGEPILOT','EXTERNAL'):raise ValueError('Invalid fill classification')
    q,p,f=dec(quantity),dec(price),dec(fee)
    if q<=0 or p<=0 or f<0:raise ValueError('Invalid fill values')
    if q>Decimal('1e12') or p>Decimal('1e12'):raise ValueError('Fill out of range')
    now=datetime.now(timezone.utc).isoformat()
    with open_db(path) as c:
        c.execute('BEGIN IMMEDIATE')
        prev=c.execute('SELECT * FROM broker_fills WHERE id=?',(fill_id,)).fetchone()
        if prev:
            # Deduplication must detect conflicting duplicate execution identifiers.
            expected=(account,symbol,side,str(q),str(p),str(f),source,timestamp)
            found=(prev['account'],prev['symbol'],prev['side'],prev['quantity'],prev['price'],prev['fee'],prev['source'],prev['timestamp'])
            if expected!=found:raise ValueError('Conflicting replay of broker fill ID')
            return {'duplicate':True}
        row=c.execute('SELECT * FROM attributed_positions WHERE account=? AND symbol=?',(account,symbol)).fetchone()
        old_q=dec(row['quantity']) if row else Decimal('0')
        cost=dec(row['cost_basis']) if row else Decimal('0')
        realized=dec(row['realized_pnl']) if row else Decimal('0')
        # Outside buys remain separate unless explicitly imported by a future attributed-lot workflow.
        attributed = source=='EDGEPILOT' or (side=='SELL' and old_q>0)
        if attributed and side=='BUY':
            new_q=old_q+q;new_cost=cost+q*p+f
        elif attributed and side=='SELL':
            if q>old_q:raise ValueError('Sell exceeds EdgePilot-attributed position; reconcile attribution manually')
            released=cost*q/old_q
            new_q=old_q-q;new_cost=cost-released
            realized+=(q*p-f-released)
            if new_q==0:new_cost=Decimal('0')
        else:new_q,new_cost=old_q,cost
        c.execute('''INSERT INTO broker_fills VALUES (?,?,?,?,?,?,?,?,?,?)''',
                  (fill_id,account,symbol,side,str(q),str(p),str(f),source,timestamp,now))
        if attributed:
            c.execute('''INSERT INTO attributed_positions(account,symbol,quantity,cost_basis,realized_pnl)
                         VALUES(?,?,?,?,?) ON CONFLICT(account,symbol) DO UPDATE SET
                         quantity=excluded.quantity,cost_basis=excluded.cost_basis,
                         realized_pnl=excluded.realized_pnl''',
                      (account,symbol,str(new_q),str(new_cost),str(realized)))
        prompted = source=='EXTERNAL' and side=='SELL' and attributed
        if prompted:
            c.execute('INSERT INTO interventions(account,symbol,fill_id,reason,created_at) VALUES(?,?,?,?,?)',
                      (account,symbol,fill_id,'Manual sale detected; choose repurchase policy',now))
        return {'duplicate':False,'attributed':attributed,'requires_repurchase_decision':prompted,
                'quantity':str(new_q),'realized_pnl':money(realized)}

def summary(path,account=None):
    with open_db(path) as c:
        if account:
            rows=c.execute('SELECT * FROM attributed_positions WHERE account=? ORDER BY symbol',(account,)).fetchall()
            actions=c.execute("SELECT * FROM interventions WHERE account=? AND state='AWAITING_DECISION' ORDER BY id DESC",(account,)).fetchall()
        else:
            rows=c.execute('SELECT * FROM attributed_positions ORDER BY account,symbol').fetchall()
            actions=c.execute("SELECT * FROM interventions WHERE state='AWAITING_DECISION' ORDER BY id DESC").fetchall()
        realized=sum((dec(r['realized_pnl']) for r in rows),Decimal('0'))
        invested=sum((dec(r['cost_basis']) for r in rows),Decimal('0'))
        return {'positions':[dict(r) for r in rows], 'pendingDecisions':[dict(r) for r in actions],
                'realizedPnl':money(realized),'openCostBasis':money(invested),
                'warning':'Broker fills have not been automatically imported. Ledger is incomplete until broker-execution reconciliation is implemented.'}
