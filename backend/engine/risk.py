'''Central fail-closed exposure calculation. Decimal-only, no broker calls.
The account adapter must provide a fresh reconciled broker snapshot.
'''
from decimal import Decimal
from .ledger import dec, money

class RiskBlocked(ValueError):pass

def buying_capacity(*, public_equity, independent_equity=None, balance_source='public',
                    protected_pct, spend_cap, per_trade_cap, broker_buying_power,
                    attributed_exposure, other_exposure, open_orders, unreconciled_orders,
                    fresh, reconciled, pending_external_sale=False):
    if not fresh or not reconciled:raise RiskBlocked('Broker data stale or not reconciled')
    values=[public_equity,protected_pct,spend_cap,per_trade_cap,broker_buying_power,
            attributed_exposure,other_exposure,open_orders,unreconciled_orders]
    if independent_equity is not None:values.append(independent_equity)
    if any(dec(v)<0 for v in values):raise RiskBlocked('Negative exposure/account input')
    if not Decimal('1')<=dec(protected_pct)<=Decimal('100'):raise RiskBlocked('Invalid protection percentage')
    if balance_source not in ('public','independent'):raise RiskBlocked('Invalid balance source')
    public=dec(public_equity)
    basis=public if balance_source=='public' else dec(independent_equity)
    if basis<=0 or basis>public:raise RiskBlocked('Allocation exceeds Public account equity')
    if pending_external_sale:raise RiskBlocked('Manual sale needs repurchase policy decision')
    allowance=min(dec(spend_cap),basis*(Decimal('100')-dec(protected_pct))/Decimal('100'))
    # Account-wide exposure cannot be hidden by switching strategies.
    outstanding=dec(attributed_exposure)+dec(other_exposure)+dec(open_orders)+dec(unreconciled_orders)
    free=max(Decimal('0'),min(allowance-outstanding,dec(broker_buying_power)))
    return {'riskBudget':money(allowance),'remainingToRisk':money(free),
            'singleTradeLimit':money(min(free,dec(per_trade_cap))),
            'protectedValue':money(basis*dec(protected_pct)/100),
            'warning':'Limits reduce potential exposure but cannot guarantee against market losses.'}
