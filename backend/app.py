"""EdgePilot single-user personal backend. Prototype: no broker orders without explicit armed state.
Never expose this server directly to the internet; use TLS and an authenticated private tunnel.
"""
import os, time, secrets, hmac, sqlite3, json, uuid, threading, re
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import requests
from flask import Flask, jsonify, request, send_from_directory, redirect, g
from dotenv import load_dotenv
from engine import ledger, reconcile, order_audit, connection_check, session_auth, broker_credentials, fifteen_minute, engine_config, automation, automation_worker, observation_health, tenant_foundation, identity_auth, tenant_password_change, tenant_session_controls, tenant_registration, tenant_passkeys, account_scope, tenant_monitor_blueprint, tenant_watchlist, tenant_public_vault, tenant_public_live_readonly, staging_isolation, staging_operator, shared_storage_cutover, permanent_admin_invitations, solo_owner_portfolio
ROOT=Path(__file__).parent; load_dotenv(ROOT/'.env')
# Refuse unsafe isolated-test configuration before opening any database,
# owner credential store or background-worker state. Production is unchanged.
staging_isolation.validate(os.environ)
DB=Path(os.getenv('EDGE_DB_PATH',str(ROOT/'edgepilot.db')))
TENANT_DB=shared_storage_cutover.select_tenant_database(os.environ,DB)
TENANT_POLICY=shared_storage_cutover.permanent_identity_policy(os.environ,DB,TENANT_DB)
# A live paid /data deployment must never initialize tenant identities in the
# legacy owner file. Existing local/offline tests retain the historic default.
if (TENANT_DB == DB and DB.parent == shared_storage_cutover.PERSISTENT_ROOT
        and os.getenv('EDGE_TENANT_SCHEMA_PREPARE','false').lower()=='true'
        and os.getenv('EDGE_ISOLATED_STAGING','false').lower()!='true'):
    raise shared_storage_cutover.SharedStorageDenied('Live tenant schema requires isolated storage')
if TENANT_DB != DB:
    os.umask(0o077)  # SQLite DB, journal, WAL and temporary files must be private
    shared_storage_cutover.ensure_private_tenant_file(TENANT_DB)
DB.parent.mkdir(parents=True,exist_ok=True)
app=Flask(__name__,static_folder='static',static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # CSV/history research limit
BASE='https://api.public.com'; lock=threading.RLock(); cached_token=None; expires=0
FEE=Decimal('.02')
DEFAULT={'spend_cap':'100.00','protected_pct':'50','per_trade_cap':'5.00','daily_loss_cap':'5.00','autonomous':'0','live_armed':'0','account_id':'','interval_seconds':'60','holdings_scope':'allocated_only','balance_source':'public','independent_balance':'100.00','profile_label':'My EdgePilot','micro_enabled':'0','micro_stock_min_edge_pct':'0.50','micro_prediction_min_edge_pct':'3.00','micro_min_net_dollars':'0.05','micro_max_trades_day':'5','ai_enabled':'0','ai_monthly_budget_usd':'2.00','chatgpt_connector_enabled':'0'}
def D(v):
    try:
        x=Decimal(str(v)); assert x.is_finite(); return x
    except (InvalidOperation,AssertionError,TypeError): raise ValueError('Invalid numeric value')
def usd(v): return str(D(v).quantize(Decimal('.01')))
def database():
    c=sqlite3.connect(DB,timeout=20); c.row_factory=sqlite3.Row; return c
def init():
    with database() as c:
        c.execute('CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, account TEXT, symbol TEXT, event TEXT, side TEXT, qty INTEGER, limit_price TEXT, reserved TEXT, state TEXT, created TEXT, broker_reply TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS watch(id TEXT PRIMARY KEY,event TEXT,symbol TEXT,fair_pct TEXT,buy_below TEXT,sell_above TEXT,quantity INTEGER,enabled INTEGER DEFAULT 0)')
        c.execute('CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY AUTOINCREMENT,ts TEXT,message TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS account_snapshots(id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT NOT NULL, ts TEXT NOT NULL, total_value TEXT NOT NULL, buying_power TEXT NOT NULL)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_account_snapshots ON account_snapshots(account, ts)')
        for k,v in DEFAULT.items(): c.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',(k,v))
init()
ledger.setup(str(DB))
reconcile.setup(str(DB))
engine_config.setup(str(DB))
automation.setup(str(DB))
observation_health.setup(str(DB))
order_audit.setup(str(DB))
sessions=session_auth.SessionStore(str(DB))
sessions.setup()
credential_vault=broker_credentials.BrokerCredentialStore(str(DB))
credential_vault.setup()
# The new identity subsystem is deliberately independent of legacy sessions.
# Activation requires BOTH separate flags and an explicit migration review.
tenant_schema_enabled=os.getenv('EDGE_TENANT_SCHEMA_PREPARE','false').lower()=='true'
identity_auth_enabled=os.getenv('EDGE_IDENTITY_AUTH_ENABLED','false').lower()=='true'
tenant_password_change_enabled=os.getenv('EDGE_TENANT_PASSWORD_CHANGE_ENABLED','false').lower()=='true'
tenant_session_controls_enabled=os.getenv('EDGE_TENANT_SESSION_CONTROLS_ENABLED','false').lower()=='true'
tenant_signup_enabled=os.getenv('EDGE_TENANT_SIGNUP_ENABLED','false').lower()=='true'
tenant_passkeys_enabled=os.getenv('EDGE_TENANT_PASSKEYS_ENABLED','false').lower()=='true'
tenant_read_enabled=os.getenv('EDGE_TENANT_ACCOUNT_READS_ENABLED','false').lower()=='true'
tenant_monitor_preview_enabled=os.getenv('EDGE_TENANT_MONITOR_PREVIEW_ENABLED','false').lower()=='true'
tenant_watchlist_edit_enabled=os.getenv('EDGE_TENANT_WATCHLIST_EDIT_ENABLED','false').lower()=='true'
tenant_public_vault_enabled=os.getenv('EDGE_TENANT_PUBLIC_VAULT_ENABLED','false').lower()=='true'
tenant_public_read_enabled=os.getenv('EDGE_TENANT_PUBLIC_READONLY_ENABLED','false').lower()=='true'
# First limited live rollout may discover and link accounts, but never show balances.
tenant_public_discovery_only=os.getenv('EDGE_TENANT_PUBLIC_DISCOVERY_ONLY','false').lower()=='true'
permanent_admin_invites_enabled=os.getenv('EDGE_PERMANENT_OWNER_INVITES_ENABLED','false').lower()=='true'
# This has no effect unless separately opted in with all private, no-trade,
# discovery-only coexistence prerequisites checked by shared_storage_cutover.
family_invite_coexistence_enabled=shared_storage_cutover.family_invite_coexistence_policy(os.environ)
# A distinct, default-off solo research pilot. Never substitutes for the
# multi-member capability gates and never activates any execution path.
solo_owner_portfolio_enabled=solo_owner_portfolio.validate_pilot(os.environ,DB,TENANT_DB)
if permanent_admin_invites_enabled and not (
        (TENANT_POLICY['tenant_only'] or family_invite_coexistence_enabled)
        and identity_auth_enabled and tenant_signup_enabled):
    raise RuntimeError('Owner invitations require protected private identity registration')
if identity_auth_enabled and not tenant_schema_enabled:
    raise RuntimeError('Identity subsystem requires the prepared tenant schema')
if tenant_password_change_enabled and not identity_auth_enabled:
    raise RuntimeError('Password management requires identity authentication')
if tenant_session_controls_enabled and not identity_auth_enabled:
    raise RuntimeError('Tenant session controls require identity authentication')
if tenant_signup_enabled and not identity_auth_enabled:
    raise RuntimeError('Tenant registration requires identity authentication')
if tenant_passkeys_enabled and not identity_auth_enabled:
    raise RuntimeError('Passkeys require identity authentication')
if tenant_read_enabled and not identity_auth_enabled:
    raise RuntimeError('Tenant account reads require identity authentication')
if tenant_monitor_preview_enabled and not tenant_read_enabled:
    raise RuntimeError('Tenant monitor preview requires account-scoped identity reads')
if tenant_watchlist_edit_enabled and not tenant_monitor_preview_enabled:
    raise RuntimeError('Tenant watchlist editing requires inactive monitoring preview')
if tenant_public_vault_enabled and not identity_auth_enabled:
    raise RuntimeError('Tenant Public vault requires identity authentication')
if tenant_public_read_enabled and not (tenant_public_vault_enabled and tenant_read_enabled):
    raise RuntimeError('Tenant Public read-only API requires vault and tenant account reads')
if tenant_public_discovery_only and (not tenant_public_read_enabled
        or os.getenv('EDGE_PERMANENT_READONLY_PILOT_ENABLED','false').lower()!='true'
        or TENANT_POLICY['tenant_only']
        or (tenant_signup_enabled and not family_invite_coexistence_enabled)
        or tenant_passkeys_enabled
        or (permanent_admin_invites_enabled and not family_invite_coexistence_enabled)
        or os.getenv('EDGE_AUTOMATION_WORKER_ENABLED','false').lower()=='true'
        or os.getenv('ENABLE_LIVE_ORDERS','false').lower()=='true'):
    raise RuntimeError('Discovery-only Public pilot requires protected legacy coexistence and inactive execution')
identity_store=None
tenant_password_manager=None
tenant_session_manager=None
tenant_registration_store=None
permanent_admin_invites=None
tenant_passkey_store=None
tenant_account_store=None
tenant_monitor_planner=None
tenant_watchlist_editor=None
tenant_connection_vault=None
tenant_public_reader=None
if tenant_schema_enabled:
    tenant_foundation.setup(str(TENANT_DB))
    if identity_auth_enabled:
        identity_auth.setup(str(TENANT_DB))
        identity_store=identity_auth.IdentityStore(str(TENANT_DB))
        if tenant_password_change_enabled:
            tenant_password_change.setup(str(TENANT_DB))
            tenant_password_manager=tenant_password_change.TenantPasswordChange(str(TENANT_DB),identity_store)
        if tenant_session_controls_enabled:
            tenant_session_controls.setup(str(TENANT_DB))
            tenant_session_manager=tenant_session_controls.TenantSessionControls(str(TENANT_DB),identity_store)
        if tenant_signup_enabled:
            tenant_registration.setup(str(TENANT_DB))
            tenant_registration_store=tenant_registration.TenantRegistration(
                str(TENANT_DB), max_users=10 if (
                    TENANT_POLICY['tenant_only'] or family_invite_coexistence_enabled
                ) else None)
            if permanent_admin_invites_enabled:
                permanent_admin_invitations.setup(str(TENANT_DB))
                permanent_admin_invites=permanent_admin_invitations.PermanentAdminInvitations(
                    str(TENANT_DB),identity_store)
        if tenant_passkeys_enabled:
            tenant_passkeys.setup(str(TENANT_DB))
            tenant_passkey_store=tenant_passkeys.TenantPasskeyStore(
                str(TENANT_DB),identity_store,
                rp_id=os.getenv('EDGE_WEBAUTHN_RP_ID',''),
                expected_origin=os.getenv('EDGE_WEBAUTHN_ORIGIN',''),
                # Only the independently verified, fail-closed staging process
                # can enable Android's signed-app origin. Production keeps
                # accepting the original HTTPS origin exclusively.
                staging_android_cert_sha256=(
                    os.getenv('EDGE_ANDROID_CERT_SHA256','')
                    if os.getenv('EDGE_ISOLATED_STAGING','false').lower()=='true'
                    else TENANT_POLICY['android_signer_sha256']))
        if tenant_read_enabled:
            account_scope.setup(str(TENANT_DB))
            tenant_account_store=account_scope.AccountScopeStore(str(TENANT_DB),identity_store)
            if tenant_monitor_preview_enabled:
                tenant_monitor_planner=tenant_monitor_blueprint.DormantAccountMonitorPlanner(str(TENANT_DB))
                if tenant_watchlist_edit_enabled:
                    tenant_watchlist_editor=tenant_watchlist.TenantWatchlistEditor(str(TENANT_DB),identity_store)
        if tenant_public_vault_enabled:
            tenant_public_vault.setup(str(TENANT_DB))
            tenant_connection_vault=tenant_public_vault.TenantPublicVault(str(TENANT_DB),identity_store)
            if tenant_public_read_enabled:
                tenant_public_live_readonly.setup(str(TENANT_DB))
                tenant_public_reader=tenant_public_live_readonly.TenantPublicReadOnly(
                    str(TENANT_DB),identity_store,tenant_connection_vault)
def settings():
    with database() as c: return {r['k']:r['v'] for r in c.execute('SELECT * FROM settings')}
def put(k,v):
    with database() as c: c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(k,str(v)))
