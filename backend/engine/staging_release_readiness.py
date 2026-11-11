"""Strict offline lint of a proposed, NOT DEPLOYABLE Render staging service.

This accepts only a static repository template. It cannot contact Render,
DNS, the broker, Android devices or GitHub; it never certifies owner billing
approval, hostname ownership, an APK signing certificate or device login.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import staging_isolation


class StagingProposalDenied(ValueError):
    pass


EXPECTED_HOST = "staging-edgepilot.belenoscreations.biz"
CERT_PENDING = "REQUIRES_VERIFIED_PUBLIC_CERT_BEFORE_DEPLOY"
PRODUCTION_KEYS = frozenset((
    "EDGE_APP_TOKEN", "PUBLIC_API_SECRET", "EDGE_CREDENTIAL_KEY",
    "OPENAI_API_KEY", "EDGE_ANDROID_SIGNING_JKS_B64",
    "EDGE_ANDROID_SIGNING_STORE_PASS",
    "EDGE_ANDROID_SIGNING_KEY_PASS",
    "EDGE_ANDROID_SIGNING_ALIAS",
))
EXPECTED_ENV = {
    "EDGE_DB_PATH": "/tmp/edgepilot-staging.db",
    "EDGE_ISOLATED_STAGING": "true",
    "EDGE_WEBAUTHN_RP_ID": EXPECTED_HOST,
    "EDGE_WEBAUTHN_ORIGIN": "https://" + EXPECTED_HOST,
    "EDGE_ANDROID_ASSOCIATION_PACKAGE": "com.edgepilot.mobile.staging",
    "EDGE_ANDROID_CERT_SHA256": CERT_PENDING,
    "EDGE_TENANT_SCHEMA_PREPARE": "true",
    "EDGE_IDENTITY_AUTH_ENABLED": "true",
    "EDGE_TENANT_SIGNUP_ENABLED": "true",
    "EDGE_TENANT_PASSKEYS_ENABLED": "true",
    "EDGE_TENANT_PASSWORD_CHANGE_ENABLED": "false",
    "EDGE_TENANT_SESSION_CONTROLS_ENABLED": "false",
    "EDGE_AUTOMATION_WORKER_ENABLED": "false",
    "ENABLE_LIVE_ORDERS": "false",
    "EDGE_TENANT_PUBLIC_VAULT_ENABLED": "false",
    "EDGE_TENANT_PUBLIC_READONLY_ENABLED": "false",
    "EDGE_TENANT_ACCOUNT_READS_ENABLED": "false",
    "EDGE_TENANT_MONITOR_PREVIEW_ENABLED": "false",
    "EDGE_TENANT_WATCHLIST_EDIT_ENABLED": "false",
}
EXPECTED_FIELDS = frozenset((
    "_purpose", "name", "runtime", "repo", "branch", "autoDeploy",
    "plan", "region", "dockerContext", "dockerfilePath",
    "candidateCustomHostname", "envVars", "blockedUntil",
    "serviceCreationApprovedByThisFile",
))


def inspect(proposal):
    """Return only a nonbinding safety report; refuse changes to the template."""
    if type(proposal) is not dict or set(proposal) != EXPECTED_FIELDS:
        raise StagingProposalDenied("Exact controlled staging fields required")
    fixed = {
        "name": "edgepilot-passkey-staging",
        "runtime": "docker",
        "repo": "https://github.com/BelenosCreations/edgepilot-personal",
        "branch": "main",
        "autoDeploy": "no",
        "plan": "free",
        "region": "ohio",
        "dockerContext": "./backend",
        "dockerfilePath": "./backend/Dockerfile",
        "candidateCustomHostname": EXPECTED_HOST,
        "serviceCreationApprovedByThisFile": False,
    }
    if any(type(proposal[k]) is not type(v) or proposal[k] != v
           for k, v in fixed.items()):
        raise StagingProposalDenied("Unapproved service or billing configuration")
    if (not isinstance(proposal["_purpose"], str) or
            "NOT an auto-applied Render Blueprint" not in proposal["_purpose"]):
        raise StagingProposalDenied("Deployment warning required")
    if (type(proposal["blockedUntil"]) is not list or
            len(proposal["blockedUntil"]) < 4 or
            not all(type(item) is str and 16 <= len(item) <= 250
                    for item in proposal["blockedUntil"])):
        raise StagingProposalDenied("External approval blockers must be recorded")
    raw = proposal["envVars"]
    if type(raw) is not list or len(raw) != len(EXPECTED_ENV):
        raise StagingProposalDenied("Complete staging-only environment required")
    env = {}
    for row in raw:
        if (type(row) is not dict or set(row) != {"key", "value"}
                or type(row["key"]) is not str
                or type(row["value"]) is not str
                or row["key"] in env):
            raise StagingProposalDenied("Invalid or duplicate environment variable")
        env[row["key"]] = row["value"]
    if (env != EXPECTED_ENV or PRODUCTION_KEYS.intersection(env)
            or any("SECRET" in name or "PASSWORD" in name
                   for name in env if name not in EXPECTED_ENV)):
        raise StagingProposalDenied("Do not mix owner credentials or execution controls")
    # Never record a fake fingerprint in the deployable template. A test-only
    # syntactically valid certificate exercises the *existing* server startup
    # isolation guard, but cannot prove the actual APK certificate matches.
    validation_env = dict(env)
    validation_env["EDGE_ANDROID_CERT_SHA256"] = ":".join(["A1"] * 32)
    try:
        if staging_isolation.validate(validation_env) is not True:
            raise StagingProposalDenied("Staging isolation guard not active")
    except staging_isolation.StagingIsolationDenied:
        raise StagingProposalDenied("Unsafe staging startup specification") from None
    return {
        "staticProposalValidated": True,
        "serviceCreated": False,
        "verifiedCertificateSupplied": False,
        "customDomainVerified": False,
        "renderChargesApproved": False,
        "productionResourcesChanged": False,
        "physicalPasskeyValidated": False,
        "hasEphemeralDatabase": True,
        "needsExternalApprovalAndEvidence": True,
    }


def inspect_file(path):
    """Only local JSON data; there are no shell commands or network calls."""
    target = Path(path)
    if target.stat().st_size > 20000:
        raise StagingProposalDenied("Oversized proposal")
    try:
        obj = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise StagingProposalDenied("Invalid static proposal") from None
    return inspect(obj)
