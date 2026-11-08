"""Broker universe discovery: strictly bounded, READ ONLY, no direction estimates.
Public instruments API response: instruments[].instrument.symbol/type.
Public events API response: content[]; always require valid details before ranking.
"""
from hashlib import sha256

MODES=('automatic','hybrid','watchlist')

def validate_mode(value):
    if value not in MODES:raise ValueError('Choose automatic, hybrid or watchlist')
    return value

def equity_symbols(response):
    if not isinstance(response,dict) or not isinstance(response.get('instruments'),list):raise ValueError('Invalid instruments response')
    symbols=[];seen=set()
    for row in response['instruments']:
        if not isinstance(row,dict) or row.get('trading')!='BUY_AND_SELL':continue
        instrument=row.get('instrument') or {}
        if instrument.get('type')!='EQUITY':continue
        sym=instrument.get('symbol')
        if not isinstance(sym,str) or not 0<len(sym)<=15 or not all(c.isalnum() or c in '.-' for c in sym):continue
        if sym not in seen:symbols.append(sym);seen.add(sym)
    return sorted(symbols)

def select_window(symbols, cursor, count, excluded=()):
    """Rotating market *coverage*, not a profitability ranking."""
    if not 1<=count<=100:raise ValueError('Invalid scan size')
    symbols=list(dict.fromkeys(symbols)); n=len(symbols)
    if not n:return [],0
    excluded=set(excluded);selected=[];position=cursor%n;visited=0
    while visited<n and len(selected)<count:
        sym=symbols[position];position=(position+1)%n;visited+=1
        if sym not in excluded:selected.append(sym)
    return selected,position

def prediction_events(response,limit=10):
    if not isinstance(response,dict) or not isinstance(response.get('content'),list):raise ValueError('Invalid event summary')
    events=[];seen=set()
    for row in response['content']:
        if not isinstance(row,dict) or row.get('resolved') or row.get('halted'):continue
        sym=row.get('eventSymbol')
        if not isinstance(sym,str) or not sym or len(sym)>160 or sym in seen:continue
        events.append({'event':sym,'title':str(row.get('title',''))[:200],'volume':row.get('volume')})
        seen.add(sym)
        if len(events)>=limit:break
    return events

def contract_candidates(details, max_contracts=2):
    """Do not infer valid broker-side prices: downstream snapshot revalidates each contract."""
    found=[]
    if not isinstance(details,dict) or details.get('resolved') or details.get('halted'):return found
    for outcome in details.get('outcomes',[]):
        if not isinstance(outcome,dict) or outcome.get('state')!='STATE_OPEN' or outcome.get('trading')!='BUY_AND_SELL':continue
        for contract in outcome.get('contracts',[]):
            if not isinstance(contract,dict):continue
            symbol=contract.get('symbol')
            if isinstance(symbol,str) and 0<len(symbol)<=160 and symbol not in found:found.append(symbol)
            if len(found)>=max_contracts:return found
    return found

def mode_sources(mode,auto,manual):
    validate_mode(mode)
    return list(dict.fromkeys((auto if mode!='watchlist' else [])+(manual if mode!='automatic' else [])))
