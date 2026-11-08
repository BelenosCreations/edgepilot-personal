"""Read-only opportunity scanner. Market-quality ranking is NOT a return forecast."""
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
import re

STOCK = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")

def dec(x):
    try:
        v=Decimal(str(x))
        if not v.is_finite():raise ValueError('Non-finite')
        return v
    except (InvalidOperation,TypeError,ValueError):raise ValueError('Invalid finite number')

def positive(x):
    v=dec(x)
    return v if v>=0 else None

def stock_universe(raw):
    if not isinstance(raw,str) or len(raw)>300:raise ValueError('Invalid symbol list')
    names=list(dict.fromkeys(x.strip().upper() for x in raw.split(',') if x.strip()))
    if len(names)>25 or any(not STOCK.fullmatch(s) for s in names):raise ValueError('Use at most 25 valid equity symbols')
    return names

def quality(snapshot):
    """Score quote tradeability, not direction, expected return or probability."""
    if not snapshot.get('completeTopOfBook'):return 0,['Incomplete top-of-book quote']
    if snapshot.get('knownStale'):return 0,['Stale quote']
    if snapshot.get('market')=='prediction' and not snapshot.get('openForTrading'):return 0,['Market closed or halted']
    try:bid,ask=dec(snapshot['bid']),dec(snapshot['ask'])
    except ValueError:return 0,['Incomplete or nonnumeric bid/ask']
    if not 0<bid<=ask:return 0,['Invalid bid/ask']
    spread=(ask-bid)/ask
    score=max(0,80-int(spread*Decimal('1000')))
    why=[f'Bid/ask spread {spread*100:.2f}% of ask']
    if snapshot['market']=='stock':
        vol=positive(snapshot.get('volume')) if snapshot.get('volume') is not None else None
        if vol is not None and vol>=100000:score+=15;why.append('Reported volume at least 100,000')
        elif vol is None:why.append('Volume unavailable')
        else:why.append('Low reported volume')
        if snapshot.get('quoteAgeSeconds') is None:score=min(score,55);why.append('Quote timestamp unavailable')
    else:
        vol=positive(snapshot.get('eventVolume')) if snapshot.get('eventVolume') is not None else None
        if vol is not None and vol>=10000:score+=15;why.append('Event volume at least 10,000')
        elif vol is None:why.append('Event volume unavailable')
        else:why.append('Limited event volume')
        if not snapshot.get('quoteTimestamp'):score=min(score,55);why.append('Contract quote timestamp unavailable')
    return max(0,min(100,score)),why

def assess(snapshot, fair_pct=None, fee_per_side=Decimal('0.02')):
    if fair_pct is not None and not 0<dec(fair_pct)<100:raise ValueError('Fair probability must be 0–100 exclusive')
    score,explain=quality(snapshot)
    result={'market':snapshot['market'],'symbol':snapshot['symbol'],'event':snapshot.get('event'),
      'bid':snapshot.get('bid'),'ask':snapshot.get('ask'),'capturedAt':snapshot.get('capturedAt'),
      'qualityScore':score,'scoreMeaning':'Data/tradeability quality only; not probability or forecast',
      'reasons':explain,'classification':'REVIEW_DATA' if score<45 else 'RESEARCH',
      'eligibleForAutomaticTrading':False,'expectedNetValue':None,'modelSource':None}
    if snapshot['market']=='prediction' and fair_pct is not None and score>=45:
        p=dec(fair_pct)/100
        if not 0<p<1:raise ValueError('Fair probability must be 0–100 exclusive')
        ask=dec(snapshot['ask'])
        # Buy-and-hold to resolution: $1 payout if YES, $0 if NO; entry fee.
        # Sell-before-resolution would require different price paths and exit fees.
        net=p-ask-dec(fee_per_side)
        result['expectedNetValue']=str(net.quantize(Decimal('.0001')))
        result['assumedProbability']=str(p)
        result['modelSource']='Manually supplied fair-probability assumption; NOT a validated predictive model'
        result['reasons'].append('Expected net value assumes hold to settlement; no early-sale fees modeled')
        result['classification']='RESEARCH_ASSUMPTION_POSITIVE' if net>0 else 'REJECT_ASSUMPTION_NEGATIVE'
    elif snapshot['market']=='stock':
        result['reasons'].append('Stock fair value and directional forecast unavailable; spread/volume alone cannot establish expected profit')
    else:
        result['reasons'].append('No independent probability estimate; market-implied odds alone cannot establish an edge')
    return result

def rank(items):
    # Never rank unvalidated fair-value assumptions as broker-ready profit signals.
    return sorted(items,key=lambda v:(v['qualityScore'],v.get('expectedNetValue') is not None),reverse=True)
