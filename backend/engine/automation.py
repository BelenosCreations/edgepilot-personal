"""EdgePilot v0.2: persisted, fail-closed, paper-only automation/risk ledger.

No broker trade route, bank transfer, or third-party AI call is present.
Paper positions are simulated at quoted ask/bid (plus assumed costs); no fills,
settlements, profit, or liquidity are guaranteed. Engine state persists in SQLite
and all spend/position transitions use a single BEGIN IMMEDIATE transaction.
"""
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from . import engine_config

ENGINES=('auto','micro','fifteen')
LEVELS={
    'conservative':{'riskPct':'0.25','rollingLossPct':'1.00','drawdownPct':'5.00','maxExposurePct':'25.00'},
    'balanced':{'riskPct':'0.50','rollingLossPct':'2.00','drawdownPct':'8.00','maxExposurePct':'50.00'},
    'aggressive':{'riskPct':'1.00','rollingLossPct':'3.00','drawdownPct':'12.00','maxExposurePct':'75.00'}
}
MONEY=Decimal('0.01')
MAX_BALANCE=Decimal('100000000.00')


def now():
    return datetime.now(timezone.utc).isoformat()


def dec(value):
    try:
        result=Decimal(str(value))
        if result.is_finite():
            return result
    except (InvalidOperation,TypeError,ValueError):
        pass
    raise ValueError('A finite decimal amount is required')


def cash(value):
    return str(dec(value).quantize(MONEY,rounding=ROUND_DOWN))


def db(path):
    con=sqlite3.connect(path,timeout=30)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA busy_timeout=30000')
    con.execute('PRAGMA foreign_keys=ON')
    return con


