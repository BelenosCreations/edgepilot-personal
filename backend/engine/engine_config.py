"""EdgePilot v0.2 isolated automation planning profiles.

Paper execution is separately and explicitly armed through the automation
controller; no config update ever triggers live broker orders.
"""
import json
import sqlite3
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone

DEFAULTS = {
    'auto': {
        'stock_allocation':'0.00','crypto_allocation':'0.00','max_per_trade':'0.00',
        'loss_stop':'0.00','profit_target':'0.00','rolling_loss_stop':'0.00',
        'stock_loss_stop':'0.00','crypto_loss_stop':'0.00','max_open':3,
        'stock_market':True,'crypto_market':True
    },
    'micro': {
        'allocation':'0.00','max_per_trade':'0.00','loss_stop':'0.00',
        'profit_target':'0.00','max_trades':10,'max_open':1,
        'cooldown_seconds':60,'stock_market':True,'prediction_market':True
    },
    'fifteen': {
        'allocation':'0.00','max_per_trade':'0.00','loss_stop':'0.00',
        'profit_target':'0.00','max_trades':10,'max_open':1,
        'cooldown_seconds':60,'minimum_seconds_left':120,'max_spread_pct':'5.00',
        'crypto_market':True,'commodity_market':False,'fx_market':False
    },
}
MONEY_FIELDS = {
    'auto':('stock_allocation','crypto_allocation','max_per_trade','loss_stop','profit_target',
            'rolling_loss_stop','stock_loss_stop','crypto_loss_stop'),
    'micro':('allocation','max_per_trade','loss_stop','profit_target'),
    'fifteen':('allocation','max_per_trade','loss_stop','profit_target','max_spread_pct')
}
BOOL_FIELDS = {
    'auto':('stock_market','crypto_market'),
    'micro':('stock_market','prediction_market'),
    'fifteen':('crypto_market','commodity_market','fx_market'),
}
INT_FIELDS = {
    'auto': {'max_open':(1,20)},
    'micro': {'max_trades':(1,100),'max_open':(1,10),'cooldown_seconds':(0,3600)},
    'fifteen': {'max_trades':(1,100),'max_open':(1,10),'cooldown_seconds':(0,3600),
                'minimum_seconds_left':(60,840)},
}

def connect(path):
    con=sqlite3.connect(path,timeout=30)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA busy_timeout=30000')
    return con

def setup(path):
    with connect(path) as con:
        con.execute('''CREATE TABLE IF NOT EXISTS engine_configs (
           engine TEXT PRIMARY KEY, config_json TEXT NOT NULL, updated_at TEXT NOT NULL
        )''')

def read(path, engine):
    if engine not in DEFAULTS:
        raise ValueError('Unknown EdgePilot engine')
    with connect(path) as con:
        row=con.execute('SELECT config_json,updated_at FROM engine_configs WHERE engine=?',
                        (engine,)).fetchone()
    values=DEFAULTS[engine].copy()
    if row:
        stored=json.loads(row['config_json'])
        values.update({k:stored[k] for k in values if k in stored})
    return {'engine':engine,'config':values,'configured':bool(row),
            'updatedAt':row['updated_at'] if row else None,'active':False,
            'mode':'configuration_only','liveTradingAvailable':False,
            'paperTradingAvailable':False}

def all_profiles(path):
    return {key:read(path,key) for key in DEFAULTS}

def _decimal(value,key,ceiling=100000):
    if isinstance(value,bool):
        raise ValueError(key+' must be a number')
    try:
        num=Decimal(str(value))
    except (InvalidOperation,TypeError,ValueError):
        raise ValueError(key+' must be a number')
    if not num.is_finite() or num<0 or num>Decimal(ceiling):
        raise ValueError(key+' is outside the permitted range')
    if num != num.quantize(Decimal('.01')):
        raise ValueError(key+' accepts at most two decimal places')
    return f'{num:.2f}'

def validate(engine, body):
    if engine not in DEFAULTS:
        raise ValueError('Unknown EdgePilot engine')
    if not isinstance(body,dict) or set(body)!=set(DEFAULTS[engine]):
        raise ValueError('Provide the complete known configuration; activation is unavailable')
    result={}
    for key in MONEY_FIELDS[engine]:
        result[key]=_decimal(body[key],key,100 if key=='max_spread_pct' else 100000)
    for key in BOOL_FIELDS[engine]:
        if not isinstance(body[key],bool):
            raise ValueError(key+' must be true or false')
        result[key]=body[key]
    for key,(minimum,maximum) in INT_FIELDS[engine].items():
        if isinstance(body[key],bool) or not isinstance(body[key],int) or not minimum<=body[key]<=maximum:
            raise ValueError(f'{key} must be an integer from {minimum} to {maximum}')
        result[key]=body[key]
    allocated=Decimal(result['stock_allocation'])+Decimal(result['crypto_allocation']) if engine=='auto' else Decimal(result['allocation'])
    per_trade=Decimal(result['max_per_trade'])
    if allocated and per_trade>allocated:
        raise ValueError('Maximum per-trade amount cannot exceed the planned allocation')
    if allocated and Decimal(result['loss_stop'])>allocated:
        raise ValueError('Loss stop cannot exceed the planned allocation')
    if engine=='auto' and allocated:
        for key in ('rolling_loss_stop','stock_loss_stop','crypto_loss_stop'):
            if Decimal(result[key])>allocated:
                raise ValueError(key+' cannot exceed total planned allocation')
    return result

def save(path,engine,body):
    values=validate(engine,body)
    stamp=datetime.now(timezone.utc).isoformat()
    with connect(path) as con:
        con.execute('''INSERT INTO engine_configs(engine,config_json,updated_at)
                       VALUES(?,?,?)
                       ON CONFLICT(engine) DO UPDATE SET
                        config_json=excluded.config_json,updated_at=excluded.updated_at''',
                    (engine,json.dumps(values,sort_keys=True),stamp))
    return read(path,engine)
