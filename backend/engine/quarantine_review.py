"""Read-only, evidence-based disposition of quarantined legacy rows.

No source records are edited or assigned an owner. Review decisions are policy
recommendations, never consent to migrate, delete, trade or enable automation.
Only sanitized group counts and next actions leave the disposable DB.
"""
from __future__ import annotations

from . import historical_reconciliation as history

POLICIES = {
    "observation_cycles": ("unscoped_observations", "ARCHIVE_UNVERIFIED"),
    "automation_quotes": ("automation_market_research", "ARCHIVE_UNVERIFIED"),
    "automation_events": ("automation_market_research", "ARCHIVE_UNVERIFIED"),
    "automation_master": ("automation_runtime", "RECREATE_DISABLED"),
    "automation_engines": ("automation_runtime", "RECREATE_DISABLED"),
    "automation_highwater": ("automation_runtime", "ARCHIVE_UNVERIFIED"),
    "automation_worker_lease": ("ephemeral_runtime", "DO_NOT_REUSE"),
    "paper_positions": ("paper_simulation", "PROVE_OWNER_FIRST"),
    "activity": ("activity_and_ai", "ARCHIVE_UNVERIFIED"),
    "ai_runs": ("activity_and_ai", "ARCHIVE_UNVERIFIED"),
    "engine_configs": ("configuration_and_watchlists", "REVIEW_BEFORE_IMPORT"),
    "discovery_config": ("configuration_and_watchlists", "REVIEW_BEFORE_IMPORT"),
    "scan_config": ("configuration_and_watchlists", "REVIEW_BEFORE_IMPORT"),
    "watch": ("configuration_and_watchlists", "REVIEW_BEFORE_IMPORT"),
    "ledger_meta": ("ledger_metadata", "RECONCILE_INDEPENDENTLY"),
    "settings": ("configuration_and_watchlists", "REVIEW_BEFORE_IMPORT"),
    "edge_sessions": ("login_security", "ROTATE_AND_REPROVISION"),
    "edge_login_failures": ("login_security", "DO_NOT_REUSE"),
    "broker_credentials": ("credential_security", "VERIFY_VAULT_SEPARATELY"),
}
ACTIONS = {
    "unscoped_observations": "Keep historical observation cycles unscoped; require corroborated account provenance before tenant import",
    "automation_market_research": "Archive read-only quotes/events; do not claim they belong to a broker account",
    "automation_runtime": "Review risk settings and state; never resume legacy engines automatically",
    "ephemeral_runtime": "Discard leases on future cutover; never import running worker state",
    "paper_simulation": "Require signed provenance and account context before importing any paper positions",
    "activity_and_ai": "Preserve private audit/AI history only with a separately authorized owner mapping",
    "configuration_and_watchlists": "Revalidate saved preferences and risk profiles per account; keep inactive",
    "ledger_metadata": "Reconcile ledger totals independently with broker-confirmed fills",
    "login_security": "Create new scoped sessions after authentication; do not carry over old tokens",
    "credential_security": "Preserve encrypted vault separately; never expose decrypted Public secrets",
    "ambiguous_account": "Obtain authoritative account owner evidence; do not infer ownership from a symbol or timestamp",
    "unknown_schema": "Review previously unknown table schema; never assign to an account by default",
}


def review(con, expected_unresolved):
    """Aggregate table/class evidence; never return IDs, row values or hashes."""
    totals = {}
    quarantined = 0
    unknown = 0
    for row in con.execute("""SELECT source_table,classification,COUNT(*) AS n
        FROM tenant_shadow_history_index
        GROUP BY source_table,classification ORDER BY source_table,classification"""):
        table, classification, n = row["source_table"], row["classification"], row["n"]
        if classification in (history.EXPLICIT, history.PREMAPPED):
            continue
        if classification == history.AMBIGUOUS:
            group, disposition = "ambiguous_account", "PROVE_OWNER_FIRST"
        elif classification == history.UNACCOUNTED:
            group, disposition = "unknown_schema", "SCHEMA_REVIEW"
            unknown += n
        else:
            group, disposition = POLICIES.get(table, ("unknown_schema", "SCHEMA_REVIEW"))
            if group == "unknown_schema":
                unknown += n
        quarantined += n
        old = totals.setdefault(group, {"rows":0, "disposition":disposition, "tables":set()})
        if old["disposition"] != disposition:
            raise history.HistoryReconciliationError("Ambiguous quarantine policy")
        old["rows"] += n
        old["tables"].add(table)

    if quarantined != expected_unresolved:
        raise history.HistoryReconciliationError("Quarantine totals do not reconcile")
    result = {
        key: {"rows":v["rows"],"tables":sorted(v["tables"]),
              "disposition":v["disposition"],"action":ACTIONS[key],
              "tenantImported":False}
        for key,v in sorted(totals.items())
    }
    if sum(v["rows"] for v in result.values()) != quarantined:
        raise history.HistoryReconciliationError("Quarantine review totals mismatch")
    return {
        "quarantinedRowsReviewed":quarantined,
        "unresolvedUnknownSchemaRows":unknown,
        "groups":result,
        "everyQuarantinedRowHasReviewPolicy":True,
        "allOwnershipInferencesWithheld":True,
        "noAutomaticOwnerAssignments":True,
        "noRecordsDeleted":True,
        "readyForCutover":False,
    }
