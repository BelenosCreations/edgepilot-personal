"""Bounded read-only 15-minute event discovery from Public's documented endpoints.

Quotes here come from event-details snapshots; they are NOT streaming quotes,
probability forecasts, order instructions, or evidence of a profitable strategy.
No order, preflight, or trade functions exist in this module.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

FREQUENCY = 'FIFTEEN_MINUTES'
ASSUMED_BUY_FEE = Decimal('0.02')  # Illustrative, not an actual Public preflight.
MAX_PAGES = 2
MAX_EVENTS = 8
SYMBOL_RE = re.compile(r'^[A-Za-z0-9._-]{10,170}$')


def timestamp(value):
    if not isinstance(value, str) or not value:
        raise ValueError('Missing market timestamp')
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('Invalid market timestamp') from None
    if dt.tzinfo is None:
        raise ValueError('Market timestamp must be timezone aware')
    return dt.astimezone(timezone.utc)


def decimal_price(value):
    if value is None or value == '':
        return None
    try:
        p = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return p if p.is_finite() and Decimal('0') <= p <= Decimal('1') else None


def side_contract(contracts, side):
    items = [x for x in contracts if isinstance(x, dict) and x.get('predictedOutcome') == side]
    if len(items) != 1:
        return None
    c = items[0]
    symbol = c.get('symbol', '')
    if not isinstance(symbol, str) or not SYMBOL_RE.fullmatch(symbol):
        return None
    bid, ask = decimal_price(c.get('bid')), decimal_price(c.get('ask'))
    if bid is None or ask is None or bid > ask:
        return None
    spread = ask - bid
    # Break-even if held to a binary settlement: ask + a hypothetical $0.02 buy fee.
    # Not a prediction and not a guaranteed brokerage fee quote.
    break_even = (ask + ASSUMED_BUY_FEE) * 100
    return {'symbol': symbol, 'bid': str(bid), 'ask': str(ask),
            'spread': str(spread),
            'illustrativeBreakEvenPct': str(break_even.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)),
            'illustrativeFeePerContract': str(ASSUMED_BUY_FEE)}


def candidate_summaries(response, now):
    if not isinstance(response, dict) or not isinstance(response.get('content'), list):
        raise ValueError('Invalid Public event summary response')
    results = []
    for item in response['content']:
        if not isinstance(item, dict) or item.get('resolved') is not False or item.get('halted') is True:
            continue
        symbol = item.get('eventSymbol', '')
        if not isinstance(symbol, str) or not SYMBOL_RE.fullmatch(symbol) or '15M-' not in symbol.upper():
            continue
        try:
            closing = timestamp(item.get('resolutionTime'))
        except ValueError:
            continue
        seconds = (closing - now).total_seconds()
        # Skip already closed or future windows; allow up to 60 s time jitter.
        if not 0 < seconds <= 960:
            continue
        results.append({'symbol': symbol, 'title': str(item.get('title') or '')[:140],
                        'close': closing, 'series': symbol.split('-', 1)[0]})
    return results


def parse_details(item, response, now):
    if not isinstance(response, dict) or response.get('eventSymbol') != item['symbol'] or response.get('resolved') is not False or response.get('halted') is True:
        raise ValueError('Event details do not match an open window')
    outcomes = response.get('outcomes')
    if not isinstance(outcomes, list) or len(outcomes) != 1 or not isinstance(outcomes[0], dict):
        raise ValueError('Expected one YES/NO outcome')
    outcome = outcomes[0]
    timeline = outcome.get('timeline')
    if not isinstance(timeline, dict):
        raise ValueError('Missing event timeline')
    opening, closing = timestamp(timeline.get('openTime')), timestamp(timeline.get('closeTime'))
    if not opening <= now < closing or not 840 <= (closing-opening).total_seconds() <= 960:
        raise ValueError('Not an active 15-minute window')
    if abs((closing-item['close']).total_seconds()) > 60:
        raise ValueError('Inconsistent close time')
    if outcome.get('trading') != 'BUY_AND_SELL' or outcome.get('state') == 'STATE_SETTLED':
        raise ValueError('Window is not open for buying and selling')
    contracts = outcome.get('contracts')
    if not isinstance(contracts, list):
        raise ValueError('Missing contract quotes')
    yes, no = side_contract(contracts, 'YES'), side_contract(contracts, 'NO')
    if yes is None or no is None:
        raise ValueError('Incomplete or crossed YES/NO quotes')
    remaining = max(0, int((closing-now).total_seconds()))
    warnings = []
    if remaining < 180: warnings.append('Close is near; displayed prices may already be stale')
    if max(Decimal(yes['spread']), Decimal(no['spread'])) > Decimal('0.05'):
        warnings.append('Wide quoted spread')
    return {'eventSymbol': item['symbol'], 'title': item['title'],
            'series': item['series'], 'target': str(outcome.get('title') or '')[:140],
            'openTime': opening.isoformat(), 'closeTime': closing.isoformat(),
            'secondsRemainingAtCapture': remaining, 'yes': yes, 'no': no,
            'warnings': warnings, 'readOnly': True}


def discover(pub, limit=MAX_EVENTS, now=None):
    """pub(method, api_path, body=None) is injected; all operations are read-only.

    Public's summary API uses POST for querying; it does not submit orders.
    Results are bounded to two pages and at most eight event-detail requests.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_EVENTS:
        raise ValueError('Invalid market limit')
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    results, seen, pages, next_token = [], set(), 0, None
    # This request shape follows Public's Get Event Summary guidance (both filter fields).
    while pages < MAX_PAGES:
        body = {'sortingMode': 'EXPIRATION', 'displayResolvedEvents': False,
                'filters': {'eventIds': [], 'frequencies': [FREQUENCY]}}
        if next_token:
            body['nextToken'] = next_token
        response = pub('POST', '/userapigateway/eventcontract/summary', body)
        pages += 1
        for candidate in candidate_summaries(response, now):
            if candidate['symbol'] not in seen:
                results.append(candidate)
                seen.add(candidate['symbol'])
        incoming = response.get('nextToken') if isinstance(response, dict) else None
        if not isinstance(incoming, str) or not incoming or incoming == next_token:
            next_token = None
            break
        next_token = incoming
        # Avoid potentially expensive extra pages once we have enough candidates.
        if len(results) >= limit:
            break
    results.sort(key=lambda x: (x['close'], x['symbol']))
    rows, errors = [], 0
    for candidate in results[:limit]:
        try:
            # No order endpoints, no preflight, and no storage of sensitive input.
            from urllib.parse import quote
            response = pub('GET', '/userapigateway/eventcontract/details/' + quote(candidate['symbol'], safe=''))
            rows.append(parse_details(candidate, response, now))
        except (ValueError, TypeError, KeyError):
            errors += 1
        except Exception:
            errors += 1
    return {'connected': True, 'readOnly': True, 'executionEnabled': False,
            'capturedAt': now.isoformat(), 'events': rows,
            'coverage': {'pagesFetched': pages, 'candidatesFound': len(results),
                         'detailsChecked': min(len(results), limit), 'skippedInvalid': errors,
                         'partialUniverse': bool(next_token) or pages == MAX_PAGES},
            'note': 'One-time event-details quote snapshots; not streaming prices. No independent win-probability model. Break-even assumes a hypothetical $0.02 buy fee per contract; actual costs require broker preflight. No trades placed.'}
