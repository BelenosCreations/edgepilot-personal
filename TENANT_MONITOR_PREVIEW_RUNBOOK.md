# EdgePilot v0.2.32 — Tenant-scoped, inactive monitoring preview

## Purpose

Move account-specific monitoring closer to the existing shared-login
experience **without** enabling an account scanner, queue, broker network
call, order, transfer or global worker. An authenticated user can inspect
the planned watchlist and safety state for a linked account they own.

A new endpoint, GET /api/identity/accounts/<account_id>/monitor/preview,
uses the verified identity session principal from the server request,
never a user_id supplied in the query or JSON. It calls the existing
DormantAccountMonitorPlanner, which authorizes the exact account and
connection and refuses revoked users, disabled accounts, revoked Public
connections and unexpected persisted worker/trading flags.

The response contains only the internal account UUID, validated watchlist
symbols, planned observe mode, and explicit false flags for scheduling,
live worker, broker network requests, paper mode and live trading.
It is not evidence of a completed market scan.

## Activation and safety

The preview is separately disabled by default through
EDGE_TENANT_MONITOR_PREVIEW_ENABLED=false and cannot be enabled unless
EDGE_TENANT_ACCOUNT_READS_ENABLED and EDGE_IDENTITY_AUTH_ENABLED are enabled
with prepared tenant schema. The legacy personal dashboard and global
Observe/Paper worker remain independent.

The static tenant_route_audit inventories this route, requires the
server-side principal/account authorization and default-off flag, and
**still prohibits importing tenant_monitor_blueprint into the legacy
automation worker**.

No API allows starting scans, modifying the stored watchlist, enabling
workers, requesting orders, submitting funds transfers, or replaying
synthetic observations. The existing offline replay method remains
restricted to isolated fixtures. The UI is labeled "inactive preview".

## Verification

Tests must prove two users with different watchlists cannot access each
other's plans, spoof user_id, or read a revoked or disabled account. Invalid
watchlist data must be returned as a uniform sanitized 404, not echoed to
the user. A disconnected client must be denied and a disabled preview flag
must not create a scheduler. The account UI must reject any server response
that claims an active worker, network calls, paper execution or trading.

Passing CI is not proof of real Public connectivity or physical-device
passkey login. This feature remains a code-only preparation milestone.
