"""Read-only anchored walk-forward validation of a transparent momentum rule.

Every fold trains on earlier chronological bars and evaluates a later, disjoint test
window. Never authorizes live trading. This intentionally does not estimate a
probability of profitable future performance.
"""
import math
from statistics import mean, median
from datetime import date


def _validate(bars, cost_bps, training_bars, test_bars, step_bars, lookbacks, hold_days):
    if not isinstance(bars,list) or len(bars)>5000: raise ValueError('Invalid bar array')
    if isinstance(cost_bps,bool) or not isinstance(cost_bps,int) or not 0<=cost_bps<=1000:raise ValueError('Costs must be 0–1000 bps')
    for name,v,lo,hi in [('trainingBars',training_bars,70,4000),('testBars',test_bars,30,1000),('stepBars',step_bars,30,1000),('holdDays',hold_days,1,20)]:
        if isinstance(v,bool) or not isinstance(v,int) or not lo<=v<=hi:raise ValueError(name+' outside allowed range')
    if not isinstance(lookbacks,(list,tuple)) or not 1<=len(lookbacks)<=12 or any(isinstance(v,bool) or not isinstance(v,int) or not 2<=v<=60 for v in lookbacks) or len(set(lookbacks))!=len(lookbacks):raise ValueError('Invalid lookback candidates')
    if step_bars<test_bars:raise ValueError('Step must be at least test window to avoid overlapping test periods')
    if training_bars+test_bars>len(bars):raise ValueError('Not enough bars for one full fold')
    last=None
    for b in bars:
        if not isinstance(b,dict):raise ValueError('Invalid daily bar')
        try:d=date.fromisoformat(b['date']);o=float(b['open']);c=float(b['close'])
        except (ValueError,TypeError,KeyError):raise ValueError('Invalid daily bar')
        if last is not None and d<=last:raise ValueError('Dates must be increasing and unique')
        if not math.isfinite(o) or not math.isfinite(c) or o<=0 or c<=0:raise ValueError('Invalid prices')
        last=d


def _trades(bars, start, end, lookback, hold, cost_bps):
    # Signal formed at close t using only closes <= t. Entry at next open.
    # Exit at the open hold days after entry; never cross window boundary.
    # Entry signal may use pre-window history, but future test observations never
    # inform parameter selection or an earlier fold.
    t=max(start,lookback)
    out=[]
    while t+1+hold<end:
        momentum=bars[t]['close']/bars[t-lookback]['close']-1
        if momentum>0:
            entry=bars[t+1]['open'];exit_=bars[t+1+hold]['open']
            net=exit_/entry-1-cost_bps/10_000
            out.append({'entryDate':bars[t+1]['date'],'exitDate':bars[t+1+hold]['date'],'netReturnPct':round(net*100,6)})
            t+=hold+1
        else:t+=1
    return out


def _stats(trades):
    n=len(trades)
    if not n:return {'trades':0,'winRatePct':None,'averageNetReturnPct':None,'compoundedReturnPct':0.,'maxDrawdownPct':0.}
    equity=1.;peak=1.;maxdd=0.
    for t in trades:
        equity*=max(0.,1+t['netReturnPct']/100)
        peak=max(peak,equity)
        maxdd=max(maxdd,(peak-equity)/peak)
    return {'trades':n,'winRatePct':round(sum(t['netReturnPct']>0 for t in trades)*100/n,2),'averageNetReturnPct':round(mean(t['netReturnPct'] for t in trades),4),'compoundedReturnPct':round((equity-1)*100,4),'maxDrawdownPct':round(maxdd*100,4)}


def validate(bars, *, training_bars=180, test_bars=60, step_bars=60, lookbacks=(3,5,10,20), hold_days=2, cost_bps=20):
    _validate(bars,cost_bps,training_bars,test_bars,step_bars,lookbacks,hold_days)
    folds=[];all_test=[]
    # Anchored growing training window: each training period begins at first bar.
    for test_start in range(training_bars,len(bars)-test_bars+1,step_bars):
        test_end=test_start+test_bars
        # Choose lookback using TRAIN only; score by average net return, but
        # require >= 3 training trades. Never fit on the test window.
        samples=[]
        for look in lookbacks:
            tr=_trades(bars,0,test_start,look,hold_days,cost_bps)
            if len(tr)<3:continue
            st=_stats(tr)
            samples.append((st['averageNetReturnPct'],st['maxDrawdownPct'],look,st))
        if not samples:
            folds.append({'trainingEndDate':bars[test_start-1]['date'],'testStartDate':bars[test_start]['date'],'testEndDate':bars[test_end-1]['date'],'status':'insufficient_training_trades','test':None})
            continue
        # deterministic tie-break: smaller drawdown, then shorter lookback
        samples.sort(key=lambda v:(-v[0],v[1],v[2]))
        _,_,chosen,train_stats=samples[0]
        test=_trades(bars,test_start,test_end,chosen,hold_days,cost_bps)
        all_test.extend(test)
        folds.append({'trainingEndDate':bars[test_start-1]['date'],'testStartDate':bars[test_start]['date'],'testEndDate':bars[test_end-1]['date'],
          'lookbackSelected':chosen,'train':train_stats,'test':_stats(test),'status':'evaluated'})
    evaluated=[f for f in folds if f['status']=='evaluated']
    positive=sum(f['test']['compoundedReturnPct']>0 for f in evaluated)
    total=_stats(all_test)
    issues=[]
    if len(evaluated)<3:issues.append('Fewer than 3 evaluated walk-forward windows')
    if total['trades']<30:issues.append('Fewer than 30 out-of-sample trades')
    if evaluated and positive/len(evaluated)<.6:issues.append('Less than 60% of evaluation windows showed positive modeled returns')
    if not evaluated:issues.append('No evaluable windows')
    if total['compoundedReturnPct']<=0:issues.append('Combined modeled out-of-sample returns were not positive')
    return {'method':'Anchored expanding-window walk-forward, nonoverlapping tests','bars':len(bars),
       'settings':{'trainingBars':training_bars,'testBars':test_bars,'stepBars':step_bars,'lookbacks':list(lookbacks),'holdingDays':hold_days,'roundTripCostBps':cost_bps},
       'folds':folds,'evaluatedWindows':len(evaluated),'positiveWindows':positive,'outOfSample':total,
       'researchReadiness':'insufficient_evidence' if issues else 'further_validation_required','warnings':issues,
       'eligibleForTrading':False,
       'disclaimer':'Research only. Historical fills are idealized and corporate actions, liquidity, survivorship bias, regime changes and taxes may invalidate results. This is not a calibrated probability or permission to trade.'}