def log(msg):
    with database() as c: c.execute('INSERT INTO activity(ts,message) VALUES (?,?)',(datetime.now(timezone.utc).isoformat(),str(msg)[:500]))
def fail(msg,code=400): return jsonify({'error':str(msg)}),code
def valid_app_token(provided):
    expected=os.getenv('EDGE_APP_TOKEN','')
    return len(expected)>=32 and isinstance(provided,str) and hmac.compare_digest(expected,provided)


def same_origin_request():
    # Explicit same-origin browser API; do not permit cross-origin token exchange
    # or state changes. This service is designed for HTTPS, never HTTP hosting.
    origin=request.headers.get('Origin','')
    return (origin == 'https://' + request.host and
            request.headers.get('Sec-Fetch-Site','same-origin') not in ('cross-site','same-site'))


@app.before_request
def authenticate():
    if not request.path.startswith('/api/'):
        return
    # Permanent tenant-only mode retires all legacy owner API entry points,
    # including old login/session and global account/worker/order routes.
    # Identity cookies were already independent and cannot bypass this gate.
    if TENANT_POLICY['tenant_only'] and not request.path.startswith('/api/identity/'):
        return fail('Not found',404)
    # All state-changing endpoints, including login, require same-origin browser calls.
    if request.method in ('POST','PUT','PATCH','DELETE') and not same_origin_request():
        return fail('Same-origin request required',403)
    if request.path=='/api/staging/invitations':
        # Only the explicitly isolated synthetic operator bootstrap is public
        # to the legacy-login guard. The route still requires the separate
        # high-entropy operator capability, exact host and same-origin request.
        if os.getenv('EDGE_ISOLATED_STAGING','false').lower()!='true':
            return fail('Not found',404)
        return
    if request.path.startswith('/api/identity/'):
        # Identity account reads require a second independently enabled gate.
        if request.path=='/api/identity/admin/invitations' and not permanent_admin_invites_enabled:
            return fail('Not found',404)
        if request.path.startswith('/api/identity/sessions') and not tenant_session_controls_enabled:
            return fail('Not found',404)
        if request.path=='/api/identity/password/change' and not tenant_password_change_enabled:
            return fail('Not found',404)
        if request.path.startswith('/api/identity/accounts') and not tenant_read_enabled:
            return fail('Not found',404)
        if request.path.startswith('/api/identity/passkeys') and not tenant_passkeys_enabled:
            return fail('Not found',404)
        if request.path.startswith('/api/identity/public/connections') and not tenant_public_vault_enabled:
            return fail('Not found',404)
        if request.path.startswith('/api/identity/public/read/') and not tenant_public_read_enabled:
            return fail('Not found',404)
        # Identity sessions cannot authenticate any existing broker, settings,
        # monitoring or order API. All routes here remain disabled by default.
        if not identity_auth_enabled:
            return fail('Not found',404)
        if request.path=='/api/identity/login' and request.method=='POST':
            return
        if request.path=='/api/identity/register' and request.method=='POST':
            if not tenant_signup_enabled:
                return fail('Not found',404)
            return
        if request.path in ('/api/identity/passkeys/authenticate/options',
                            '/api/identity/passkeys/authenticate/finish') and request.method=='POST':
            return
        token=request.cookies.get(identity_auth.COOKIE_NAME,'')
        principal=identity_store.principal(token)
        if principal is None:
            return fail('Not authenticated',401)
        if request.method in ('POST','PUT','PATCH','DELETE'):
            if identity_store.principal(token,request.headers.get('X-Edge-Identity-CSRF','')) is None:
                return fail('Invalid request verification token',403)
        g.edge_identity=principal
        return
    if request.path=='/api/login':
        return
    session=request.cookies.get(session_auth.COOKIE_NAME,'')
    if not sessions.validate(session):
        return fail('Not authenticated',401)
    if request.method in ('POST','PUT','PATCH','DELETE'):
        if not sessions.validate(session,csrf=request.headers.get('X-Edge-CSRF','')):
            return fail('Invalid request verification token',403)


