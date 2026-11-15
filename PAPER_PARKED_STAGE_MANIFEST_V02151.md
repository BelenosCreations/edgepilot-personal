# Parked-stage location manifest rehearsal (v0.2.151, offline synthetic only)

The previous Linux renameat2(RENAME_NOREPLACE) experiment prevents overwriting an occupied destination name, but does not authenticate the moved directory or let a reviewer discover a parked directory after restart. This milestone adds a test-local source-attributed, HMAC-authenticated location record for *read-only review* only. It does not add any engine, Android, backend route, Render or operator-facing production API.

## Evidence and tests

Ten isolated Linux-only synthetic tests (five terminal receipts and five checkpoint cases) cover:

1. Clean read-only review: a signed record held outside the parking directory identifies source kind, original stage name and directory identity, holding directory identity, parked name, publication target identity and SHA-256, receipt digest, and digests of separately retained evidence. A reviewer reopens without following symlinks, checks descriptor identities, verifies the exact hard link and performs authenticated readback.
2. Replaced holding parent: the real holding directory moves aside and a fake takes its name. The reviewer refuses while retaining the authentic parked candidate.
3. Replaced parked basename: the verified parked directory moves aside and an unreviewed directory takes its name. The reviewer refuses without deleting either.
4. Tampered manifest: modified record bytes without the ephemeral test HMAC key are rejected.
5. Altered independent evidence: a change to an independently retained evidence file causes read-only review to refuse.

All observations are fabricated. These are not hostile same-UID security proofs, host-crash durability tests, or a license to restore or delete anything.

## Security and recovery boundaries

The record is emitted after the rename, leaving a crash window before its publication. A write-ahead manifest would introduce an ambiguous prepared state instead, requiring separately trusted monotonic custody and explicit recovery decisions. The ephemeral in-process test key is not an independent key service. Valid older manifests might still replay if all external state rolls back. A same-UID writer can swap paths after a final identity check. No combined full-evidence rollback, cross-resource power-loss consistency, or autonomous repair is solved.

Ordinary stage-prefix inventory cannot locate the parked entry without explicitly authenticated read-only discovery. Production paper fills, live trades, autonomous orders and bank transfers remain disabled. Tenant archive pin, signed receipt/checkpoint custody, detached authenticated paper preflight and session-only source-attributed Public history remain unchanged. No credentials, tenant data, production storage, Render configuration or paid infrastructure changed.
