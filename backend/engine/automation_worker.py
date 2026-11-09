"""Background observation and experimental paper-model polling for EdgePilot.

Safe to run inside one Gunicorn web worker on the current Render Starter
service. Uses a SQLite lease to prevent duplicate loops. A dedicated worker
and a shared transactional database are required before live automation.
No live brokerage execution or bank movement exists in this module.
"""
import logging
import os
import threading
import uuid
from datetime import datetime, timezone

from . import automation

LOG=logging.getLogger(__name__)
_worker=None
_worker_lock=threading.Lock()


def one_cycle(appmod, worker_id):
    path=str(appmod.DB)
    if not automation.acquire_lease(path,worker_id):
        return {'status':'LEASE_HELD','scanned':0}
    state=automation.status(path)
    m=state['master']
    if not m['enabled'] or m['emergency']:
        automation.heartbeat(path,worker_id)
        return {'status':'IDLE','scanned':0}
    engines={k:v for k,v in state['engines'].items() if v['state']=='running'}
    if not engines:
        automation.heartbeat(path,worker_id)
        return {'status':'IDLE','scanned':0}
    if not m['mode'] in ('observe','paper'):
        automation.fail_closed(path,'Unsupported automation mode')
        return {'status':'FAIL_CLOSED','scanned':0}
    try:
        account=appmod.selected_account()
        from . import opportunity_scan, market_snapshot
        with appmod.database() as con:
            config=con.execute('SELECT symbols FROM scan_config WHERE id=1').fetchone()
            discovery=con.execute('''SELECT mode,cursor,equity_per_scan FROM discovery_config WHERE id=1''').fetchone()
            watch=opportunity_scan.stock_universe(config['symbols'] if config else '')
        issues=[]
        if discovery:
            mode=discovery['mode']
            count=min(5,max(1,discovery['equity_per_scan']))
            cursor=discovery['cursor']
        else:
            mode,count,cursor='automatic',5,0
        symbols,ignored,next_cursor,total=appmod.discovered_market_candidates(
            account,mode,count,0,cursor,watch,issues)
        if discovery and mode!='watchlist' and total:
            with appmod.database() as con:
                con.execute('UPDATE discovery_config SET cursor=? WHERE id=1',(next_cursor,))
        # Open paper positions must be quoted on every cycle even when discovery rotates.
        for p in state['paper']['openPositions']:
            if p['asset_class']=='stock' and p['symbol'] not in symbols:
                symbols.insert(0,p['symbol'])
        symbols=list(dict.fromkeys(symbols))[:15]
        if not symbols:
            raise ValueError('No eligible equity symbols; broker discovery/watchlist is unavailable')
        scanned=0
        for symbol in symbols:
            try:
                quote=market_snapshot.stock_snapshot(appmod.pub,account,symbol)
            except Exception as exc:
                LOG.warning('Read-only quote unavailable for %s: %s',symbol,type(exc).__name__)
                continue
            for engine in ('auto','micro'):
                if engine not in engines:
                    continue
                try:
                    automation.process_quote(path,engine,quote)
                    scanned+=1
                except ValueError as exc:
                    LOG.info('Skipped invalid paper quote for %s: %s',symbol,str(exc)[:150])
        if 'fifteen' in engines and m['mode']=='observe':
            try:
                from . import fifteen_minute
                data=fifteen_minute.discover(appmod.pub,limit=4)
                automation.record_research(path,'fifteen','Validated open market windows: '+str(len(data['events'])))
            except Exception as exc:
                automation.record_research(path,'fifteen','Market research unavailable: '+type(exc).__name__)
        if not scanned and m['mode']=='paper':
            automation.fail_closed(path,'No usable fresh stock quotes from Public; manual resume required')
            return {'status':'PAUSED_NO_DATA','scanned':0}
        automation.heartbeat(path,worker_id)
        return {'status':'OBSERVED','scanned':scanned}
    except Exception as exc:
        # No market data means the risk engine must not continue paper entries.
        LOG.exception('EdgePilot worker safety pause')
        automation.fail_closed(path,'Market access or worker failure: '+type(exc).__name__)
        automation.heartbeat(path,worker_id,str(type(exc).__name__))
        return {'status':'PAUSED_ERROR','scanned':0}


def _run(appmod, interval):
    worker_id=str(uuid.uuid4())
    while True:
        try:
            one_cycle(appmod,worker_id)
        except Exception:
            LOG.exception('EdgePilot automation worker unexpected error')
        threading.Event().wait(interval)


def start_web_worker(appmod):
    """Only one Gunicorn worker and one persistent local volume are supported.
    Never called during local unit tests unless explicitly opted in.
    """
    global _worker
    if os.getenv('EDGE_AUTOMATION_WORKER_ENABLED','false').lower()!='true':
        return False
    with _worker_lock:
        if _worker is not None and _worker.is_alive():
            return True
        delay=int(os.getenv('EDGE_AUTOMATION_POLL_SECONDS','90'))
        if not 60<=delay<=3600:
            raise ValueError('Worker poll interval must be 60–3600 seconds')
        _worker=threading.Thread(target=_run,args=(appmod,delay),daemon=True,
                                name='edgepilot-paper-observer')
        _worker.start()
    return True