def setup(path):
    with db(path) as con:
        con.execute('''CREATE TABLE IF NOT EXISTS automation_master(
            id INTEGER PRIMARY KEY CHECK(id=1),
            mode TEXT NOT NULL, enabled INTEGER NOT NULL, emergency INTEGER NOT NULL,
            risk_level TEXT NOT NULL, paper_capital TEXT NOT NULL,
            protected_pct TEXT NOT NULL, profit_lock_pct TEXT NOT NULL,
            compound_pct TEXT NOT NULL, reserve_profit_pct TEXT NOT NULL,
            worker_heartbeat TEXT, last_error TEXT, updated_at TEXT NOT NULL)''')
        con.execute('''INSERT OR IGNORE INTO automation_master
            (id,mode,enabled,emergency,risk_level,paper_capital,protected_pct,
             profit_lock_pct,compound_pct,reserve_profit_pct,updated_at)
             VALUES(1,'observe',0,0,'balanced','0.00','50.00','0.00',
                    '0.00','0.00',?)''',(now(),))
        con.execute('''CREATE TABLE IF NOT EXISTS automation_engines(
            engine TEXT PRIMARY KEY, state TEXT NOT NULL, reason TEXT NOT NULL,
            updated_at TEXT NOT NULL, last_signal_at TEXT)''')
        fields={r['name'] for r in con.execute('PRAGMA table_info(automation_engines)')}
        for column in ('session_started_at','risk_reset_at'):
            if column not in fields:
                con.execute('ALTER TABLE automation_engines ADD COLUMN '+column+' TEXT')
        for engine in ENGINES:
            con.execute('''INSERT OR IGNORE INTO automation_engines
                (engine,state,reason,updated_at) VALUES(?,'stopped','',?)''',(engine,now()))
        con.execute('''CREATE TABLE IF NOT EXISTS paper_positions(
            id TEXT PRIMARY KEY, engine TEXT NOT NULL, asset_class TEXT NOT NULL,
            symbol TEXT NOT NULL, strategy TEXT NOT NULL, qty TEXT NOT NULL,
            entry_ask TEXT NOT NULL, entry_fee TEXT NOT NULL, opened_at TEXT NOT NULL,
            last_bid TEXT NOT NULL, last_ask TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('OPEN','CLOSED')),
            exit_bid TEXT, exit_fee TEXT, closed_at TEXT, realized_net TEXT,
            close_reason TEXT)''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_paper_open ON paper_positions(status,engine,symbol)')
        con.execute('''CREATE TABLE IF NOT EXISTS automation_quotes(
            id INTEGER PRIMARY KEY AUTOINCREMENT, engine TEXT NOT NULL,
            symbol TEXT NOT NULL, asset_class TEXT NOT NULL,
            captured_at TEXT NOT NULL, bid TEXT NOT NULL, ask TEXT NOT NULL,
            provider_timestamp TEXT NOT NULL)''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_quotes ON automation_quotes(engine,symbol,id)')
        con.execute('''CREATE TABLE IF NOT EXISTS automation_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, engine TEXT,
            event TEXT NOT NULL, details TEXT NOT NULL)''')
        con.execute('''CREATE TABLE IF NOT EXISTS automation_highwater(
            id INTEGER PRIMARY KEY CHECK(id=1), peak_equity TEXT NOT NULL)''')
        con.execute("INSERT OR IGNORE INTO automation_highwater(id,peak_equity) VALUES(1,'0.00')")
        con.execute('''CREATE TABLE IF NOT EXISTS automation_worker_lease(
            id INTEGER PRIMARY KEY CHECK(id=1), worker_id TEXT NOT NULL, expires_at TEXT NOT NULL)''')


def event(con, engine, kind, detail):
    con.execute('''INSERT INTO automation_events(ts,engine,event,details) VALUES(?,?,?,?)''',
                (now(),engine,kind,str(detail)[:300]))


def master(path):
    with db(path) as con:
        return dict(con.execute('SELECT * FROM automation_master WHERE id=1').fetchone())


def configure(path, data):
    """Changes never auto-start engines and may not arm live orders."""
    if not isinstance(data,dict) or set(data)!={'mode','risk_level','paper_capital',
             'protected_pct','profit_lock_pct','compound_pct','reserve_profit_pct'}:
        raise ValueError('Provide the complete known master settings')
    mode=data['mode']
    if mode not in ('observe','paper'):
        raise ValueError('Live mode unavailable until independently audited execution safety')
    level=data['risk_level']
    if level not in LEVELS:
        raise ValueError('Choose a supported risk level')
    values={}
    for key in ('paper_capital','protected_pct','profit_lock_pct','compound_pct','reserve_profit_pct'):
        v=dec(data[key])
        limit=MAX_BALANCE if key=='paper_capital' else Decimal('99')
        if v<0 or v>limit or v!=v.quantize(MONEY):
            raise ValueError(key+' must be within range and have at most two decimals')
        values[key]=cash(v)
    if dec(values['compound_pct'])+dec(values['reserve_profit_pct'])>100:
        raise ValueError('Compound and reserve percentages cannot exceed 100%')
    with db(path) as con:
        con.execute('BEGIN IMMEDIATE')
        old=con.execute('SELECT * FROM automation_master WHERE id=1').fetchone()
        if old['mode']!=mode and old['enabled']:
            raise ValueError('Stop all engines before switching Observe and Paper modes')
        position_count=con.execute('SELECT COUNT(*) AS n FROM paper_positions').fetchone()['n']
        if position_count and values['paper_capital']!=old['paper_capital']:
            raise ValueError('Cannot change paper starting capital after trades exist; historical performance must remain comparable')
        open_count=con.execute("SELECT COUNT(*) AS n FROM paper_positions WHERE status='OPEN'").fetchone()['n']
        if open_count and old['mode']!=mode:
            raise ValueError('Close existing paper positions before switching Observe and Paper modes')
        con.execute('''UPDATE automation_master SET mode=?,risk_level=?,paper_capital=?,
          protected_pct=?,profit_lock_pct=?,compound_pct=?,reserve_profit_pct=?,updated_at=?
          WHERE id=1''',(mode,level,values['paper_capital'],values['protected_pct'],
                         values['profit_lock_pct'],values['compound_pct'],
                         values['reserve_profit_pct'],now()))
        event(con,None,'CONFIG_UPDATED','Master limits saved, no automatic activation')
    return status(path)


def _set_engine(con,engine,state,reason):
    con.execute('''UPDATE automation_engines SET state=?,reason=?,updated_at=?
        WHERE engine=?''',(state,reason,now(),engine))
    event(con,engine,state.upper(),reason)


def control(path,action,engine=None):
    if action not in ('start','pause','stop','reset_emergency','emergency'):
        raise ValueError('Unsupported automation control')
    if engine is not None and engine not in ENGINES:
        raise ValueError('Unknown trading engine')
    if action in ('start','pause','stop') and engine is None:
        raise ValueError('Choose an engine')
    with db(path) as con:
        con.execute('BEGIN IMMEDIATE')
        m=con.execute('SELECT * FROM automation_master WHERE id=1').fetchone()
        if action=='emergency':
            con.execute('''UPDATE automation_master SET emergency=1,enabled=0,updated_at=? WHERE id=1''',(now(),))
            for e in ENGINES:
                _set_engine(con,e,'paused','Global Emergency Stop; manual reset required')
            event(con,None,'EMERGENCY','New paper entries and market scanning halted; no broker orders were canceled')
        elif action=='reset_emergency':
            if not m['emergency']:
                raise ValueError('Emergency Stop is not active')
            con.execute('UPDATE automation_master SET emergency=0,updated_at=? WHERE id=1',(now(),))
            event(con,None,'EMERGENCY_RESET','Engines remain paused; each needs manual restart')
        elif action=='start':
            if m['emergency']:
                raise ValueError('Global Emergency Stop must be reset first')
            if dec(m['paper_capital'])<=0 and m['mode']=='paper':
                raise ValueError('Configure a positive virtual paper balance first')

            if m['mode']=='paper' and engine=='fifteen':
                raise ValueError('15-minute settlement-safe paper execution is not yet validated; Observe mode only')
            config=engine_config.read(path,engine)
            if m['mode']=='paper' and not config['configured']:
                raise ValueError('Save this engine plan before starting paper automation')

            if m['mode']=='paper' and engine=='auto' and not config['config']['stock_market']:
                raise ValueError('Automated crypto paper orders are not yet implemented; enable stock/ETF observation first')
            if m['mode']=='paper' and engine in ('auto','micro'):
                c=config['config']
                allocation=dec(c['stock_allocation']) if engine=='auto' else dec(c['allocation'])
                if allocation<=0 or dec(c['max_per_trade'])<=0:
                    raise ValueError('Set a positive equity allocation and per-trade limit before paper trading')
            previous=con.execute('SELECT state,reason,session_started_at FROM automation_engines WHERE engine=?',(engine,)).fetchone()
            open_positions=con.execute("SELECT COUNT(*) AS n FROM paper_positions WHERE engine=? AND status='OPEN'",(engine,)).fetchone()['n']
            if engine in ('micro','fifteen') and (previous['state']=='stopped' or not previous['session_started_at']) and not open_positions:
                con.execute('UPDATE automation_engines SET session_started_at=? WHERE engine=?',(now(),engine))
            if engine=='auto' and previous['state']=='paused' and (
                    'Engine dollar loss pause' in previous['reason'] or
                    'stock dollar loss pause' in previous['reason'] or
                    'profit pause' in previous['reason']):
                # An explicit operator restart resets only lifetime engine-specific
                # stops; shared rolling/drawdown protections are never reset.
                con.execute('UPDATE automation_engines SET risk_reset_at=? WHERE engine=?',(now(),engine))
            con.execute('UPDATE automation_master SET enabled=1,updated_at=? WHERE id=1',(now(),))
            _set_engine(con,engine,'running','Observe only' if m['mode']=='observe' else 'Experimental paper simulation; not validated for live orders')
        else:
            _set_engine(con,engine,'paused' if action=='pause' else 'stopped','Manually '+action+'d')
            left=con.execute("SELECT COUNT(*) AS n FROM automation_engines WHERE state='running'").fetchone()['n']
            if not left:con.execute('UPDATE automation_master SET enabled=0,updated_at=? WHERE id=1',(now(),))
    return status(path)


def _pnl(con):
    realized=sum((dec(r['realized_net']) for r in con.execute(
        "SELECT realized_net FROM paper_positions WHERE status='CLOSED'")),Decimal(0))
    positions=[dict(r) for r in con.execute(
        "SELECT * FROM paper_positions WHERE status='OPEN' ORDER BY opened_at DESC")]
    exposure=sum((dec(p['entry_ask'])*dec(p['qty'])+dec(p['entry_fee']) for p in positions),Decimal(0))
    unrealized=sum(((dec(p['last_bid'])-dec(p['entry_ask']))*dec(p['qty'])-dec(p['entry_fee'])
                    for p in positions),Decimal(0))
    return realized,unrealized,exposure,positions


def status(path):
    with db(path) as con:
        m=dict(con.execute('SELECT * FROM automation_master WHERE id=1').fetchone())
        eng={r['engine']:{k:r[k] for k in ('state','reason','updated_at','last_signal_at','session_started_at','risk_reset_at')}
             for r in con.execute('SELECT * FROM automation_engines')}
        realized,unrealized,exposure,positions=_pnl(con)
        capital=dec(m['paper_capital'])
        equity=capital+realized+unrealized
        closed=[dict(r) for r in con.execute('''SELECT engine,asset_class,symbol,strategy,
            qty,entry_ask,exit_bid,entry_fee,exit_fee,realized_net,opened_at,closed_at,close_reason
            FROM paper_positions WHERE status='CLOSED' ORDER BY closed_at DESC LIMIT 50''')]
        events=[dict(r) for r in con.execute('SELECT ts,engine,event,details FROM automation_events ORDER BY id DESC LIMIT 30')]
        peak=con.execute('SELECT peak_equity FROM automation_highwater WHERE id=1').fetchone()['peak_equity']
        recent=datetime.now(timezone.utc)-timedelta(hours=24)
        rolling=sum((dec(r['realized_net']) for r in con.execute(
            "SELECT realized_net FROM paper_positions WHERE status='CLOSED' AND closed_at>=?",
            (recent.isoformat(),))),Decimal(0))
        for engine in ENGINES:
            eng[engine]['openPositions']=sum(1 for p in positions if p['engine']==engine)
            eng[engine]['totalCompletedTrades']=con.execute(
                "SELECT COUNT(*) AS n FROM paper_positions WHERE engine=? AND status='CLOSED'",(engine,)).fetchone()['n']
            baseline=eng[engine]['session_started_at'] if engine in ('micro','fifteen') else None
            eng[engine]['completedTrades']=con.execute(
                "SELECT COUNT(*) AS n FROM paper_positions WHERE engine=? AND status='CLOSED' AND (? IS NULL OR closed_at>=?)",
                (engine,baseline,baseline)).fetchone()['n']
            eng[engine]['netRealized']=cash(sum((dec(r['realized_net']) for r in con.execute(
                "SELECT realized_net FROM paper_positions WHERE engine=? AND status='CLOSED'",(engine,))),Decimal(0)))
    return {'master':{**m,'liveTradingAvailable':False,
                       'paperWorkerExperimental':True},
            'riskProfile':LEVELS[m['risk_level']],
            'engines':eng,'paper':{
                'capital':cash(capital),'equity':cash(equity),'realizedNet':cash(realized),
                'unrealizedNet':cash(unrealized),'exposure':cash(exposure),'peakEquity':cash(max(dec(peak),capital)),
                'rolling24hRealizedNet':cash(rolling),'openPositions':positions,
                'recentTrades':closed},
            'events':events,
            'limitations':['No real broker orders, no bank transfers, no proven profitability',
                           'Paper fills are modeled, not broker confirmed',
                           'Stock-only experimental paper signals; crypto and 15-minute orders unavailable',
                           'Web-process worker is a beta until an independent durable worker is deployed']}


def heartbeat(path,worker_id,error=None):
    with db(path) as con:
        con.execute('UPDATE automation_master SET worker_heartbeat=?,last_error=? WHERE id=1',
                    (now(),str(error)[:240] if error else None))
        if error:event(con,None,'WORKER_ERROR',error)


def _validated_quote(quote):
    if not isinstance(quote,dict) or quote.get('source')!='Public official quote API' or quote.get('market')!='stock':
        raise ValueError('Only verified Public equity snapshots are supported')
    if quote.get('completeTopOfBook') is not True or quote.get('knownStale'):
        raise ValueError('Incomplete or stale Public quote')
    if quote.get('quoteAgeSeconds') is None:
        raise ValueError('Untimestamped quote cannot be used in paper execution')
    age=dec(quote['quoteAgeSeconds'])
    if age<0 or age>120:raise ValueError('Stale quote timestamp')
    captured=datetime.fromisoformat(quote['capturedAt'].replace('Z','+00:00'))
    if captured.tzinfo is None or abs((datetime.now(timezone.utc)-captured.astimezone(timezone.utc)).total_seconds())>120:
        raise ValueError('Quote capture time stale or future dated')
    bid,ask=dec(quote['bid']),dec(quote['ask'])
    if not Decimal(0)<bid<=ask or ask>Decimal('1000000'):
        raise ValueError('Invalid bid/ask')
    if (ask-bid)/ask>Decimal('.02'):
        raise ValueError('Spread exceeds safety ceiling')
    symbol=quote['symbol']
    if not isinstance(symbol,str) or not 1<=len(symbol)<=15 or not all(x.isalnum() or x in '.-' for x in symbol):
        raise ValueError('Invalid equity symbol')
    return symbol,bid,ask


def _pause(con,engine,reason):
    row=con.execute('SELECT state FROM automation_engines WHERE engine=?',(engine,)).fetchone()
    if row and row['state']=='running':
        _set_engine(con,engine,'paused',reason)
        remaining=con.execute("SELECT COUNT(*) AS n FROM automation_engines WHERE state='running'").fetchone()['n']
        if not remaining:
            con.execute('UPDATE automation_master SET enabled=0,updated_at=? WHERE id=1',(now(),))


def process_quote(path,engine,quote,commission_bps='10'):
    """Experimental trend-following paper model; never a validated profit signal.

    A virtual fill opens at the *ask* and closes at the *bid*, with assumed
    10 bps each side. All changes are transacted atomically, checking the
    shared virtual account and individual allocations before new entry.
    """
    if engine not in ('auto','micro'):
        raise ValueError('Only Auto and Micro equity paper models are supported')
    symbol,bid,ask=_validated_quote(quote)
    bps=dec(commission_bps)
    if not 0<=bps<=100:raise ValueError('Invalid paper cost assumption')
    with db(path) as con:
        con.execute('BEGIN IMMEDIATE')
        m=con.execute('SELECT * FROM automation_master WHERE id=1').fetchone()
        e=con.execute('SELECT * FROM automation_engines WHERE engine=?',(engine,)).fetchone()
        if not m['enabled'] or m['emergency'] or m['mode'] not in ('observe','paper') or e['state']!='running':
            return {'action':'SKIP','reason':'Engine inactive or emergency stop'}
        captured=quote['capturedAt']
        con.execute('''INSERT INTO automation_quotes(engine,symbol,asset_class,captured_at,bid,ask,provider_timestamp)
                       VALUES(?,?,'stock',?,?,?,?)''',
                    (engine,symbol,captured,cash(bid),cash(ask),str(quote.get('bidTimestamp') or captured)[:60]))
        con.execute('''DELETE FROM automation_quotes WHERE id IN (
            SELECT id FROM automation_quotes WHERE engine=? AND symbol=? ORDER BY id DESC LIMIT -1 OFFSET 16)''',
                    (engine,symbol))
        if m['mode']=='observe':return {'action':'OBSERVE','symbol':symbol,'bid':cash(bid),'ask':cash(ask)}
        cfg=engine_config.read(path,engine)['config']
        capital=dec(m['paper_capital'])
        level=LEVELS[m['risk_level']]
        # Revalue matching open paper positions before testing drawdown/rolling limits.
        con.execute("UPDATE paper_positions SET last_bid=?,last_ask=? WHERE status='OPEN' AND engine=? AND symbol=?",
                    (cash(bid),cash(ask),engine,symbol))
        realized,unrealized,exposure,positions=_pnl(con)
        equity=capital+realized+unrealized
        old_peak=dec(con.execute('SELECT peak_equity FROM automation_highwater WHERE id=1').fetchone()['peak_equity'])
        peak=max(capital,old_peak,equity)
        if peak>old_peak:
            con.execute('UPDATE automation_highwater SET peak_equity=? WHERE id=1',(cash(peak),))
        profit_lock=dec(m['profit_lock_pct'])
        # Protect a percentage of already accrued virtual gains from peak equity.
        if profit_lock>0 and peak>capital and equity<=peak-(peak-capital)*profit_lock/100:
            for x in ENGINES:_pause(con,x,'Virtual high-water profit-lock drawdown triggered')
            return {'action':'PAUSE','reason':'Profit-lock drawdown reached; manual resume required'}
        protection=capital*dec(m['protected_pct'])/100
        rolling_limit=capital*dec(level['rollingLossPct'])/100
        drawdown_limit=capital*dec(level['drawdownPct'])/100
        rolled=datetime.now(timezone.utc)-timedelta(hours=24)
        recent=sum((dec(r['realized_net']) for r in con.execute(
            "SELECT realized_net FROM paper_positions WHERE status='CLOSED' AND closed_at>=?",
            (rolled.isoformat(),))),Decimal(0))
        if equity<=protection or equity<=peak-drawdown_limit or recent<=-rolling_limit:
            reason='Paper account drawdown or rolling loss threshold reached; manual resume required'
            for x in ENGINES:_pause(con,x,reason)
            return {'action':'PAUSE','reason':reason}
        limits=dec(cfg['stock_allocation']) if engine=='auto' else dec(cfg['allocation'])
        eng_row=con.execute('SELECT session_started_at,risk_reset_at FROM automation_engines WHERE engine=?',(engine,)).fetchone()
        baseline=eng_row['session_started_at'] if engine=='micro' else eng_row['risk_reset_at']
        if engine=='micro':
            completed=con.execute(
                "SELECT COUNT(*) AS n FROM paper_positions WHERE engine=? AND status='CLOSED' AND (? IS NULL OR closed_at>=?)",
                (engine,baseline,baseline)).fetchone()['n']
            if completed>=cfg['max_trades']:
                _pause(con,engine,'Micro-Trade completed-trade limit reached')
                return {'action':'PAUSE','reason':'Session trade limit reached'}
        this_open=[p for p in positions if p['engine']==engine]
        local_realized=sum((dec(r['realized_net']) for r in con.execute(
            "SELECT realized_net FROM paper_positions WHERE engine=? AND status='CLOSED' AND (? IS NULL OR closed_at>=?)",
            (engine,baseline,baseline))),Decimal(0))
        if dec(cfg['loss_stop'])>0 and local_realized<=-dec(cfg['loss_stop']):
            _pause(con,engine,'Engine dollar loss pause reached')
            return {'action':'PAUSE','reason':'Engine loss stop reached'}
        if engine=='auto' and dec(cfg.get('stock_loss_stop','0'))>0:
            stock_loss=sum((dec(r['realized_net']) for r in con.execute(
                "SELECT realized_net FROM paper_positions WHERE engine=? AND asset_class='stock' AND status='CLOSED' AND (? IS NULL OR closed_at>=?)",
                (engine,baseline,baseline))),Decimal(0))
            if stock_loss<=-dec(cfg['stock_loss_stop']):
                _pause(con,engine,'Auto-Trade stock dollar loss pause triggered')
                return {'action':'PAUSE','reason':'Auto-Trade stock loss pause reached'}
        if engine=='auto' and dec(cfg.get('profit_target','0'))>0 and local_realized>=dec(cfg['profit_target']):
            _pause(con,engine,'Optional cumulative profit pause reached')
            return {'action':'PAUSE','reason':'Configured Auto-Trade profit pause reached'}
        if engine=='auto' and dec(cfg.get('rolling_loss_stop','0'))>0:
            local_rolling=sum((dec(r['realized_net']) for r in con.execute(
                "SELECT realized_net FROM paper_positions WHERE engine=? AND status='CLOSED' AND closed_at>=?",(engine,rolled.isoformat()))),Decimal(0))
            if local_rolling<=-dec(cfg['rolling_loss_stop']):
                _pause(con,engine,'Auto-Trade 24-hour dollar loss pause reached')
                return {'action':'PAUSE','reason':'Auto-Trade rolling loss stop reached'}
        if engine!='auto' and dec(cfg['profit_target'])>0 and local_realized>=dec(cfg['profit_target']):
            _pause(con,engine,'Session profit target reached')
            return {'action':'PAUSE','reason':'Session profit target reached'}
        existing=[p for p in this_open if p['symbol']==symbol]
        if existing:
            p=existing[0]
            con.execute('UPDATE paper_positions SET last_bid=?,last_ask=? WHERE id=?',(cash(bid),cash(ask),p['id']))
            entry=dec(p['entry_ask'])
            held=(datetime.now(timezone.utc)-datetime.fromisoformat(p['opened_at'])).total_seconds()
            pnl=(bid-entry)*dec(p['qty'])
            if bid<=entry*Decimal('.98') or bid>=entry*Decimal('1.04') or held>=86400:
                exit_fee=(bid*dec(p['qty'])*bps/10000).quantize(MONEY)
                net=pnl-dec(p['entry_fee'])-exit_fee
                con.execute('''UPDATE paper_positions SET status='CLOSED',exit_bid=?,exit_fee=?,
                  realized_net=?,closed_at=?,close_reason=? WHERE id=?''',
                  (cash(bid),cash(exit_fee),cash(net),now(),
                   'experimental price threshold / holding time',p['id']))
                event(con,engine,'PAPER_EXIT',f'{symbol} modeled net {cash(net)}')
                return {'action':'PAPER_EXIT','symbol':symbol,'net':cash(net)}
            return {'action':'MARK','symbol':symbol,'unrealizedNet':cash(pnl-dec(p['entry_fee']))}
        if len(this_open)>= (cfg.get('max_open',3) if engine=='micro' else cfg.get('max_open',3)):
            return {'action':'SKIP','reason':'Engine concurrent-position ceiling'}
        if not cfg['stock_market'] or limits<=0 or dec(cfg['max_per_trade'])<=0:
            return {'action':'SKIP','reason':'Stocks disabled or allocation not configured'}
        # A paper strategy uses three temporally separated *observed* quotes.
        history=[dict(r) for r in con.execute(
            'SELECT captured_at,bid,ask FROM automation_quotes WHERE engine=? AND symbol=? ORDER BY id DESC LIMIT 3',(engine,symbol))]
        if len(history)<3:return {'action':'OBSERVE','reason':'Collecting three fresh quotes'}
        dates=[datetime.fromisoformat(r['captured_at'].replace('Z','+00:00')) for r in history]
        if (dates[0]-dates[-1]).total_seconds()<120 or (dates[0]-dates[-1]).total_seconds()>1800:
            return {'action':'OBSERVE','reason':'Waiting for evenly recent signal history'}
        old,mid,current=dec(history[2]['bid']),dec(history[1]['bid']),bid
        if not (old<mid<current):return {'action':'OBSERVE','reason':'Trend rule not confirmed'}
        trend=(current-old)/old
        spread=(ask-bid)/ask
        if trend<max(Decimal('.004'),spread*3) or trend>Decimal('.05'):
            return {'action':'OBSERVE','reason':'Trend below cost threshold or excessively volatile'}
        last=con.execute('SELECT opened_at FROM paper_positions WHERE engine=? ORDER BY opened_at DESC LIMIT 1',(engine,)).fetchone()
        cooldown=cfg.get('cooldown_seconds',60)
        if last and (datetime.now(timezone.utc)-datetime.fromisoformat(last['opened_at'])).total_seconds()<cooldown:
            return {'action':'SKIP','reason':'Entry cooldown'}
        # Percentage risk is an *estimated* loss at a modeled 2% stop, plus
        # spread and fees. A price gap can still exceed this estimate.
        max_modeled_loss=capital*dec(level['riskPct'])/100
        modeled_loss_fraction=Decimal('.02')+(ask-bid)/ask+(bps/Decimal('10000'))*2
        risk_limited_notional=max_modeled_loss/modeled_loss_fraction
        global_exposure_cap=capital*dec(level['maxExposurePct'])/100
        # Reinvest only the approved share of positive *realized* virtual gains.
        # Reserve the remaining opted-out share as non-tradable paper cash.
        gains=max(Decimal(0),realized)
        reserve=gains*dec(m['reserve_profit_pct'])/100
        compounded=gains*dec(m['compound_pct'])/100
        incremental=min(compounded,capital*Decimal('.25'))
        remaining=min(equity-protection-exposure-reserve,
                      global_exposure_cap+incremental-exposure)
        local_exposure=sum((dec(p['entry_ask'])*dec(p['qty'])+dec(p['entry_fee']) for p in this_open),Decimal(0))
        budget=min(remaining,limits-local_exposure,dec(cfg['max_per_trade']),risk_limited_notional)
        # This $5 minimum is a SIMULATION eligibility constraint, not a broker order.
        # Stocks use a $5 simulated minimum order, matching current fractional equity floor.
        if budget<Decimal('5.00'):return {'action':'SKIP','reason':'Capital limits below $5 paper order minimum'}
        # Reserve a rounded-up fee BEFORE computing quantity so cent rounding
        # can never make the modeled transaction exceed its atomic risk budget.
        from decimal import ROUND_UP
        fee_reserve=(budget*bps/10000).quantize(MONEY,rounding=ROUND_UP)
        qty=((budget-fee_reserve)/ask).quantize(Decimal('.000001'),rounding=ROUND_DOWN)
        cost=qty*ask
        entry_fee=(cost*bps/10000).quantize(MONEY,rounding=ROUND_UP)
        if qty<=0 or cost<Decimal('5.00') or cost+entry_fee>budget:
            return {'action':'SKIP','reason':'Allocation cannot cover $5 minimum and rounded-up costs'}
        paper_id=str(uuid.uuid4())
        con.execute('''INSERT INTO paper_positions
            (id,engine,asset_class,symbol,strategy,qty,entry_ask,entry_fee,
             opened_at,last_bid,last_ask,status)
            VALUES(?,?,'stock',?,'unvalidated_momentum',?,?,?,?,?,?,'OPEN')''',
            (paper_id,engine,symbol,str(qty),cash(ask),cash(entry_fee),now(),cash(bid),cash(ask)))
        con.execute('UPDATE automation_engines SET last_signal_at=? WHERE engine=?',(now(),engine))
        event(con,engine,'PAPER_ENTRY',
              f'{symbol} modeled ask {cash(ask)} qty {qty}; risk-at-stop estimate {cash(cost*modeled_loss_fraction)}; no broker order')
        return {'action':'PAPER_ENTRY','symbol':symbol,'qty':str(qty),'notional':cash(cost),
                'warning':'Experimental paper trend rule, not a validated profitable strategy'}


def fail_closed(path,reason):
    """Any market-data or worker failure pauses engines and requires human restart."""
    with db(path) as con:
        con.execute('BEGIN IMMEDIATE')
        for engine in ENGINES:
            _pause(con,engine,str(reason)[:160])
        con.execute('UPDATE automation_master SET enabled=0,last_error=?,updated_at=? WHERE id=1',
                    (str(reason)[:240],now(),))
        event(con,None,'FAIL_CLOSED',str(reason)[:220])
    return status(path)


def record_research(path,engine,detail):
    if engine not in ENGINES:
        raise ValueError('Unknown trading engine')
    with db(path) as con:
        event(con,engine,'OBSERVATION',detail)


def acquire_lease(path,worker_id,seconds=120):
    """Guard against two app instances simultaneously processing one paper engine."""
    current=datetime.now(timezone.utc)
    expiry=(current+timedelta(seconds=seconds)).isoformat()
    with db(path) as con:
        con.execute('BEGIN IMMEDIATE')
        row=con.execute('SELECT * FROM automation_worker_lease WHERE id=1').fetchone()
        if row and row['worker_id']!=worker_id and row['expires_at']>current.isoformat():
            return False
        con.execute('''INSERT INTO automation_worker_lease(id,worker_id,expires_at) VALUES(1,?,?)
            ON CONFLICT(id) DO UPDATE SET worker_id=excluded.worker_id,expires_at=excluded.expires_at''',
            (worker_id,expiry))
    return True
