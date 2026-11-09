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

from . import automation, observation_health, stock_session

LOG=logging.getLogger(__name__)
_worker=None
_worker_lock=threading.Lock()


def one_cycle(appmod, worker_id):
    path=str(appmod.DB)
    if not automation.acquire_lease(path,worker_id):
        return {'status':'LEASE_HELD','scanned':0}
    state=automation.status(path)
    m=state['master']
    attempted=[]; accepted=0; rejected=0; ages=[]; warnings=[]; scanned=0
    session='NOT_APPLICABLE'
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
    # A recent Public quote does not prove the NYSE cash equity session is
    # open. Do not poll for modeled fills when the regular exchange is closed.
    if m['mode']=='paper' and any(e in engines for e in ('auto','micro')):
        session=stock_session.regular_session_state()
        if session=='UNKNOWN':
            automation.fail_closed(path,'Stock exchange schedule unavailable; manual resume required')
            observation_health.record_cycle(path,mode=m['mode'],state='CALENDAR_UNKNOWN',
                                            market_session=session,issue='Exchange schedule unavailable')
            automation.heartbeat(path,worker_id)
            return {'status':'PAUSED_NO_CALENDAR','scanned':0}
        if session=='CLOSED':
            observation_health.record_cycle(path,mode=m['mode'],state='MARKET_CLOSED',
                                            market_session=session,issue='NYSE scheduled regular session closed')
            automation.heartbeat(path,worker_id)
            return {'status':'MARKET_CLOSED','scanned':0}
    try:
        account=appmod.selected_account()
        from . import opportunity_scan, market_snapshot
        stock_engines=[engine for engine in ('auto','micro') if engine in engines]
        if stock_engines and m['mode']=='observe':
            session=stock_session.regular_session_state()
        positions=[p for p in state['paper']['openPositions'] if p['asset_class']=='stock']
        # Always prioritize outstanding paper positions over new discovery.
        required_symbols=list(dict.fromkeys(p['symbol'] for p in positions))
        symbols=list(required_symbols)
        issues=[]
        if stock_engines:
            with appmod.database() as con:
                config=con.execute('SELECT symbols FROM scan_config WHERE id=1').fetchone()
                discovery=con.execute('''SELECT mode,cursor,equity_per_scan FROM discovery_config WHERE id=1''').fetchone()
                watch=opportunity_scan.stock_universe(config['symbols'] if config else '')
            if discovery:
                mode=discovery['mode']
                count=min(5,max(1,discovery['equity_per_scan']))
                cursor=discovery['cursor']
            else:
                mode,count,cursor='automatic',5,0
            discovered,ignored,next_cursor,total=appmod.discovered_market_candidates(
                account,mode,count,0,cursor,watch,issues)
            if discovery and mode!='watchlist' and total:
                with appmod.database() as con:
                    con.execute('UPDATE discovery_config SET cursor=? WHERE id=1',(next_cursor,))
            symbols=list(dict.fromkeys(required_symbols+discovered[:5]))
            if not symbols and m['mode']=='paper':
                raise ValueError('No eligible equities; paper model must pause rather than invent quotes')
        seen_open=set()
        for symbol in symbols:
            attempted.append(symbol)
            try:
                quote=market_snapshot.stock_snapshot(appmod.pub,account,symbol)
            except Exception as exc:
                rejected+=1
                warnings.append('Public quote unavailable for '+symbol)
                LOG.warning('Read-only quote unavailable for %s: %s',symbol,type(exc).__name__)
                if symbol in required_symbols:
                    raise ValueError('An open paper position lacks a fresh broker quote')
                continue
            valid=False
            for engine in stock_engines:
                try:
                    result=automation.process_quote(path,engine,quote)
                    if result['action']=='MARKET_CLOSED':
                        # Session closed between preflight and processing; never model fills.
                        observation_health.record_cycle(
                            path,mode=m['mode'],state='MARKET_CLOSED',market_session='CLOSED',
                            symbols=attempted,accepted=accepted,rejected=rejected,
                            issue='NYSE session closed during observation cycle')
                        automation.heartbeat(path,worker_id)
                        return {'status':'MARKET_CLOSED','scanned':scanned}
                    if result['action']!='SKIP':
                        valid=True
                        scanned+=1
                        if symbol in required_symbols:
                            seen_open.add(symbol)
                except ValueError as exc:
                    LOG.info('Skipped invalid paper quote for %s: %s',symbol,str(exc)[:150])
                    warnings.append('Quote validation rejected for '+symbol)
                    if symbol in required_symbols:
                        rejected+=1
                        raise ValueError('An open paper position has an invalid broker quote')
            if valid:
                accepted+=1
                try:
                    age=int(float(quote['quoteAgeSeconds']))
                    if 0<=age<=86400:ages.append(age)
                except (ValueError,TypeError,OverflowError,KeyError):
                    pass
            else:
                rejected+=1
        if required_symbols and not set(required_symbols)<=seen_open:
            raise ValueError('Open paper positions could not be marked safely')
        if 'fifteen' in engines and m['mode']=='observe':
            try:
                from . import fifteen_minute
                data=fifteen_minute.discover(appmod.pub,limit=4)
                automation.record_research(path,'fifteen','Validated open market windows: '+str(len(data['events'])))
            except Exception as exc:
                automation.record_research(path,'fifteen','Market research unavailable: '+type(exc).__name__)
        if not accepted and m['mode']=='paper' and stock_engines:
            observation_health.record_cycle(
                path,mode=m['mode'],state='NO_DATA',market_session=session,
                symbols=attempted,accepted=accepted,rejected=rejected,
                quote_age_seconds=max(ages) if ages else None,
                issue='No usable verified Public stock quotes; manual restart required')
            automation.fail_closed(path,'No usable fresh stock quotes from Public; manual resume required')
            automation.heartbeat(path,worker_id)
            return {'status':'PAUSED_NO_DATA','scanned':0}
        cycle_state='PARTIAL' if rejected and accepted else 'OK' if accepted else 'NO_DATA'
        note='Some quotes unavailable or rejected' if rejected else (
            'No verified equity quotes in this cycle' if not accepted else None)
        if issues and not note:note='Partial market discovery; research-only catalog limitations'
        observation_health.record_cycle(
            path,mode=m['mode'],state=cycle_state,market_session=session,
            symbols=attempted,accepted=accepted,rejected=rejected,
            quote_age_seconds=max(ages) if ages else None,issue=note)
        automation.heartbeat(path,worker_id)
        return {'status':'OBSERVED' if accepted else 'NO_DATA','scanned':scanned}
    except Exception as exc:
        # Worker errors must never silently appear as successful observations.
        LOG.exception('EdgePilot worker safety pause')
        automation.fail_closed(path,'Market access or worker failure: '+type(exc).__name__)
        observation_health.record_cycle(
            path,mode=m['mode'],state='ERROR',market_session=session,
            symbols=attempted,accepted=accepted,rejected=rejected,
            quote_age_seconds=max(ages) if ages else None,
            issue='Worker failed closed: '+type(exc).__name__)
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
