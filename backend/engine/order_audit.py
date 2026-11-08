# Read-only order-to-fill evidence collector for Public; no trade submission.
# Orders require proven provenance for allocation; do not guess fees.
import sqlite3, json
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone

FINAL={'FILLED','CANCELLED','QUEUED_CANCELLED','REJECTED','EXPIRED','REPLACED'}
VALID={'NEW','PARTIALLY_FILLED','CANCELLED','QUEUED_CANCELLED','FILLED','REJECTED','PENDING_REPLACE','PENDING_CANCEL','EXPIRED','REPLACED'}

def dec(v):
    try:
        d=Decimal(str(v))
        if not d.is_finite():raise ValueError('non finite')
        return d
    except (InvalidOperation,ValueError,TypeError) as e:raise ValueError('Invalid numeric field') from e

def connection(path):
    c=sqlite3.connect(path,timeout=30); c.row_factory=sqlite3.Row
    c.execute('PRAGMA busy_timeout=30000')
    return c

def setup(path):
    with connection(path) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS observed_orders (
          account TEXT NOT NULL, order_id TEXT NOT NULL, status TEXT NOT NULL,
          side TEXT NOT NULL, symbol TEXT NOT NULL, created_at TEXT NOT NULL,
          filled_quantity TEXT NOT NULL, last_seen TEXT NOT NULL,
          origin TEXT NOT NULL DEFAULT 'UNVERIFIED', raw_json TEXT NOT NULL,
          PRIMARY KEY(account,order_id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS observed_trades (
          account TEXT NOT NULL, trade_id TEXT NOT NULL, order_id TEXT NOT NULL,
          symbol TEXT NOT NULL, side TEXT NOT NULL, quantity TEXT NOT NULL,
          price TEXT NOT NULL, timestamp TEXT NOT NULL,
          fees_status TEXT NOT NULL DEFAULT 'UNKNOWN',
          origin TEXT NOT NULL, raw_json TEXT NOT NULL,
          PRIMARY KEY(account,trade_id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS order_audit_alerts (
          id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT NOT NULL,
          fingerprint TEXT NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'OPEN', created TEXT NOT NULL,
          UNIQUE(account,fingerprint))''')
        c.execute('''CREATE TABLE IF NOT EXISTS order_audit_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT NOT NULL, ts TEXT NOT NULL,
          count_orders INTEGER NOT NULL, count_trades INTEGER NOT NULL,
          state TEXT NOT NULL, note TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS submitted_order_provenance (
          account TEXT NOT NULL, order_id TEXT NOT NULL, client_intent_id TEXT NOT NULL,
          created TEXT NOT NULL, PRIMARY KEY(account,order_id),
          UNIQUE(account,client_intent_id))''')

def _alert(c,account,key,kind,message,ts):
    c.execute('''INSERT OR IGNORE INTO order_audit_alerts
                 (account,fingerprint,kind,message,created) VALUES(?,?,?,?,?)''',
              (account,key,kind,message,ts))

def observe(path,account,orders,*,complete=True):
    if not complete:raise ValueError('Partial broker response is not safe to commit')
    if not account or not isinstance(orders,list):raise ValueError('Invalid account / order results')
    ts=datetime.now(timezone.utc).isoformat()
    seen_orders=set();seen_trades=set(); parsed=[]
    for order in orders:
        if not isinstance(order,dict):raise ValueError('Malformed order response')
        oid=str(order.get('orderId') or '').strip()
        status=str(order.get('status') or '').upper()
        side=str(order.get('side') or '').upper()
        symbol=str((order.get('instrument') or {}).get('symbol') or '').strip()
        if not oid or oid in seen_orders or status not in VALID or side not in ('BUY','SELL') or not symbol:
            raise ValueError('Incomplete/duplicated broker order: no changes committed')
        seen_orders.add(oid)
        fq=dec(order.get('filledQuantity') or '0')
        if fq<0:raise ValueError('Negative filled quantity')
        trades=order.get('trades') or []
        if not isinstance(trades,list):raise ValueError('Malformed trades array')
        computed=Decimal('0'); normalized=[]
        for trade in trades:
            if not isinstance(trade,dict):raise ValueError('Malformed trade')
            tid=str(trade.get('tradeId') or '').strip()
            q=dec(trade.get('quantity'));price=dec(trade.get('price'))
            sym=str((trade.get('instrument') or {}).get('symbol') or symbol).strip()
            sd=str(trade.get('side') or side).upper()
            stamp=str(trade.get('timestamp') or '').strip()
            if not tid or tid in seen_trades or q<=0 or price<=0 or sym!=symbol or sd!=side or not stamp:
                raise ValueError('Conflicting, duplicate, or incomplete trade: no changes committed')
            seen_trades.add(tid);computed+=q
            normalized.append((tid,q,price,stamp,trade))
        # Broker may report cumulative fills before the trade array catches up.
        if computed>fq:raise ValueError('Trades exceed cumulative filled quantity; fail closed')
        parsed.append((oid,status,side,symbol,fq,order,normalized,computed))
    # Atomically update after ALL orders validated. Old trades never disappear on a later poll.
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        new_trades=0
        for oid,status,side,symbol,fq,order,trades,computed in parsed:
            prior=c.execute('SELECT * FROM observed_orders WHERE account=? AND order_id=?',(account,oid)).fetchone()
            origin='EDGEPILOT' if c.execute('SELECT 1 FROM submitted_order_provenance WHERE account=? AND order_id=?',(account,oid)).fetchone() else 'UNVERIFIED'
            if prior:
                if prior['symbol']!=symbol or prior['side']!=side or fq<dec(prior['filled_quantity']):
                    raise ValueError('Order identity / cumulative quantity changed: rollback')
                if prior['status'] in FINAL and status!=prior['status']:
                    _alert(c,account,'changed-order:'+oid,'CHANGED_ORDER',f'Order {oid} changed terminal status; requires review',ts)
                    raise ValueError('Terminal order mutated: rollback')
            c.execute('''INSERT INTO observed_orders
              (account,order_id,status,side,symbol,created_at,filled_quantity,last_seen,origin,raw_json)
              VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(account,order_id) DO UPDATE SET
              status=excluded.status,filled_quantity=excluded.filled_quantity,
              last_seen=excluded.last_seen,origin=excluded.origin,raw_json=excluded.raw_json''',
              (account,oid,status,side,symbol,str(order.get('createdAt') or ''),str(fq),ts,origin,json.dumps(order,sort_keys=True)))
            if computed<fq:
                _alert(c,account,'pending-trade-details:'+oid,'INCOMPLETE_TRADES',
                    f'Order {oid} has filled quantity but incomplete trade details; no ledger posting.',ts)
            for tid,q,price,stamp,t in trades:
                raw=json.dumps(t,sort_keys=True)
                prev=c.execute('SELECT * FROM observed_trades WHERE account=? AND trade_id=?',(account,tid)).fetchone()
                if prev:
                    if (prev['order_id'],prev['quantity'],prev['price'],prev['symbol'],prev['side'],prev['timestamp'])!=(oid,str(q),str(price),symbol,side,stamp):
                        raise ValueError('Trade ID conflict: rollback')
                    continue
                c.execute('''INSERT INTO observed_trades
                  (account,trade_id,order_id,symbol,side,quantity,price,timestamp,origin,raw_json)
                  VALUES(?,?,?,?,?,?,?,?,?,?)''',(account,tid,oid,symbol,side,str(q),str(price),stamp,origin,raw))
                new_trades+=1
                if origin!='EDGEPILOT':
                    _alert(c,account,'external-trade:'+tid,'UNATTRIBUTED_EXECUTION',
                        f'Broker execution {tid} is not proven to originate in EdgePilot; attribution withheld.',ts)
                else:
                    _alert(c,account,'fee-pending:'+tid,'FEES_UNVERIFIED',
                        f'EdgePilot order execution {tid} confirmed; actual fees not yet deterministically matched. Ledger posting held.',ts)
        c.execute('INSERT INTO order_audit_runs(account,ts,count_orders,count_trades,state,note) VALUES(?,?,?,?,?,?)',
                  (account,ts,len(parsed),new_trades,'READ_ONLY','No fills automatically attributed or posted to monetary ledger'))
    return {'ordersObserved':len(parsed),'newTrades':new_trades,'liveTradingAvailable':False,
            'pnlVerified':False,'status':'READ_ONLY','message':'Confirmed trade IDs saved. Fee matching and provenance verification remain mandatory before P&L posting.'}

def overview(path,account):
    with connection(path) as c:
        run=c.execute('SELECT * FROM order_audit_runs WHERE account=? ORDER BY id DESC LIMIT 1',(account,)).fetchone()
        orders=c.execute('SELECT order_id,status,symbol,side,filled_quantity,origin,last_seen FROM observed_orders WHERE account=? ORDER BY last_seen DESC LIMIT 100',(account,)).fetchall()
        trades=c.execute('SELECT trade_id,order_id,symbol,side,quantity,price,fees_status,origin,timestamp FROM observed_trades WHERE account=? ORDER BY timestamp DESC LIMIT 200',(account,)).fetchall()
        alerts=c.execute("SELECT kind,message,created FROM order_audit_alerts WHERE account=? AND state='OPEN' ORDER BY id DESC LIMIT 30",(account,)).fetchall()
    return {'lastRun':dict(run) if run else None,'orders':[dict(r) for r in orders],
            'trades':[dict(r) for r in trades],'alerts':[dict(r) for r in alerts],
            'ledgerPostingEnabled':False,'liveTradingAvailable':False}
