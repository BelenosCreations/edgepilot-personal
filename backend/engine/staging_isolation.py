"""Fail-closed configuration check for isolated Android biometric test service.

The already-running owner deployment is unaffected unless explicitly configured
with EDGE_ISOLATED_STAGING=true. This is a startup gate, NOT a runtime account
authorization and NOT permission to use real broker data or funds.
"""
import os
import re
from pathlib import Path


class StagingIsolationDenied(RuntimeError):
    pass


def validate(environment=None):
    env=os.environ if environment is None else environment
    stage_mode=str(env.get("EDGE_ISOLATED_STAGING","false")).lower()
    if stage_mode=="false" or stage_mode=="":
        return False
    if stage_mode!="true":
        raise StagingIsolationDenied("Staging isolation flag must be explicit true or false")
    rp=str(env.get("EDGE_WEBAUTHN_RP_ID","")).lower()
    origin=str(env.get("EDGE_WEBAUTHN_ORIGIN",""))
    hostname=re.fullmatch(r"(?:[a-z0-9]+(?:-[a-z0-9]+)*\.)+belenoscreations\.biz",rp)
    if (not hostname or rp=="edgepilot.belenoscreations.biz" or
        origin!="https://"+rp or
        env.get("EDGE_ANDROID_ASSOCIATION_PACKAGE")!="com.edgepilot.mobile.staging"):
        raise StagingIsolationDenied("Isolated staging requires a distinct pinned HTTPS RP and Android package")
    fingerprint=str(env.get("EDGE_ANDROID_CERT_SHA256","")).upper().strip()
    if not re.fullmatch(r"(?:[0-9A-F]{2}:){31}[0-9A-F]{2}",fingerprint):
        raise StagingIsolationDenied("Isolated staging requires a verified public Android signing certificate")
    raw_path=str(env.get("EDGE_DB_PATH",""))
    try:
        db_path=Path(raw_path).resolve(strict=False)
    except (OSError, ValueError, RuntimeError):
        raise StagingIsolationDenied("Isolated staging requires a separate ephemeral DB path") from None
    if (not raw_path.startswith("/tmp/") or not db_path.is_relative_to(Path("/tmp")) or
        db_path == Path("/tmp") or db_path.suffix != ".db"):
        raise StagingIsolationDenied("Isolated staging requires a separate /tmp SQLite test database")
    for key in ("EDGE_APP_TOKEN","PUBLIC_API_SECRET","EDGE_CREDENTIAL_KEY"):
        if str(env.get(key,"")):
            raise StagingIsolationDenied("Production credentials must be absent from isolated staging")
    for key in (
        "EDGE_AUTOMATION_WORKER_ENABLED",
        "ENABLE_LIVE_ORDERS",
        "EDGE_TENANT_PUBLIC_VAULT_ENABLED",
        "EDGE_TENANT_PUBLIC_READONLY_ENABLED",
        "EDGE_TENANT_ACCOUNT_READS_ENABLED",
        "EDGE_TENANT_MONITOR_PREVIEW_ENABLED",
        "EDGE_TENANT_WATCHLIST_EDIT_ENABLED",
    ):
        if str(env.get(key,"false")).lower()!="false":
            raise StagingIsolationDenied("Worker, broker and monitoring features must be explicitly disabled in staging")
    for key in (
        "EDGE_TENANT_SCHEMA_PREPARE",
        "EDGE_IDENTITY_AUTH_ENABLED",
        "EDGE_TENANT_SIGNUP_ENABLED",
        "EDGE_TENANT_PASSKEYS_ENABLED",
    ):
        if str(env.get(key,"false")).lower()!="true":
            raise StagingIsolationDenied("Isolated staging must have independently enabled test-only identity ceremonies")
    return True
