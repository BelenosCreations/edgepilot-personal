"""Conservative XNYS regular-session gate for experimental stock paper activity.

Uses a cached, locally calculated exchange calendar, including its documented
holidays and early closes. This is a SCHEDULE check, not a broker confirmation
of trading availability, halt status, or permission to execute real orders.
On missing/invalid calendar data the answer is UNKNOWN and paper activity must
fail closed. Research-only quote access remains independent of this gate.
"""
from datetime import datetime, timezone
from functools import lru_cache


@lru_cache(maxsize=1)
def _calendar():
    import exchange_calendars
    return exchange_calendars.get_calendar("XNYS")


def regular_session_state(instant=None):
    """Return OPEN, CLOSED or UNKNOWN; never guess that a session is open."""
    moment = instant if instant is not None else datetime.now(timezone.utc)
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        return "UNKNOWN"
    try:
        return "OPEN" if bool(_calendar().is_open_on_minute(moment.astimezone(timezone.utc))) else "CLOSED"
    except Exception:
        return "UNKNOWN"
