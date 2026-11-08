"""Read-only, broker-sourced, explicit market snapshots. No forecasts or trades."""
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

STOCK_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")

def number(value):
    try:
        x=Decimal(str(value))
        return str(x) if x.is_finite() and x >= 0 else None
    except (InvalidOperation, TypeError, ValueError):return None

def stock_snapshot(public_call, account, symbol, now=None):
    symbol=str(symbol).strip().upper()
    if not STOCK_SYMBOL.fullmatch(symbol):raise ValueError('Invalid stock or ETF symbol')
    data=public_call('POST','/userapigateway/marketdata/'+quote(account,safe='')+'/quotes',
                     {'instruments':[{'symbol':symbol,'type':'EQUITY'}]})
    quotes=data.get('quotes')
    if not isinstance(quotes,list):raise ValueError('Invalid Public quotes response')
    matched=[q for q in quotes if isinstance(q,dict) and q.get('instrument',{}).get('symbol')==symbol and q.get('instrument',{}).get('type')=='EQUITY']
    if len(matched)!=1 or matched[0].get('outcome')!='SUCCESS':raise ValueError('Matching successful equity quote unavailable')
    q=matched[0];bid=number(q.get('bid'));ask=number(q.get('ask'))
    valid=bid is not None and ask is not None and Decimal(ask)>0 and Decimal(bid)>0 and Decimal(ask)>=Decimal(bid)
    spread=str(Decimal(ask)-Decimal(bid)) if valid else None
    ratio=str((Decimal(spread)/Decimal(ask)*100).quantize(Decimal('.0001'))) if valid else None
    quote_times=[q.get('bidTimestamp'),q.get('askTimestamp')]
    parsed=[]
    for value in quote_times:
        if not value:continue
        try:parsed.append(datetime.fromisoformat(str(value).replace('Z','+00:00')).astimezone(timezone.utc))
        except ValueError:pass
    # A bid/ask is not execution-ready when it is crossed, incomplete, or known stale.
    age=max(((datetime.now(timezone.utc)-t).total_seconds() for t in parsed),default=None)
    stale=(age is not None and age>120)
    return {'market':'stock','symbol':symbol,'source':'Public official quote API','capturedAt':now or datetime.now(timezone.utc).isoformat(),
       'bid':bid,'ask':ask,'last':number(q.get('last')),'volume':q.get('volume'),
       'spread':spread,'spreadPctOfAsk':ratio,'bidTimestamp':q.get('bidTimestamp'), 'askTimestamp':q.get('askTimestamp'),
       'completeTopOfBook':valid,'knownStale':stale,'quoteAgeSeconds':str(round(age)) if age is not None else None,'riskWarning':'Real broker quote, not a forecast, opportunity ranking, or guaranteed executable price.'}

def prediction_snapshot(public_call,event,contract,now=None):
    event=str(event).strip();contract=str(contract).strip()
    if not event or len(event)>160 or '/' in event or '?' in event or not contract or len(contract)>160:raise ValueError('Invalid event/contract')
    data=public_call('GET','/userapigateway/eventcontract/details/'+quote(event,safe=''))
    if data.get('eventSymbol')!=event:raise ValueError('Event symbol mismatch')
    found=[]
    for outcome in data.get('outcomes',[]):
      if not isinstance(outcome,dict):continue
      for c in outcome.get('contracts',[]):
       if isinstance(c,dict) and c.get('symbol')==contract:found.append((outcome,c))
    if len(found)!=1:raise ValueError('Contract not present exactly once in event response')
    outcome,c=found[0];bid=number(c.get('bid'));ask=number(c.get('ask'))
    valid=bid is not None and ask is not None and 0<Decimal(bid)<=Decimal(ask)<=1
    trading=outcome.get('state')=='STATE_OPEN' and outcome.get('trading')=='BUY_AND_SELL' and not (data.get('resolved') or data.get('halted'))
    return {'market':'prediction','event':event,'symbol':contract,'title':str(data.get('title',''))[:200],
        'outcomeTitle':str(outcome.get('title',''))[:200],'source':'Public official event details API',
        'capturedAt':now or datetime.now(timezone.utc).isoformat(),'bid':bid,'ask':ask,
        'spread':str(Decimal(ask)-Decimal(bid)) if valid else None,
        'volume':number(outcome.get('volume')),'eventVolume':number(data.get('volume')),
        'probabilityFromProvider':number(c.get('probability')),'openForTrading':trading,
        'completeTopOfBook':valid, 'estimatedFeePerContractPerSide':'0.02',
        'riskWarning':'Market quote is not an independently calibrated outcome probability. Fees, uncertainty and lack of liquidity can create losses.'}

def text_context(snapshot):
    """Allowlisted summary only; never forward credentials, account IDs or raw broker JSON."""
    keys=('market','symbol','event','title','outcomeTitle','capturedAt','bid','ask','last','spread',
          'spreadPctOfAsk','volume','eventVolume','bidTimestamp','askTimestamp','knownStale','quoteAgeSeconds','openForTrading','completeTopOfBook',
          'estimatedFeePerContractPerSide','riskWarning')
    return '\n'.join(f'{k}: {snapshot[k]}' for k in keys if snapshot.get(k) is not None)[:3800]
