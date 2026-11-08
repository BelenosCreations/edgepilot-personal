"""Historical research only: deterministic, out-of-sample momentum study.

Bars are user supplied rather than falsely claiming full Public historical integration.
No candidate score or model output authorizes orders. Returns include fee/slippage assumption.
"""
import csv, io, math
from datetime import date
from statistics import mean


def parse_daily_csv(data):
    if not isinstance(data,str) or len(data)>500_000:raise ValueError('CSV must be text of at most 500 KB')
    reader=csv.DictReader(io.StringIO(data))
    if reader.fieldnames is None:raise ValueError('CSV header required')
    fields={x.strip().lower():x for x in reader.fieldnames if x}
    if not {'date','open','close'}.issubset(fields):raise ValueError('Required columns: date,open,close')
    bars=[];last=None
    for raw in reader:
        if len(bars)>=5000:raise ValueError('Maximum 5000 daily bars')
        try:
            d=date.fromisoformat(raw[fields['date']].strip());o=float(raw[fields['open']]);c=float(raw[fields['close']])
        except (TypeError,ValueError,AttributeError,KeyError):raise ValueError('Invalid ISO date or numeric bar')
        if not all(math.isfinite(v) and v>0 for v in (o,c)):raise ValueError('Prices must be finite and positive')
        if last is not None and d<=last:raise ValueError('Bars must be strictly ordered by date, no duplicates')
        bars.append({'date':d.isoformat(),'open':o,'close':c});last=d
    if len(bars)<50:raise ValueError('At least 50 daily bars required')
    return bars


def backtest(bars, lookback=5, holding_days=2, cost_bps=20, training_pct=60):
    """Signal at close of day t using only past closes; buy next open; sell later open.
    No overlapping positions. Results come from unmodified train/test chronological partitions.
    Costs include assumed round-trip spreads, broker fees and slippage in basis points.
    This is NOT predictive model validation and does not calculate a calibrated edge.
    """
    if not 2<=lookback<=60:raise ValueError('lookback must be 2–60 days')
    if not 1<=holding_days<=20:raise ValueError('holding days must be 1–20')
    if not 0<=cost_bps<=1000:raise ValueError('cost_bps must be 0–1000')
    if not 50<=training_pct<=80:raise ValueError('training_pct must be 50–80')
    if len(bars)<max(50,lookback+holding_days+20):raise ValueError('Insufficient observations')
    split=int(len(bars)*training_pct/100)
    # Test positions have signal at/after split; no overlap, no future bars beyond array.
    def sample(start,end):
        pos=max(start,lookback);trades=[]
        while pos+1+holding_days<len(bars) and pos+1+holding_days<end:
            # Today signal checks trailing lookback change only, never future prices.
            momentum=bars[pos]['close']/bars[pos-lookback]['close']-1
            if momentum>0:
                entry=bars[pos+1]['open'];exit_price=bars[pos+1+holding_days]['open']
                gross=exit_price/entry-1
                net=gross-cost_bps/10_000
                trades.append({'signalDate':bars[pos]['date'],'entryDate':bars[pos+1]['date'],
                  'exitDate':bars[pos+1+holding_days]['date'],'grossReturnPct':round(gross*100,4),
                  'netReturnPct':round(net*100,4)})
                pos+=1+holding_days
            else:pos+=1
        return trades
    def stats(trades):
        if not trades:return {'trades':0,'winRatePct':None,'meanNetReturnPct':None,'compoundedNetReturnPct':0.0,'maxDrawdownPct':0.0}
        equity=1.0;high=1.0;max_dd=0.0
        for t in trades:
            equity*=1+t['netReturnPct']/100;high=max(high,equity)
            max_dd=max(max_dd,(high-equity)/high)
        return {'trades':len(trades),'winRatePct':round(100*sum(t['netReturnPct']>0 for t in trades)/len(trades),2),
          'meanNetReturnPct':round(mean(t['netReturnPct'] for t in trades),4),
          'compoundedNetReturnPct':round((equity-1)*100,4), 'maxDrawdownPct':round(max_dd*100,4)}
    training=sample(lookback,split);testing=sample(split,len(bars))
    return {'model':'Long-only trailing momentum illustrative rule','dataSource':'User-supplied daily CSV',
      'assumptions':{'lookbackDays':lookback,'holdingDays':holding_days,'roundTripCostBps':cost_bps,'trainingPct':training_pct},
      'bars':len(bars),'training':stats(training),'outOfSample':stats(testing),
      'sampleTrades':testing[:15],
      'warning':'Research only. No calibrated success probability or demonstrated future edge. Data may have survivorship bias, corporate action errors, gaps, and unrealistically assumed fills. Not trade eligible.',
      'eligibleForTrading':False}
