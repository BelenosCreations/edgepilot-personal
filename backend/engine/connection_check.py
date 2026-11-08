"""Read-only account connectivity checks with injected API functions.

No account IDs, credentials, or balances leave the diagnostics response.
No trade or transfer actions are accepted as inputs to this module.
"""
from datetime import datetime, timezone
from decimal import Decimal

def verify(configured, list_accounts, selected_account, load_portfolio):
    result = {
        'checkedAt': datetime.now(timezone.utc).isoformat(),
        'tradingEnabled': False,
        'backend': 'ready', 'broker': 'not_configured',
        'portfolio': 'not_checked', 'accountCount': 0,
        'selectedAccount': 'none',
        'nextStep': 'Add your Public API key in EdgePilot Settings → Public Brokerage Connection.',
    }
    if not configured:
        return result
    try:
        response = list_accounts()
        raw = response.get('accounts') if isinstance(response, dict) else None
        if not isinstance(raw, list):
            raise ValueError('Unexpected account list')
        valid_accounts = [a for a in raw if isinstance(a, dict) and a.get('accountId')]
        result.update(broker='verified', accountCount=len(valid_accounts),
                      nextStep='Choose your Public account in Settings, then run this check again.')
        if not selected_account:
            return result
        if not any(str(a['accountId']) == selected_account for a in valid_accounts):
            result.update(selectedAccount='not_available',
                          nextStep='Choose an account returned by Public.')
            return result
        result['selectedAccount'] = 'verified'
        try:
            p = load_portfolio(selected_account)
            if not isinstance(p, dict) or not isinstance(p.get('positions'), list):
                raise ValueError('Unexpected portfolio')
            value = Decimal(str(p.get('totalAccountValue')))
            if not value.is_finite() or value < 0:
                raise ValueError('Invalid portfolio total')
            result.update(portfolio='verified',
                          nextStep='Connection verified. Your dashboard can now load actual account data.')
        except Exception:
            result.update(portfolio='failed',
                          nextStep='Broker connection works, but the selected portfolio could not be read. Check permissions and retry.')
    except Exception:
        result.update(broker='failed',
                      nextStep='Public authentication or account discovery failed. Check the key and host configuration; do not paste credentials into chat.')
    return result