@app.after_request
def headers(r):
    r.headers['Cache-Control']='no-store'
    r.headers['X-Content-Type-Options']='nosniff'
    r.headers['Referrer-Policy']='no-referrer'
    r.headers['X-Frame-Options']='DENY'
    r.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
    r.headers['Content-Security-Policy']=(
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'self'")
    if request.is_secure or request.headers.get('X-Forwarded-Proto')=='https':
        r.headers['Strict-Transport-Security']='max-age=31536000'
    return r


@app.post('/api/login')
def login():
    # EDGE_APP_TOKEN is a login secret only; never reused as an API header.
    secret=os.getenv('EDGE_APP_TOKEN','')
    if len(secret)<32:
        return fail('EdgePilot login not configured on server',503)
    source=request.remote_addr or 'unknown'
    if sessions.blocked(source):
        resp=fail('Too many attempts. Try again later.',429)
        return resp
    payload=request.get_json(silent=True) or {}
    candidate=payload.get('accessToken') if isinstance(payload,dict) else None
    if not isinstance(candidate,str) or len(candidate)>512 or not valid_app_token(candidate):
        sessions.failed_login(source)
        return fail('Invalid login',401)
    sessions.successful_login(source)
    session, csrf, expires=sessions.issue()
    result=jsonify({'ok':True,'csrf':csrf,'expiresAt':datetime.fromtimestamp(expires,timezone.utc).isoformat()})
    result.set_cookie(session_auth.COOKIE_NAME,session,max_age=session_auth.SESSION_SECONDS,
                      secure=True,httponly=True,samesite='Strict',path='/')
    return result


# Separate identity-only endpoints: never authorize legacy owner operations.
# The feature is opt-in and there is intentionally no HTTP registration flow.
@app.post('/api/identity/login')
def identity_login():
    payload=request.get_json(silent=True)
    if not isinstance(payload,dict) or set(payload)!={'username','password'}:
        return fail('Invalid login',401)
    try:
        issued=identity_store.authenticate(
            payload['username'],payload['password'],request.remote_addr or 'unknown')
    except identity_auth.TooManyAttempts:
        return fail('Too many attempts. Try later.',429)
    if issued is None:
        return fail('Invalid login',401)
    response=jsonify({'ok':True,'csrf':issued['csrf'],
        'expiresAt':datetime.fromtimestamp(issued['expires_at'],timezone.utc).isoformat()})
    response.set_cookie(identity_auth.COOKIE_NAME,issued['token'],
        max_age=identity_auth.SESSION_SECONDS,
        secure=True,httponly=True,samesite='Strict',path='/')
    return response


# Invitation-only user creation. Never auto-logs in, selects a broker
# account, enables provider access, or assigns owner/operator permissions.
@app.post('/api/identity/register')
def identity_register():
    if not tenant_signup_enabled:
        return fail('Not found',404)
    payload=request.get_json(silent=True)
    if not isinstance(payload,dict) or set(payload)!={'invitation','username','password','displayName'}:
        return fail('Registration unavailable',400)
    try:
        result=tenant_registration_store.register(
            payload['invitation'],payload['username'],payload['password'],
            payload['displayName'],source=request.remote_addr or 'unknown')
        return jsonify(result),201
    except tenant_registration.RegistrationRateLimited:
        return fail('Registration temporarily unavailable',429)
    except tenant_registration.RegistrationDenied:
        return fail('Registration unavailable',400)


# Opt-in permanent owner invitation issuance. The verified member's role,
# session version and CSRF are rechecked inside the atomic tenant DB lock.
# The client cannot request another role, identify an owner, or submit a key.
@app.post('/api/identity/admin/invitations')
def identity_issue_private_invitation():
    if not permanent_admin_invites_enabled:
        return fail('Not found',404)
    if request.get_json(silent=True)!={}:
        return fail('Invitation request unavailable',400)
    try:
        return jsonify(permanent_admin_invites.issue(
            request.cookies.get(identity_auth.COOKIE_NAME,''),
            request.headers.get('X-Edge-Identity-CSRF',''))),201
    except permanent_admin_invitations.PermanentInvitationDenied:
        return fail('Owner invitation unavailable',403)


# Optional verified WebAuthn ceremonies. All four routes are separately
# disabled by default and use a fixed HTTPS relying party, never request.host.
@app.post('/api/identity/passkeys/register/options')
def identity_passkey_register_options():
    if request.get_json(silent=True)!={}:
        return fail('Passkey request unavailable',400)
    try:
        return tenant_passkey_store.begin_registration(
            request.cookies.get(identity_auth.COOKIE_NAME,''),
            request.headers.get('X-Edge-Identity-CSRF',''))
    except tenant_passkeys.PasskeyDenied:
        return fail('Passkey request unavailable',400)


@app.post('/api/identity/passkeys/register/finish')
def identity_passkey_register_finish():
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or set(body)!={'requestId','credential'}:
        return fail('Passkey verification failed',400)
    try:
        return tenant_passkey_store.finish_registration(
            request.cookies.get(identity_auth.COOKIE_NAME,''),
            request.headers.get('X-Edge-Identity-CSRF',''),
            body['requestId'],body['credential'])
    except tenant_passkeys.PasskeyDenied:
        return fail('Passkey verification failed',400)


@app.post('/api/identity/passkeys/authenticate/options')
def identity_passkey_auth_options():
    if request.get_json(silent=True)!={}:
        return fail('Passkey request unavailable',400)
    try:
        return tenant_passkey_store.begin_authentication()
    except tenant_passkeys.PasskeyDenied:
        return fail('Passkey request unavailable',400)


@app.post('/api/identity/passkeys/authenticate/finish')
def identity_passkey_auth_finish():
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or set(body)!={'requestId','credential'}:
        return fail('Passkey verification failed',400)
    try:
        issued=tenant_passkey_store.finish_authentication(
            body['requestId'],body['credential'])
    except tenant_passkeys.PasskeyDenied:
        return fail('Passkey verification failed',400)
    resp=jsonify({'ok':True,'csrf':issued['csrf'],
        'expiresAt':datetime.fromtimestamp(issued['expires_at'],timezone.utc).isoformat(),
        'scope':'identity_only_no_legacy_access'})
    resp.set_cookie(identity_auth.COOKIE_NAME,issued['token'],
        max_age=identity_auth.SESSION_SECONDS,
        secure=True,httponly=True,samesite='Strict',path='/')
    return resp


@app.get('/api/identity/passkeys')
def identity_passkey_status():
    try:
        return tenant_passkey_store.redacted_own_status(
            request.cookies.get(identity_auth.COOKIE_NAME,''),
            request.headers.get('X-Edge-Identity-CSRF',''))
    except tenant_passkeys.PasskeyDenied:
        return fail('Passkey status unavailable',404)


@app.delete('/api/identity/passkeys/<credential_id>')
def identity_passkey_revoke(credential_id):
    try:
        from webauthn import base64url_to_bytes
        if not isinstance(credential_id,str) or not 20<=len(credential_id)<=2750:
            return fail('Passkey unavailable',404)
        result=tenant_passkey_store.revoke_for_user(
            request.cookies.get(identity_auth.COOKIE_NAME,''),
            request.headers.get('X-Edge-Identity-CSRF',''),
            base64url_to_bytes(credential_id))
    except (tenant_passkeys.PasskeyDenied,ValueError,TypeError):
        return fail('Passkey unavailable',404)
    response=jsonify(result)
    response.delete_cookie(identity_auth.COOKIE_NAME,path='/',
        secure=True,httponly=True,samesite='Strict')
    return response


# Owner-only password rotation; user must prove their existing password.
# The change revalidates identity and CSRF inside the SQLite write lock,
# invalidates all of that member's sessions and does not affect passkeys
# or Public account ownership. This is NOT a forgotten-password recovery API.
@app.post('/api/identity/password/change')
def identity_password_change():
    if not tenant_password_change_enabled:
        return fail('Not found',404)
    payload=request.get_json(silent=True)
    if not isinstance(payload,dict) or set(payload)!={'currentPassword','newPassword'}:
        return fail('Password change unavailable',400)
    try:
        result=tenant_password_manager.change(
            request.cookies.get(identity_auth.COOKIE_NAME,''),
            request.headers.get('X-Edge-Identity-CSRF',''),
            payload['currentPassword'],payload['newPassword'])
    except tenant_password_change.PasswordChangeRateLimited:
        return fail('Password change temporarily unavailable',429)
    except tenant_password_change.PasswordChangeDenied:
        return fail('Password change unavailable',400)
    response=jsonify(result)
    response.delete_cookie(identity_auth.COOKIE_NAME,path='/',
                           secure=True,httponly=True,samesite='Strict')
    return response


# Independently gated identity-only session controls. No device fingerprint
# data, IP address, credential hash or bearer token is exposed to the browser.
@app.get('/api/identity/sessions')
def identity_list_sessions():
    if not tenant_session_controls_enabled:
        return fail('Not found',404)
    try:
        return tenant_session_manager.list_sessions(
            request.cookies.get(identity_auth.COOKIE_NAME,''),
            request.headers.get('X-Edge-Identity-CSRF',''))
    except tenant_session_controls.SessionControlDenied:
        return fail('Session management unavailable',403)


@app.delete('/api/identity/sessions/<session_id>')
def identity_revoke_other_session(session_id):
    if not tenant_session_controls_enabled:
        return fail('Not found',404)
    try:
        return tenant_session_manager.revoke_other(
            request.cookies.get(identity_auth.COOKIE_NAME,''),
            request.headers.get('X-Edge-Identity-CSRF',''),
            session_id)
    except tenant_session_controls.SessionTargetDenied:
        return fail('Other session unavailable',404)
    except tenant_session_controls.SessionControlDenied:
        return fail('Session management unavailable',403)


# Read-only tenant-account metadata and persisted research data.
# Requires a verified identity cookie, account ownership and an additional
# feature flag. These endpoints never call Public or the legacy global worker.
@app.get('/api/identity/accounts')
def identity_accounts():
    if not tenant_read_enabled:
        return fail('Not found',404)
    token=request.cookies.get(identity_auth.COOKIE_NAME,'')
    try:
        accounts=tenant_account_store.list_accounts(token)
        solo=bool(solo_owner_portfolio_enabled and
            solo_owner_portfolio.active_for_owner(TENANT_DB,g.edge_identity))
        return {'accounts':accounts,
                'readOnly':True,'brokerConnected':False,
                'discoveryOnlyPilot':tenant_public_discovery_only,
                'soloOwnerPortfolioAvailable':solo,
                'note':('Owner-only read-only Public portfolio available; other users remain discovery-only'
                        if solo else
                        'Verified Public account links; portfolio and execution disabled'
                        if tenant_public_discovery_only else
                        'Account-scoped storage only; no live broker requests or workers')}
    except account_scope.TenantAccessError:
        return fail('Not authenticated',401)


@app.get('/api/identity/accounts/<account_id>/summary')
def identity_account_summary(account_id):
    if not tenant_read_enabled:
        return fail('Not found',404)
    token=request.cookies.get(identity_auth.COOKIE_NAME,'')
    try:
        return tenant_account_store.account_summary(token,account_id)
    except account_scope.TenantAccessError:
        # Uniform 404 for missing, disabled, revoked or other user's account.
        return fail('Account unavailable',404)


# Preview ONLY: plans are deliberately disabled and contain no provider
# token, job execution, order capability, or global selected-account fallback.
@app.get('/api/identity/accounts/<account_id>/monitor/preview')
def identity_monitor_preview(account_id):
    if not tenant_monitor_preview_enabled:
        return fail('Not found',404)
    try:
        principal=g.edge_identity
        plan=tenant_monitor_planner.plan_for(principal['user_id'],account_id)
        return {'accountId':plan.account_id,'watchlist':list(plan.symbols),
                'mode':plan.mode,'scheduled':False,'workerActive':False,
                'brokerRequestsAllowed':False,'paperEnabled':False,
                'liveTradingEnabled':False,'readOnly':True,
                'simulatedPlanOnly':True}
    except (account_scope.TenantAccessError,tenant_monitor_blueprint.MonitorPlanningError):
        return fail('Account unavailable',404)


# Account-scoped watchlist settings are NOT a scheduler or worker activation.
# Authenticated identity and CSRF are independently revalidated under the
# database write lock before any change, including revocation-race protection.
@app.put('/api/identity/accounts/<account_id>/monitor/watchlist')
def identity_monitor_watchlist(account_id):
    if not tenant_watchlist_edit_enabled:
        return fail('Not found',404)
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or set(body)!={'symbols'}:
        return fail('Invalid watchlist',400)
    try:
        return tenant_watchlist_editor.replace(
            request.cookies.get(identity_auth.COOKIE_NAME,''),
            request.headers.get('X-Edge-Identity-CSRF',''),
            account_id,body['symbols'])
    except tenant_watchlist.WatchlistInvalid:
        return fail('Invalid watchlist',400)
    except tenant_watchlist.WatchlistDenied:
        return fail('Account unavailable',404)


# Identity-only Public key storage. Never sends a broker request and never
# returns plaintext or encrypted credentials to the client.
@app.get('/api/identity/public/connections')
def identity_public_connections():
    try:
        token=request.cookies.get(identity_auth.COOKIE_NAME,'')
        return {**tenant_connection_vault.list_connections(token),
                'discoveryOnlyPilot':tenant_public_discovery_only}
    except tenant_public_vault.TenantVaultDenied:
        return fail('Connection unavailable',404)


@app.post('/api/identity/public/connections')
def identity_public_save_connection():
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or set(body)!={'secret'}:
        return fail('Provide only the Public API secret',400)
    try:
        token=request.cookies.get(identity_auth.COOKIE_NAME,'')
        result=tenant_connection_vault.save(
            token,request.headers.get('X-Edge-Identity-CSRF',''),body['secret'])
        return jsonify(result),201
    except tenant_public_vault.TenantVaultDenied:
        return fail('Credential not accepted securely',400)


@app.post('/api/identity/public/connections/<connection_id>/rotate')
def identity_public_rotate_connection(connection_id):
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or set(body)!={'secret'}:
        return fail('Provide only the replacement Public API secret',400)
    try:
        token=request.cookies.get(identity_auth.COOKIE_NAME,'')
        return tenant_connection_vault.rotate(
            token,request.headers.get('X-Edge-Identity-CSRF',''),
            connection_id,body['secret'])
    except tenant_public_vault.TenantVaultDenied:
        return fail('Connection unavailable',404)


@app.delete('/api/identity/public/connections/<connection_id>')
def identity_public_delete_connection(connection_id):
    try:
        token=request.cookies.get(identity_auth.COOKIE_NAME,'')
        return tenant_connection_vault.disconnect(
            token,request.headers.get('X-Edge-Identity-CSRF',''),connection_id)
    except tenant_public_vault.TenantVaultDenied:
        return fail('Connection unavailable',404)


# Real read-only Public API access, separately flagged and identity-scoped.
# These endpoints can only list/verify accounts and sanitize portfolio reads.
# There is no path here for submitting orders or moving funds.
@app.get('/api/identity/public/read/connections/<connection_id>/accounts')
def identity_public_discover_accounts(connection_id):
    try:
        token=request.cookies.get(identity_auth.COOKIE_NAME,'')
        return tenant_public_reader.discover(token,connection_id)
    except (tenant_public_live_readonly.PublicReadUnavailable,
            tenant_public_vault.TenantVaultDenied):
        return fail('Public account discovery unavailable',404)


@app.post('/api/identity/public/read/connections/<connection_id>/accounts')
def identity_public_link_account(connection_id):
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or set(body)!={'accountId','label'}:
        return fail('Choose one verified Public account and label',400)
    try:
        token=request.cookies.get(identity_auth.COOKIE_NAME,'')
        return tenant_public_reader.link_verified(
            token,request.headers.get('X-Edge-Identity-CSRF',''),
            connection_id,body['accountId'],body['label'])
    except (tenant_public_live_readonly.PublicReadUnavailable,
            tenant_public_vault.TenantVaultDenied):
        return fail('Public account unavailable',404)


@app.get('/api/identity/public/read/accounts/<account_id>/portfolio')
def identity_public_account_portfolio(account_id):
    # Existing discovery-only rollout remains the default for EVERY identity.
    # A separately approved future single-owner pilot may read only that
    # owner-owned account, and immediately fails closed if another member is
    # enrolled, without deleting or changing any multi-user implementation.
    if tenant_public_discovery_only and not (
            solo_owner_portfolio_enabled and
            solo_owner_portfolio.active_for_owner(TENANT_DB,g.edge_identity)):
        return fail('Not found',404)
    try:
        token=request.cookies.get(identity_auth.COOKIE_NAME,'')
        portfolio=tenant_public_reader.portfolio(token,account_id)
        # A member might register during the external HTTPS request. Recheck
        # before returning ANY portfolio data so solo mode fails closed.
        if tenant_public_discovery_only and not (
                solo_owner_portfolio_enabled and
                solo_owner_portfolio.active_for_owner(TENANT_DB,g.edge_identity)):
            return fail('Not found',404)
        return portfolio
    except (tenant_public_live_readonly.PublicReadUnavailable,
            tenant_public_vault.TenantVaultDenied):
        return fail('Public portfolio unavailable',404)


@app.get('/api/identity/session')
def identity_session():
    token=request.cookies.get(identity_auth.COOKIE_NAME,'')
    rotated=identity_store.rotate_csrf(token)
    if rotated is None:
        return fail('Not authenticated',401)
    principal,csrf=rotated
    return {'ok':True,'csrf':csrf,
            'user':{'userId':principal['user_id'],
                    'label':principal['label'],'role':principal['role']},
            # Capability metadata only; the POST route still independently
            # authenticates the owner, CSRF and current role under DB lock.
            'privateInvitationsAvailable':bool(
                permanent_admin_invites_enabled and principal['role']=='owner'),
            'scope':'identity_only_no_broker_access'}


@app.post('/api/identity/logout')
def identity_logout():
    identity_store.revoke(request.cookies.get(identity_auth.COOKIE_NAME,''))
    response=jsonify({'ok':True})
    response.delete_cookie(identity_auth.COOKIE_NAME,path='/',
                           secure=True,httponly=True,samesite='Strict')
    return response


@app.get('/api/session')
def get_session():
    session=request.cookies.get(session_auth.COOKIE_NAME,'')
    csrf=sessions.renew_csrf(session)
    if csrf is None:
        return fail('Not authenticated',401)
    return {'ok':True,'csrf':csrf}


@app.post('/api/logout')
def logout():
    sessions.revoke(request.cookies.get(session_auth.COOKIE_NAME,''))
    response=jsonify({'ok':True})
    response.delete_cookie(session_auth.COOKIE_NAME,path='/',secure=True,httponly=True,samesite='Strict')
    return response
@app.get('/')
def index():
    # Keep the owner dashboard exactly as-is, but open the independent
    # identity interface by default on the staging-only Android package.
    if (os.getenv('EDGE_ISOLATED_STAGING','false').lower()=='true' or
            TENANT_POLICY['tenant_only']):
        return redirect('/account',code=302)
    return send_from_directory(ROOT/'static','index.html')


@app.get('/staging-operator')
def staging_operator_page():
    if (os.getenv('EDGE_ISOLATED_STAGING','false').lower()!='true' or
            request.host.lower()!=os.getenv('EDGE_WEBAUTHN_RP_ID','').lower() or
            not re.fullmatch(r'[a-f0-9]{64}',
                             os.getenv('EDGE_STAGING_OPERATOR_SHA256',''))):
        return fail('Not found',404)
    return send_from_directory(ROOT/'static','staging-operator.html')


@app.post('/api/staging/invitations')
def staging_operator_invites():
    # A synthetic-only owner provisioning path for a Free instance which
    # has no SSH/one-off shell. No public invitation issuance is possible.
    if (os.getenv('EDGE_ISOLATED_STAGING','false').lower()!='true' or
            request.host.lower()!=os.getenv('EDGE_WEBAUTHN_RP_ID','').lower() or
            os.getenv('EDGE_WEBAUTHN_ORIGIN','')!='https://'+request.host.lower() or
            request.get_json(silent=True)!={}):
        return fail('Not found',404)
    try:
        return jsonify(staging_operator.issue_two(
            str(DB),
            request.headers.get('X-Edge-Staging-Operator',''),
            os.getenv('EDGE_STAGING_OPERATOR_SHA256',''),
            source=request.remote_addr or 'unknown'
        ))
    except staging_operator.StagingOperatorDenied:
        return fail('Staging operator unavailable',403)

@app.get('/owner')
def owner_dashboard_page():
    # Public HTML shell only. All account and portfolio data still require
    # independent identity cookies, strict owner role, and scoped API checks.
    # Deliberately NOT a redirect to the legacy global-token dashboard.
    return send_from_directory(ROOT/'static','owner-dashboard.html')


@app.get('/account')
def identity_account_page():
    # Unprivileged same-origin UI; every API operation still requires verified
    # server-side identity/session/CSRF and independent feature gates.
    return send_from_directory(ROOT/'static','identity.html')

@app.get('/.well-known/assetlinks.json')
def android_passkey_asset_links():
    # Only a verified, configured app signing certificate may claim this
    # website for Android passkeys. Debug builds use per-run keys and are NOT
    # automatically trusted. A missing fingerprint never serves a fake link.
    fingerprint=os.getenv('EDGE_ANDROID_CERT_SHA256','').upper().strip()
    if not re.fullmatch(r'(?:[0-9A-F]{2}:){31}[0-9A-F]{2}',fingerprint):
        return fail('Not found',404)
    package='com.edgepilot.mobile'
    requested_package=os.getenv('EDGE_ANDROID_ASSOCIATION_PACKAGE','').strip()
    if (os.getenv('EDGE_ISOLATED_STAGING','false').lower()=='true' and
        not requested_package):
        return fail('Not found',404)
    if requested_package:
        # Isolated WebAuthn phone testing needs a separate installable package
        # and a distinct HTTPS host, never the legacy owner deployment.
        # These guards publish only a public app association, not an auth grant.
        rp=os.getenv('EDGE_WEBAUTHN_RP_ID','').strip().lower()
        if (requested_package!='com.edgepilot.mobile.staging' or
            os.getenv('EDGE_ISOLATED_STAGING','false').lower()!='true' or
            not rp.endswith('.belenoscreations.biz') or
            rp=='edgepilot.belenoscreations.biz' or
            request.host.lower()!=rp or
            os.getenv('EDGE_WEBAUTHN_ORIGIN','')!='https://'+rp or
            os.getenv('EDGE_DB_PATH','').startswith('/data/') or
            os.getenv('EDGE_APP_TOKEN','') or
            os.getenv('PUBLIC_API_SECRET','') or
            os.getenv('EDGE_AUTOMATION_WORKER_ENABLED','false').lower()!='false' or
            os.getenv('ENABLE_LIVE_ORDERS','false').lower()!='false' or
            os.getenv('EDGE_TENANT_PUBLIC_VAULT_ENABLED','false').lower()!='false' or
            os.getenv('EDGE_TENANT_PUBLIC_READONLY_ENABLED','false').lower()!='false'):
            return fail('Not found',404)
        package=requested_package
    return jsonify([{
      'relation':['delegate_permission/common.get_login_creds'],
      'target':{'namespace':'android_app',
                'package_name':package,
                'sha256_cert_fingerprints':[fingerprint]}
    }])
@app.get('/icon-192.png')
@app.get('/icon-512.png')
@app.get('/icon-maskable-512.png')
@app.get('/favicon.png')
@app.get('/apple-touch-icon.png')
def icon_file(): return send_from_directory(ROOT/'static',request.path.lstrip('/'))
@app.get('/manifest.webmanifest')
def manifest(): return send_from_directory(ROOT/'static','manifest.webmanifest')
@app.get('/service-worker.js')
def sw(): return send_from_directory(ROOT/'static','service-worker.js')
@app.get('/healthz')
def healthz():
    # Unauthenticated liveness probe: no account, secret, or permission details.
    return {'ok':True}

@app.get('/api/health')
def health(): return {'ok':True,'version':'0.2.40-two-user-synthetic-acceptance-only','time':datetime.now(timezone.utc).isoformat()}
def token():
    global cached_token,expires
    with lock:
        if cached_token and time.time()<expires-120:return cached_token
        api_secret=credential_vault.secret_for_broker()
        r=requests.post(BASE+'/userapiauthservice/personal/access-tokens',json={'secret':api_secret,'validityInMinutes':60},timeout=20);r.raise_for_status()
        cached_token=r.json()['accessToken'];expires=time.time()+3600;return cached_token
def pub(method,path,body=None):
    assert path.startswith('/userapigateway/');r=requests.request(method,BASE+path,json=body,headers={'Authorization':'Bearer '+token(),'Content-Type':'application/json'},timeout=20)
    if not r.ok:raise ValueError(f'Public HTTP {r.status_code}. Check your account permissions and API configuration.')
    return r.json()
def portfolio(account): return pub('GET','/userapigateway/trading/'+quote(account,safe='')+'/portfolio/v2')
def selected_account():
    s=settings();acct=s['account_id'];
    if not acct:raise ValueError('Select a Public account in Settings')
    return acct
def broker_summary():
    p=portfolio(selected_account())
    balance=D(p.get('totalAccountValue') or '0');bp=D((p.get('buyingPower') or {}).get('cashOnlyBuyingPower') or '0')
    # Conservatively count ALL account positions at current value and all open orders' price commitments.
    positions=sum((max(D(v.get('currentValue') or '0'),D('0')) for v in p.get('positions',[])),D('0'))
    pending=D('0')
    for o in p.get('orders',[]):
        if o.get('status') in ('NEW','PENDING','PARTIALLY_FILLED','ACCEPTED','OPEN') and o.get('side')=='BUY':
            try:pending+=D(o.get('quantity') or '0')*D(o.get('limitPrice') or '1')
            except ValueError:pending+=D('999999')
    # Local unverified orders are also counted to prevent duplicate spending; conservative double counting permitted.
    with database() as c:
        local=sum((D(r['reserved']) for r in c.execute("SELECT reserved FROM orders WHERE state IN ('SUBMITTED_UNVERIFIED','PENDING','FILLED') AND side='BUY'")),D('0'))
    s=settings();pct=D(s['protected_pct']);cap=D(s['spend_cap'])
    independent=s['balance_source']=='independent'
    assigned=D(s['independent_balance']) if independent else balance
    # Independent funds are a virtual allocation, not a separate brokerage subaccount.
    # Fail closed if outside transactions or losses reduce the real account beneath the allocation.
    requires_reset=independent and balance<assigned
    calculation_balance=assigned if independent else balance
    max_at_risk=max(D('0'),min(cap,calculation_balance*(D('100')-pct)/100))
    remaining=max(D('0'),min(max_at_risk-positions-pending-local,bp))
    if requires_reset:remaining=D('0')
    return {'balance':usd(balance),'effectiveBalance':usd(calculation_balance),'balanceSource':s['balance_source'],
            'independentBalance':usd(assigned) if independent else None,'requiresBalanceReset':requires_reset,
            'balanceAlert':('Public balance fell below the assigned EdgePilot balance. Choose a new allocation before any new buys.' if requires_reset else None),
            'cashBuyingPower':usd(bp),'positionsExposure':usd(positions),'brokerOpenBuyExposure':usd(pending),
            'unreconciledLocal':usd(local),'protectedAmount':usd(calculation_balance*pct/100),
            'riskBudget':usd(max_at_risk),'remainingToRisk':usd(remaining),'accountId':selected_account(),
            'positionCount':len(p.get('positions',[])),
            'holdings':[{'symbol':str((v.get('instrument') or {}).get('symbol') or v.get('symbol') or 'Unknown')[:70],
                         'value':usd(v.get('currentValue') or '0'),
                         'quantity':str(v.get('quantity') or '0')} for v in p.get('positions',[])][:100]}
@app.get('/api/broker/credentials/status')
def broker_credential_status():
    """Credential metadata only. Never serialize a secret or ciphertext."""
    return jsonify(credential_vault.status())


@app.post('/api/broker/credentials')
def save_broker_credential():
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or set(body) != {'secret'}:
        return fail('Provide only the Public API secret',400)
    try:
        with lock:
            credential_vault.save(body['secret'])
            global cached_token, expires
            cached_token=None; expires=0
            # Changing identities invalidates existing account association and disarms trading.
            put('account_id','')
            put('live_armed','0')
            log('Public connection credential updated in encrypted settings vault')
        return {'ok':True,'configured':True,'message':'Saved securely. Use Test connection to verify access.'}
    except broker_credentials.CredentialError as exc:
        return fail(str(exc),503 if 'encryption' in str(exc).lower() else 400)


@app.delete('/api/broker/credentials')
def disconnect_broker_credential():
    with lock:
        credential_vault.clear()
        global cached_token, expires
        cached_token=None; expires=0
        put('account_id','')
        put('live_armed','0')
        log('Public connection credential disconnected')
    return {'ok':True,'configured':False,'message':'Public connection disconnected'}


@app.get('/api/connection/verify')
def verify_connection():
    """Authenticated read-only Public API connection check. Never leaks credentials."""
    check=connection_check.verify(
        configured=credential_vault.status()['usable'],
        list_accounts=lambda:pub('GET','/userapigateway/trading/account'),
        selected_account=settings().get('account_id',''),
        load_portfolio=portfolio,
    )
    return jsonify(check)

# v0.19.16 -- configuration-only independent trading engines.
# These routes deliberately contain no order, activation, or paper-fill actions.
@app.get('/api/engines/config')
def engine_profiles():
    return {'profiles':engine_config.all_profiles(str(DB)),
            'activationAvailable':True,'paperTradingAvailable':True,
            'warning':'Observe and experimental stock paper modes can be started separately. Live brokerage order execution remains unavailable.'}

@app.post('/api/engines/<engine>/config')
def save_engine_profile(engine):
    try:
        payload=request.get_json(silent=True)
        with lock:
            # Always pause before replacing limits so a racing worker cannot
            # accept a new entry using partially changed risk preferences.
            automation.control(str(DB),'pause',engine)
            updated=engine_config.save(str(DB),engine,payload)
            put('live_armed','0')
            log('Updated '+engine+' plan; engine paused pending manual restart')
        return {'ok':True,'profile':updated,'activationAvailable':True,'liveTradingAvailable':False}
    except (ValueError,TypeError) as exc:
        return fail(exc,400)

# v0.2 master automation commands. These never place a live broker order.
@app.get('/api/automation/status')
def automation_status():
    result=automation.status(str(DB))
    result['observationHealth']=observation_health.report(str(DB))
    result['workerConfigured']=os.getenv('EDGE_AUTOMATION_WORKER_ENABLED','false').lower()=='true'
    return result

@app.post('/api/automation/config')
def automation_config():
    try:
        with lock:
            result=automation.configure(str(DB),request.get_json(silent=True))
            put('live_armed','0')
        return result
    except (ValueError,TypeError) as exc:
        return fail(exc,400)

@app.post('/api/automation/<engine>/<action>')
def automation_command(engine,action):
    if engine not in automation.ENGINES or action not in ('start','pause','stop'):
        return fail('Unsupported trading engine or control',400)
    try:
        data=request.get_json(silent=True) or {}
        m=automation.master(str(DB))
        confirmation='START PAPER' if m['mode']=='paper' else 'START OBSERVE'
        if action=='start' and data.get('confirmation')!=confirmation:
            return fail('Explicit '+confirmation+' confirmation required',400)
        if action=='start' and os.getenv('EDGE_AUTOMATION_WORKER_ENABLED','false').lower()!='true':
            return fail('Server-side market observer is not running; automation cannot start',503)
        if action=='start' and not settings().get('account_id'):
            return fail('Select a verified Public account first for read-only market quotes',400)
        if action=='start':
            last_heartbeat=automation.master(str(DB)).get('worker_heartbeat')
            if not last_heartbeat or (datetime.now(timezone.utc)-datetime.fromisoformat(last_heartbeat)).total_seconds()>180:
                return fail('Automation worker heartbeat is missing or stale; cannot start',503)
        with lock:
            result=automation.control(str(DB),action,engine)
            put('live_armed','0')
        return result
    except (ValueError,TypeError) as exc:
        return fail(exc,400)

@app.post('/api/automation/emergency/reset')
def automation_emergency_reset():
    if (request.get_json(silent=True) or {}).get('confirmation')!='RESET EMERGENCY':
        return fail('Explicit reset confirmation required',400)
    try:
        with lock:return automation.control(str(DB),'reset_emergency')
    except ValueError as exc:return fail(exc,400)

@app.get('/api/funds/transfer-history')
def funds_transfer_history():
    """Read-only, best-effort hints from an already-captured Public sync journal.
    Not a banking/withdrawable-funds API, and never transfers money.
    """
    account=settings().get('account_id','')
    if not account:
        return {'entries':[],'historyCaptured':False,
                'warning':'Select your Public account first. Transfers are completed in Public.'}
    with database() as c:
        run=c.execute('SELECT ts FROM sync_runs WHERE account=? ORDER BY id DESC LIMIT 1',(account,)).fetchone()
        rows=c.execute('''SELECT timestamp,type,subtype FROM sync_transactions
                          WHERE account=? ORDER BY first_seen DESC LIMIT 500''',(account,)).fetchall()
    entries=[]
    for r in rows:
        name=(str(r['type'] or '')+' '+str(r['subtype'] or '')).upper()
        if 'DEPOSIT' in name:
            label='Deposit-like history entry'
        elif 'WITHDRAW' in name:
            label='Withdrawal-like history entry'
        elif 'TRANSFER' in name or 'ACH' in name:
            label='Transfer-like history entry'
        else:
            continue
        entries.append({'timestamp':str(r['timestamp'] or '')[:40],
                        'label':label,'verifiedBankTransfer':False})
        if len(entries)==25:break
    return {'entries':entries,'historyCaptured':bool(run),
            'lastSync':run['ts'] if run else None,
            'warning':'Public app History is authoritative. These entries may be incomplete or non-bank transfers. Withdrawable cash and transfer status are not available through this endpoint.'}

@app.get('/api/accounts')
def accounts():
    try:return {'accounts':pub('GET','/userapigateway/trading/account').get('accounts',[])}
    except Exception as e:return fail(e,502)
@app.get('/api/dashboard')
def dashboard():
    try:
        b=broker_summary();err=None
        # Store broker-verified snapshots; no historical values are synthesized.
        with database() as c:
            last=c.execute('SELECT ts FROM account_snapshots WHERE account=? ORDER BY id DESC LIMIT 1',(b['accountId'],)).fetchone()
            now=datetime.now(timezone.utc)
            if not last or (now-datetime.fromisoformat(last['ts'])).total_seconds()>=60:
                c.execute('INSERT INTO account_snapshots(account,ts,total_value,buying_power) VALUES (?,?,?,?)',
                          (b['accountId'],now.isoformat(),b['balance'],b['cashBuyingPower']))
    except Exception as e:b=None;err=str(e)
    with database() as c:
        orders=[dict(r) for r in c.execute('SELECT * FROM orders ORDER BY created DESC LIMIT 30')]
        activity=[dict(r) for r in c.execute('SELECT * FROM activity ORDER BY id DESC LIMIT 25')]
        watch=[dict(r) for r in c.execute('SELECT * FROM watch ORDER BY rowid DESC')]
    return {'settings':settings(),'broker':b,'brokerError':err,'orders':orders,'watch':watch,'activity':activity,'liveTradingAvailable':False}
@app.get('/api/performance/history')
def performance_history():
    acct=settings().get('account_id','')
    if not acct: return {'account':'','points':[],'warning':'Select a Public account to collect real balance history.'}
    with database() as c:
        rows=c.execute('SELECT ts,total_value,buying_power FROM account_snapshots WHERE account=? ORDER BY ts DESC LIMIT 2500',(acct,)).fetchall()
    return {'account':acct, 'points':[{'ts':r['ts'],'value':r['total_value'],'buyingPower':r['buying_power']} for r in reversed(rows)],
            'warning':'Account value changes include deposits, withdrawals and outside trades. Do not interpret as investment-only P&L.'}

@app.get('/api/ledger')
def ledger_read():
    s=settings()
    return ledger.summary(str(DB),s['account_id'] or None)

@app.post('/api/settings')
def update_settings():
    body=request.get_json(silent=True) or {}
    allowed={'spend_cap','protected_pct','per_trade_cap','daily_loss_cap','account_id','autonomous','live_armed','holdings_scope','balance_source','independent_balance','profile_label','micro_enabled','micro_stock_min_edge_pct','micro_prediction_min_edge_pct','micro_min_net_dollars','micro_max_trades_day','ai_enabled','ai_monthly_budget_usd','chatgpt_connector_enabled'}
    if set(body)-allowed-{'confirmation'}:return fail('Unsupported setting')
    try:
        with lock:
            original=settings()
            for k,v in body.items():
                if k in ('spend_cap','per_trade_cap','daily_loss_cap') and not D('0')<D(v)<=D('100000'):raise ValueError(k+' must be positive')
                if k=='protected_pct' and not D('0')<=D(v)<=D('99'):raise ValueError('Protection must be 0–99%')
                if k=='account_id':
                    if not str(v).strip() or len(str(v))>100:raise ValueError('Invalid account')
                    # Confirm ownership before setting account
                    valid={str(a.get('accountId')) for a in pub('GET','/userapigateway/trading/account').get('accounts',[])}
                    if str(v) not in valid:raise ValueError('Account not found among your Public accounts')
                if k=='profile_label' and (not str(v).strip() or len(str(v))>48):raise ValueError('Profile label must be 1–48 characters')
                if k=='holdings_scope' and str(v) not in ('allocated_only','existing_allowed'):raise ValueError('Invalid holdings scope')
                if k=='balance_source' and str(v) not in ('public','independent'):raise ValueError('Invalid balance source')
                if k=='independent_balance' and not D('0')<D(v)<=D('100000000'):raise ValueError('Independent balance must be positive')
                if k in ('micro_stock_min_edge_pct','micro_prediction_min_edge_pct') and not D('0')<=D(v)<=D('50'):raise ValueError('Edge threshold must be 0–50%')
                if k=='micro_min_net_dollars' and not D('0')<=D(v)<=D('100'):raise ValueError('Minimum net dollars must be $0–$100')
                if k=='micro_max_trades_day' and (str(v) not in ('1','2','3','5','10','20','50')):raise ValueError('Invalid daily micro-trade limit')
                if k in ('ai_enabled','chatgpt_connector_enabled') and str(v) not in ('0','1'):raise ValueError('AI setting must be 0 or 1')
                if k=='ai_monthly_budget_usd' and not D('0')<=D(v)<=D('1000'):raise ValueError('Monthly AI budget must be between $0 and $1000')
                if k=='chatgpt_connector_enabled' and str(v)=='1':raise ValueError('ChatGPT connector not deployed; cannot enable an unavailable connection')
                if k=='micro_enabled' and str(v) not in ('0','1'):raise ValueError('Micro-trading toggle must be 0 or 1')
                if k in ('autonomous','live_armed') and str(v) not in ('0','1'): raise ValueError('Switch must be 0 or 1')
                if k=='live_armed' and str(v)=='1':
                    raise ValueError('Live orders unavailable in family beta: complete broker reconciliation and loss-limit enforcement first')
                    if body.get('confirmation')!='ARM LIVE TRADING':raise ValueError('Explicit live confirmation required')
                if k=='autonomous' and str(v)=='1' and body.get('confirmation')!='ENABLE AUTONOMY':raise ValueError('Explicit autonomous confirmation required')
            # Validate effective allocation against broker data before saving, even when
            # switching source without editing the assigned amount.
            new_source=str(body.get('balance_source',original['balance_source']))
            new_allocation=D(body.get('independent_balance',original['independent_balance']))
            new_account=str(body.get('account_id',original['account_id']))
            if new_source=='independent':
                if not new_account:raise ValueError('Select your Public account before choosing independent balance')
                real= D(portfolio(new_account).get('totalAccountValue') or '0')
                if new_allocation>real:raise ValueError('Independent balance cannot exceed current Public balance ($'+usd(real)+')')
            # no partial writes on errors, and confirmations aren't saved
            for k,v in body.items():
                if k!='confirmation':put(k,v)
            if any(k in body for k in ('spend_cap','protected_pct','account_id','holdings_scope','balance_source','independent_balance','micro_enabled','micro_stock_min_edge_pct','micro_prediction_min_edge_pct','micro_min_net_dollars','micro_max_trades_day','ai_enabled','ai_monthly_budget_usd','chatgpt_connector_enabled')):
                # keep automation locked after changing envelope
                put('live_armed','0')
            log('Settings changed: '+', '.join(k for k in body if k!='confirmation'))
        return {'ok':True,'settings':settings()}
    except Exception as e:return fail(e)
# Confirmation field may be present in settings body.
@app.get('/api/orders/audit')
def audit_orders_status():
    account=selected_account()
    return order_audit.overview(str(DB),account)

@app.post('/api/orders/audit/run')
def audit_orders_run():
    # Only lookup broker order IDs already observed by the local Public snapshot,
    # or locally submitted orders (when a future audited adapter exists).
    # Do not query the entire global order history and assume it is ours.
    try:
        with lock:
            account=selected_account()
            snapshot=portfolio(account)
            raw=snapshot.get('orders')
            if not isinstance(raw,list):raise ValueError('Public portfolio returned no reliable orders list')
            ids=set()
            for order in raw:
                oid=str(order.get('orderId') or '').strip()
                if oid:ids.add(oid)
            with database() as c:
                for r in c.execute('SELECT order_id FROM observed_orders WHERE account=?',(account,)):
                    ids.add(r['order_id'])
                for r in c.execute('SELECT order_id FROM submitted_order_provenance WHERE account=?',(account,)):
                    ids.add(r['order_id'])
            if len(ids)>500:raise ValueError('Too many broker orders for a single audit; requires paginated review')
            # Fetch full order details before a single atomic audit commit.
            orders=[]
            for oid in sorted(ids):
                orders.append(pub('GET','/userapigateway/trading/'+quote(account,safe='')+'/order/v2/'+quote(oid,safe='')))
            result=order_audit.observe(str(DB),account,orders,complete=True)
            return {'ok':True,**result}
    except Exception as e:return fail(e,502)

@app.get('/api/sync/status')
def sync_status():
    acct=settings().get('account_id','')
    if not acct:return {'lastSync':None,'alerts':[],'openAlertCount':0,'warning':'Select account first'}
    return reconcile.overview(str(DB),acct)

@app.post('/api/sync/run')
def sync_run():
    """Explicit on-demand sync. Fetch all history pages before committing any changes.
    No raw credentials or broker payloads are returned to the Android UI.
    """
    try:
        with lock:
            acct=selected_account()
            # Read current portfolio first, then all history pages. API may be eventually consistent.
            snapshot=portfolio(acct)
            tx=[]; page_token=None; pages=0;seen=set()
            while True:
                pages+=1
                if pages>100:raise ValueError('History pagination limit exceeded; sync not committed')
                from urllib.parse import urlencode
                params={'pageSize':100}
                if page_token:params['nextToken']=page_token
                data=pub('GET','/userapigateway/trading/'+quote(acct,safe='')+'/history?'+urlencode(params))
                chunk=data.get('transactions')
                if not isinstance(chunk,list):raise ValueError('Invalid transaction history response')
                tx.extend(chunk)
                nxt=data.get('nextToken')
                if not nxt:break
                if nxt in seen:raise ValueError('Repeated pagination token; sync not committed')
                seen.add(nxt);page_token=nxt
            result=reconcile.reconcile(str(DB),acct,snapshot,tx,pages=pages)
            log('Read-only Public sync: '+str(result['importedTransactions'])+' new transactions; '+str(result['openAlerts'])+' alerts')
            return result
    except Exception as exc:return fail('Synchronization failed: '+str(exc),502)

@app.post('/api/sync/alerts/<int:alert_id>/acknowledge')
def sync_acknowledge(alert_id):
    try:
        if not reconcile.dismiss(str(DB),selected_account(),alert_id):return fail('Alert not found',404)
        return {'ok':True,'note':'Alert acknowledged only; no order, repurchase, or attribution changes made.'}
    except Exception as exc:return fail(exc)

@app.post('/api/sync/alerts/acknowledge-all')
def sync_acknowledge_all():
    """Bulk acknowledgement is informational only; order permissions remain unchanged."""
    try:
        with lock:
            acct=selected_account()
            count=reconcile.dismiss_all(str(DB),acct)
            if count:
                log('Acknowledged '+str(count)+' Public synchronization alerts; no trading actions')
            return {'ok':True,'acknowledgedCount':count,'openAlertCount':0,
                    'note':'Sync alerts acknowledged only; transaction records and audit history retained. No order, repurchase or attribution changes.'}
    except Exception as exc:return fail(exc)

@app.get('/api/markets/15-minute')
def fifteen_minute_markets():
    """One-shot, bounded, authenticated read-only Public 15-minute market scan."""
    try:
        limit = int(request.args.get('limit', '8'))
        if not 1 <= limit <= fifteen_minute.MAX_EVENTS:
            return fail('Limit must be 1 through 8', 400)
        if not credential_vault.status()['usable']:
            return {'connected': False, 'readOnly': True, 'executionEnabled': False,
                    'events': [], 'note': 'Connect Public in Settings to retrieve active 15-minute windows.'}
        return fifteen_minute.discover(pub, limit=limit)
    except (ValueError, TypeError):
        return fail('Invalid scanner parameters', 400)
    except Exception:
        # Do not serialize or log credential-bearing upstream error bodies.
        app.logger.warning('Public 15-minute market scan unavailable')
        return fail('15-minute market data unavailable; no trades placed.', 502)

@app.get('/api/markets')
def markets():
    try:
        raw=pub('POST','/userapigateway/eventcontract/summary',{'sortingMode':'VOLUME','displayResolvedEvents':False})
        return {'events':[{'symbol':e.get('eventSymbol'),'title':e.get('title'),'volume':e.get('volume')} for e in raw.get('content',[]) if not e.get('resolved')][:100]}
    except Exception as e:return fail(e,502)
@app.get('/api/event/<path:event>')
def event_details(event):
    if '/' in event or len(event)>180:return fail('Invalid symbol')
    try:return pub('GET','/userapigateway/eventcontract/details/'+quote(event,safe=''))
    except Exception as e:return fail(e,502)
def order_payload(symbol,qty,price,side):
    return {'instrument':{'symbol':symbol,'type':'EVENTCONTRACT'},'orderSide':side,'orderType':'LIMIT','expiration':{'timeInForce':'DAY'},'quantity':str(qty),'limitPrice':usd(price),'useMargin':False}
def validate_order(body):
    side=str(body.get('side','BUY'));account=selected_account()
    if side not in ('BUY','SELL'):raise ValueError('Invalid order side')
    qty=int(body.get('qty',0));price=D(body.get('price',0))
    symbol=str(body.get('symbol',''));event=str(body.get('event',''))
    if not 1<=qty<=50 or not D('.01')<=price<=D('.99') or price.as_tuple().exponent < -2:raise ValueError('Invalid quantity/price')
    if not symbol.startswith(('KALSHI.','PMUS.','CDNA.')) or not event:raise ValueError('Invalid contract/event')
    details=pub('GET','/userapigateway/eventcontract/details/'+quote(event,safe=''))
    if details.get('halted') or details.get('resolved'):raise ValueError('Halted/resolved')
    matches=[x for o in details.get('outcomes',[]) if o.get('state')=='STATE_OPEN' and o.get('trading')=='BUY_AND_SELL' for x in o.get('contracts',[]) if x.get('symbol')==symbol]
    if not matches:raise ValueError('Contract not tradeable')
    quote_price=D(matches[0].get('ask' if side=='BUY' else 'bid') or '0')
    if quote_price<=0 or (side=='BUY' and quote_price>price) or (side=='SELL' and quote_price<price):raise ValueError('Quote outside limit; refresh price')
    exposure=price*qty+FEE*qty
    risk=broker_summary()
    if side=='BUY':
        if risk['requiresBalanceReset']:raise ValueError('Public balance below independent allocation. Update the independent balance before placing buys.')
        if exposure>D(settings()['per_trade_cap']):raise ValueError('Per trade cap exceeded')
        if exposure>D(risk['remainingToRisk']):raise ValueError('Protected balance / spending cap / buying power exceeded')
    else:
        p=portfolio(account);held=sum((D(x.get('quantity') or '0') for x in p.get('positions',[]) if (x.get('instrument') or {}).get('symbol')==symbol),D('0'))
        if held<qty:raise ValueError('Cannot sell more contracts than broker shows as held')
    pre=pub('POST','/userapigateway/trading/'+quote(account,safe='')+'/preflight/single-leg',{**order_payload(symbol,qty,price,side),'validateOrder':True})
    cost=D(pre.get('estimatedCost') or '0')
    if side=='BUY' and (cost<=0 or cost>D(settings()['per_trade_cap']) or cost>D(risk['remainingToRisk'])):raise ValueError('Preflight cost exceeds risk limits')
    return {'payload':order_payload(symbol,qty,price,side),'preflight':pre,'cost':usd(cost if cost>0 else exposure),'account':account,'symbol':symbol,'event':event,'side':side,'qty':qty,'price':usd(price)}
@app.post('/api/order/preview')
def preview():
    try:
        with lock:return validate_order(request.get_json(silent=True) or {})
    except Exception as e:return fail(e)
@app.post('/api/order/submit')
def submit():
    data=request.get_json(silent=True) or {}
    if data.get('confirmation')!='PLACE LIVE ORDER':return fail('Manual confirmation required')
    try:
        with lock:return execute(data,automatic=False)
    except Exception as e:return fail(e)
def execute(data,automatic=False):
    # This code intentionally never sends a broker order. A future audited
    # execution adapter must implement idempotency, reconciliation and risk gates.
    raise ValueError('Real-money execution disabled: broker fill reconciliation incomplete')

@app.post('/api/disarm')
def disarm():
    with lock:
        put('autonomous','0');put('live_armed','0')
        automation.control(str(DB),'emergency')
        log('Global Emergency Stop activated including all paper/observe engines')
    return {'ok':True}
@app.post('/api/watch')
def add_watch():
    body=request.get_json(silent=True) or {}
    try:
        event=str(body.get('event',''));symbol=str(body.get('symbol',''));qty=int(body.get('quantity',1))
        if not event or not symbol.startswith(('KALSHI.','PMUS.','CDNA.')) or not 1<=qty<=50:raise ValueError('Invalid watch rule')
        buy=D(body.get('buy_below','0'));sell=D(body.get('sell_above','0'));fair=D(body.get('fair_pct','0'))
        if not D('.01')<=buy<sell<=D('.99') or not D('0')<fair<D('100'):raise ValueError('Invalid thresholds / estimate')
        with database() as c:c.execute('INSERT INTO watch VALUES (?,?,?,?,?,?,?,0)',(str(uuid.uuid4()),event,symbol,str(fair),str(buy),str(sell),qty))
        return {'ok':True,'note':'Watch rule saved disabled; strategy must be tested and explicitly enabled.'}
    except Exception as e:return fail(e)
@app.post('/api/watch/<id>/toggle')
def toggle_watch(id):
    with database() as c:
        row=c.execute('SELECT enabled FROM watch WHERE id=?',(id,)).fetchone()
        if not row:return fail('Rule not found',404)
        c.execute('UPDATE watch SET enabled=? WHERE id=?',(0 if row['enabled'] else 1,id))
    return {'ok':True}

@app.post('/api/micro/evaluate')
def micro_evaluate():
    """Read-only, user-input scenario. Prices and probabilities are NEVER auto-inferred.
    All amounts in US dollars; expected value includes losing outcomes and costs.
    """
    b=request.get_json(silent=True) or {}
    try:
        market=str(b.get('market',''))
        if market not in ('stock','prediction'):raise ValueError('Choose stock or prediction')
        q=D(b.get('quantity'));entry=D(b.get('entry_price'));win=D(b.get('win_exit_price'));loss=D(b.get('loss_exit_price'))
        prob=D(b.get('success_probability_pct'))/100
        fees=D(b.get('total_fees','0'));slippage=D(b.get('total_slippage','0'))
        if not (q>0 and entry>0 and win>0 and loss>=0 and 0<prob<1 and fees>=0 and slippage>=0):raise ValueError('Invalid quantity, prices, probability or costs')
        if q>1000000 or entry>100000 or win>100000 or fees>100000 or slippage>100000:raise ValueError('Input out of range')
        if market=='prediction' and (q!=int(q) or any(x>1 for x in (entry,win,loss))):raise ValueError('Prediction contracts require whole quantities and prices up to $1')
        if win<=entry or loss>=entry:raise ValueError('Require winning exit above entry and losing exit below entry')
        gross_win=q*(win-entry);gross_loss=q*(loss-entry)
        net_win=gross_win-fees-slippage;net_loss=gross_loss-fees-slippage
        expected=prob*net_win+(1-prob)*net_loss
        notional=q*entry
        required= (fees+slippage)/q
        threshold=D(settings()['micro_stock_min_edge_pct'] if market=='stock' else settings()['micro_prediction_min_edge_pct'])/100
        min_net=D(settings()['micro_min_net_dollars'])
        passes=expected>=notional*threshold and net_win>=min_net
        return {'market':market,'grossWinningGain':usd(gross_win),'netWinningGain':usd(net_win),'netLosingResult':usd(net_loss),
          'expectedNetValue':usd(expected),'notional':usd(notional),'roundTripCost':usd(fees+slippage),
          'minimumPriceMoveToCoverCosts':str(required),'thresholdPct':str(threshold*100),
          'passesEconomicScreen':passes,'tradeAuthorized':False,
          'warning':'Scenario only. Probability, expected prices, fees and slippage are manually supplied, not validated quotes. Passing does not authorize trades. Settlement and account restrictions still apply.'}
    except Exception as e:return fail(e)


# v0.19.3 — optional OpenAI analysis: no order tools, no bank actions, no brokerage credential exposure.
from engine import ai_analysis
ai_analysis.setup(str(DB))

@app.get('/api/ai/status')
def ai_status():
    return ai_analysis.status(str(DB),settings(),bool(os.getenv('OPENAI_API_KEY')))

@app.get('/api/ai/history')
def ai_history():
    return {'history':ai_analysis.history(str(DB),limit=30)}

@app.post('/api/ai/analyze')
def ai_analyze():
    body=request.get_json(silent=True) or {}
    try:
        # Analysis is explicitly on-demand. No automatic analysis in a trading loop.
        if settings().get('ai_enabled')!='1':return fail('Enable optional AI in settings first',403)
        prompt=body.get('question','')
        if not isinstance(prompt,str) or not 1<=len(prompt.strip())<=1000:return fail('Question must be 1–1000 characters')
        asset=body.get('asset','')
        if not isinstance(asset,str) or len(asset)>40:return fail('Invalid asset symbol')
        market=body.get('market','stock')
        if market not in ('stock','etf','prediction','portfolio'):return fail('Invalid market type')
        # Only user-supplied context is transmitted. Account ID, holdings, balances and API secrets are NOT sent.
        context=body.get('context','')
        if not isinstance(context,str) or len(context)>4000:return fail('Context must be no more than 4000 characters')
        return ai_analysis.analyze(str(DB),settings(),prompt,market,asset,context,os.getenv('OPENAI_API_KEY',''),os.getenv('OPENAI_MODEL','gpt-6-luna'))
    except ai_analysis.AIError as e:return fail(str(e),400)
    except Exception:
        app.logger.exception('AI analysis failed')
        return fail('AI provider error. Check the private server logs; no trade was placed.',502)

@app.get('/api/opportunities')
def opportunities():
    # Quotes plus manual fair probability. NO model probabilities are fabricated.
    with database() as c:rules=[dict(r) for r in c.execute('SELECT * FROM watch WHERE enabled=1')]
    suggestions=[]
    for rule in rules[:20]:
        try:
            det=pub('GET','/userapigateway/eventcontract/details/'+quote(rule['event'],safe=''))
            matches=[v for o in det.get('outcomes',[]) for v in o.get('contracts',[]) if v.get('symbol')==rule['symbol']]
            if not matches:continue
            ask=D(matches[0].get('ask') or 0);bid=D(matches[0].get('bid') or 0)
            edge=D(rule['fair_pct'])/100-ask-FEE
            action='BUY' if ask>0 and ask<=D(rule['buy_below']) and edge>=D('.05') else 'SELL' if bid>=D(rule['sell_above']) else 'WAIT'
            suggestions.append({'rule':rule,'ask':usd(ask),'bid':usd(bid),'netEdge':usd(edge),'suggestion':action})
        except Exception as e:suggestions.append({'rule':rule,'error':str(e)})
    return {'opportunities':suggestions,'note':'Signals rely on user-provided probability estimates; not an independent predictive engine.'}
# This worker deliberately does not submit buy orders while a prior order is unreconciled.
# Continuous autonomous execution must only run in a separately configured always-on service,
# after reconciling holdings, fills, daily P&L and duplicate orders. The UI switch is a
# desired automation setting, not permission to bypass incomplete trade verification.

# v0.19.4: on-demand read-only broker market snapshots; never place orders.
from engine import market_snapshot

@app.post('/api/research/snapshot')
def research_snapshot():
    try:
        body=request.get_json(silent=True) or {}
        kind=body.get('market');acct=selected_account()
        if kind in ('stock','etf'):
            snapshot=market_snapshot.stock_snapshot(pub,acct,body.get('symbol',''))
        elif kind=='prediction':
            snapshot=market_snapshot.prediction_snapshot(pub,body.get('event',''),body.get('symbol',''))
        else:return fail('Market must be stock, ETF, or prediction')
        # Incomplete quotes are shown as unavailable, never interpreted as investable.
        return {'snapshot':snapshot,'readOnly':True,'eligibleForLiveExecution':False}
    except Exception as e:return fail(e,502)

@app.post('/api/research/analyze-snapshot')
def research_analyze_snapshot():
    try:
        if settings().get('ai_enabled')!='1':return fail('Enable AI in settings first',403)
        body=request.get_json(silent=True) or {}
        question=body.get('question','')
        if not isinstance(question,str) or not 1<=len(question.strip())<=1000:return fail('Question must be 1–1000 characters')
        if body.get('consent') is not True:return fail('Confirm sharing the fresh market snapshot with your AI provider',403)
        kind=body.get('market');symbol=body.get('symbol','');acct=selected_account()
        if kind in ('stock','etf'):snapshot=market_snapshot.stock_snapshot(pub,acct,symbol)
        elif kind=='prediction':snapshot=market_snapshot.prediction_snapshot(pub,body.get('event',''),symbol)
        else:return fail('Unsupported market')
        if not snapshot['completeTopOfBook'] or snapshot.get('knownStale'):return fail('Bid/ask incomplete or stale: AI analysis blocked; refresh data',409)
        if kind=='prediction' and not snapshot['openForTrading']:return fail('Event is closed or halted',409)
        context=market_snapshot.text_context(snapshot)
        result=ai_analysis.analyze(str(DB),settings(),question,kind,symbol,context,os.getenv('OPENAI_API_KEY',''),os.getenv('OPENAI_MODEL','gpt-6-luna'))
        result['dataSource']='Public market snapshot retrieved on demand; provider quote timestamps may differ'
        result['capturedAt']=snapshot['capturedAt']
        return result
    except ai_analysis.AIError as e:return fail(e,400)
    except Exception:
        app.logger.exception('Snapshot AI analysis error')
        return fail('Market quote or provider unavailable; no order placed',502)


# v0.19.5: on-demand research screening, no model-derived directional predictions.
from engine import opportunity_scan, discovery

def init_opportunity_scan():
    with database() as c:
        c.execute('CREATE TABLE IF NOT EXISTS scan_config (id INTEGER PRIMARY KEY CHECK(id=1),symbols TEXT NOT NULL)')
        c.execute("CREATE TABLE IF NOT EXISTS discovery_config (id INTEGER PRIMARY KEY CHECK(id=1),mode TEXT NOT NULL, cursor INTEGER NOT NULL DEFAULT 0, equity_per_scan INTEGER NOT NULL DEFAULT 15, events_per_scan INTEGER NOT NULL DEFAULT 5)")
        c.execute("INSERT OR IGNORE INTO discovery_config(id,mode,cursor,equity_per_scan,events_per_scan) VALUES (1,'automatic',0,15,5)")
        c.execute("INSERT OR IGNORE INTO scan_config (id,symbols) VALUES (1,'SPY,QQQ,AAPL,MSFT')")
        c.execute('CREATE TABLE IF NOT EXISTS scan_runs (id INTEGER PRIMARY KEY AUTOINCREMENT,ts TEXT NOT NULL,account TEXT NOT NULL,result_json TEXT NOT NULL)')
init_opportunity_scan()

@app.get('/api/scanner/config')
def scanner_config():
    with database() as c:
        row=c.execute('SELECT symbols FROM scan_config WHERE id=1').fetchone()
        d=c.execute('SELECT * FROM discovery_config WHERE id=1').fetchone()
    return {'symbols':row['symbols'],'mode':d['mode'],'equityPerScan':d['equity_per_scan'],
      'eventsPerScan':d['events_per_scan'],'note':'Automatic: broker universe; Hybrid: both; Watchlist Only: manual entries. All scans are read-only.'}

@app.post('/api/scanner/config')
def scanner_config_set():
    try:
        body=request.get_json(silent=True) or {}
        mode=discovery.validate_mode(body.get('mode','automatic'))
        symbols=opportunity_scan.stock_universe(body.get('symbols',''))
        eq=int(body.get('equityPerScan',15));events=int(body.get('eventsPerScan',5))
        if not 1<=eq<=40 or not 0<=events<=10:raise ValueError('Equities per scan: 1–40; events per scan: 0–10')
        if mode=='watchlist' and not symbols:return fail('Watchlist Only requires at least one symbol')
        with database() as c:
            c.execute('UPDATE scan_config SET symbols=? WHERE id=1',(','.join(symbols),))
            c.execute('UPDATE discovery_config SET mode=?,equity_per_scan=?,events_per_scan=? WHERE id=1',(mode,eq,events))
        return {'symbols':','.join(symbols),'mode':mode,'equityPerScan':eq,'eventsPerScan':events,'saved':True}
    except (ValueError,TypeError) as exc:return fail(exc)

def discovered_market_candidates(account,mode,eq_count,event_count,cursor,manual,issues):
    selected=[];events=[];next_cursor=cursor;total=0
    if mode!='watchlist':
        try:
            # Official Public instrument catalog; this is broad rotating *coverage*, not intelligent selection.
            raw=pub('GET','/userapigateway/trading/instruments?typeFilter=EQUITY&tradingFilter=BUY_AND_SELL')
            all_symbols=discovery.equity_symbols(raw)
            total=len(all_symbols)
            selected,next_cursor=discovery.select_window(all_symbols,cursor,eq_count, manual if mode=='hybrid' else [])
        except Exception:
            issues.append({'market':'stock','symbol':'Discovery','reason':'Broker equity catalog unavailable; automatic stock scanning skipped'})
        if event_count:
            try:
                # One bounded high-volume page, never assume it represents all events.
                raw=pub('POST','/userapigateway/eventcontract/summary',{'sortingMode':'VOLUME','displayResolvedEvents':False,'filters':{'eventIds':[],'frequencies':[]}})
                events=discovery.prediction_events(raw,event_count)
            except Exception:
                issues.append({'market':'prediction','symbol':'Discovery','reason':'Broker event catalog unavailable; automatic prediction scanning skipped'})
    symbols=discovery.mode_sources(mode,selected,manual)
    return symbols,events,next_cursor,total

@app.post('/api/scanner/run')
def scanner_run():
    try:
        from engine import market_snapshot
        account=selected_account()
        with database() as c:
            manual=opportunity_scan.stock_universe(c.execute('SELECT symbols FROM scan_config WHERE id=1').fetchone()['symbols'])
            cfg=c.execute('SELECT * FROM discovery_config WHERE id=1').fetchone()
            mode=cfg['mode'];cursor=cfg['cursor'];eq_count=cfg['equity_per_scan'];event_count=cfg['events_per_scan']
            watches=[dict(r) for r in c.execute('SELECT * FROM watch WHERE enabled=1 LIMIT 20')]
        results=[];issues=[]
        symbols,events,next_cursor,total=discovered_market_candidates(account,mode,eq_count,event_count,cursor,manual,issues)
        for symbol in symbols:
            try:results.append(opportunity_scan.assess(market_snapshot.stock_snapshot(pub,account,symbol)))
            except Exception:issues.append({'market':'stock','symbol':symbol,'reason':'Quote unavailable/invalid; not ranked'})
        reviewed_events=0
        for e in events:
            try:
                details=pub('GET','/userapigateway/eventcontract/details/'+quote(e['event'],safe=''))
                if details.get('eventSymbol')!=e['event']:raise ValueError('Event mismatch')
                contracts=discovery.contract_candidates(details,2)
                reviewed_events+=1
                for contract in contracts:
                    try:results.append(opportunity_scan.assess(market_snapshot.prediction_snapshot(pub,e['event'],contract)))
                    except Exception:issues.append({'market':'prediction','symbol':contract,'reason':'Contract quote invalid or unavailable'})
            except Exception:issues.append({'market':'prediction','symbol':e['event'],'reason':'Event details unavailable'})
        if mode!='automatic':
            for w in watches:
                try:results.append(opportunity_scan.assess(market_snapshot.prediction_snapshot(pub,w['event'],w['symbol']),fair_pct=w['fair_pct']))
                except Exception:issues.append({'market':'prediction','symbol':w['symbol'],'reason':'Watched contract details unavailable'})
        output={'capturedAt':datetime.now(timezone.utc).isoformat(),'mode':mode,
          'coverage':{'eligibleEquitiesReported':total,'watchlistSymbols':len(manual),'equitiesSampled':len(symbols),'eventsReviewed':reviewed_events,'partialUniverse':mode!='watchlist'},
          'candidates':opportunity_scan.rank(results),'unavailable':issues,'readOnly':True,'eligibleForLiveExecution':False,
          'note':'Automatic discovery samples broker listings in rotating windows; it is NOT a whole-market simultaneous scan. Rankings are quote-quality scores, NOT return forecasts.'}
        with database() as c:
            c.execute('INSERT INTO scan_runs (ts,account,result_json) VALUES (?,?,?)',(output['capturedAt'],account,json.dumps(output)))
            if mode!='watchlist' and total and not any(x['symbol']=='Discovery' and x['market']=='stock' for x in issues):
                c.execute('UPDATE discovery_config SET cursor=? WHERE id=1',(next_cursor,))
        return output
    except Exception:
        app.logger.exception('Scanner failed')
        return fail('Market scan unavailable. Check Public connection; no trades placed.',502)

@app.post('/api/predictive/backtest')
def predictive_backtest():
    # Import only user-pasted historical bars: no look-ahead or fabricated market history.
    try:
        from engine import predictive
        body=request.get_json(silent=True) or {}
        bars=predictive.parse_daily_csv(body.get('csv',''))
        result=predictive.backtest(bars,int(body.get('lookback',5)),int(body.get('hold',2)),
            int(body.get('costBps',20)),int(body.get('trainingPct',60)))
        return jsonify(result)
    except (ValueError,TypeError,OverflowError) as e:
        return fail(str(e))

@app.post('/api/predictive/public-history')
def predictive_public_history():
    # Stocks/ETFs only; prediction markets need separate historical contract modeling.
    # Never returns fake history or treats a backtest as a live trade signal.
    try:
        from engine import predictive, public_history
        body=request.get_json(silent=True) or {}
        symbol=public_history.clean_symbol(body.get('symbol'))
        period=body.get('period','YEAR')
        refresh=body.get('refresh',False)
        if not isinstance(refresh,bool):raise ValueError('refresh must be boolean')
        public_history.setup(str(DB))
        hist=public_history.fetch_history(str(DB),pub,symbol,period,refresh)
        result=predictive.backtest(hist['bars'],int(body.get('lookback',5)),int(body.get('hold',2)),
            int(body.get('costBps',20)),int(body.get('trainingPct',60)))
        result.update({'symbol':symbol,'dataSource':'Public API regular-hours ONE_DAY EQUITY bars',
            'dataPeriod':period,'cached':hist['cacheHit'],'fetchedAt':hist['fetchedAt'],
            'firstBarDate':hist['bars'][0]['date'],'lastBarDate':hist['bars'][-1]['date'],
            'eligibleForTrading':False})
        result['warning']+=' Historical bar availability, trading calendars, corporate actions, splits, dividends and missing sessions are not independently verified. Cache may be up to 6 hours old.'
        return jsonify(result)
    except (ValueError,TypeError,OverflowError) as e:return fail(str(e))
    except Exception:
        app.logger.exception('Public history failed')
        return fail('Broker historical data unavailable; no synthetic data substituted.',502)

@app.post('/api/predictive/walk-forward')
def predictive_walk_forward():
    """Explicit CSV or broker historical studies; never authorizes trading."""
    try:
        from engine import predictive, public_history, walk_forward
        body=request.get_json(silent=True) or {}
        source=body.get('source','public')
        if source=='csv':
            bars=predictive.parse_daily_csv(body.get('csv',''))
            provenance={'dataSource':'User-supplied daily CSV'}
        elif source=='public':
            symbol=public_history.clean_symbol(body.get('symbol'))
            period=body.get('period','FIVE_YEARS')
            public_history.setup(str(DB))
            hist=public_history.fetch_history(str(DB),pub,symbol,period,False)
            bars=hist['bars']
            provenance={'dataSource':'Public API stock/ETF daily bars','symbol':symbol,'period':period,
                        'cacheHit':hist['cacheHit'],'fetchedAt':hist['fetchedAt']}
        else:raise ValueError('Source must be public or csv')
        lookbacks=body.get('lookbacks',[3,5,10,20])
        if not isinstance(lookbacks,list):raise ValueError('Lookbacks must be an array')
        result=walk_forward.validate(bars,training_bars=int(body.get('trainingBars',180)),
           test_bars=int(body.get('testBars',60)),step_bars=int(body.get('stepBars',60)),
           lookbacks=lookbacks,hold_days=int(body.get('holdingDays',2)),cost_bps=int(body.get('costBps',20)))
        result.update(provenance)
        return jsonify(result)
    except (ValueError,TypeError,OverflowError) as e:return fail(str(e))
    except Exception:
        app.logger.exception('Walk forward unavailable')
        return fail('Walk-forward study unavailable; no orders placed.',502)

@app.get('/api/scanner/history')
def scanner_history():
    with database() as c: rows=c.execute('SELECT ts,result_json FROM scan_runs ORDER BY id DESC LIMIT 10').fetchall()
    return {'runs':[{'capturedAt':r['ts'],'candidateCount':len(json.loads(r['result_json'])['candidates'])} for r in rows]}

# Uses one Render Starter web worker, shared local SQLite and a lease.
# Experimental Observe/Paper only; production live execution still hard-blocked.
automation_worker.start_web_worker(__import__(__name__))

if __name__=='__main__':
    app.run(host=os.getenv('HOST','127.0.0.1'),port=int(os.getenv('PORT','8787')),debug=False)
