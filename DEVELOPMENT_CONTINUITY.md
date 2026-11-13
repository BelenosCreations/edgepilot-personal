## v0.2.107 — 2026-11-13 — Authenticated offline paper preflight

Starting checkpoint independently verified against GitHub main `f0a028f472fe7551086a42977cad4a9e4202e6fd`, push Actions `43429441401`, and the successful exact-SHA GitHub deployment status targeting Render `dep-dbrgi5s9v7es73a7i15g` with the service health probe returning OK. No open PRs at baseline.

The marked /dev/shm fixture now rehearses session- and CSRF-derived tenant authorization, account isolation, dormant ledger audit/idempotency, and v0.2.106 fractional Decimal risk projection in a single always-rolled-back transaction. See PAPER_AUTHENTICATED_PREFLIGHT_V02107.md. v0.2.94 owner acceptance still applies.

**Next.** Advance externally durable operator evidence custody and crash-consistency design for fractional accounting, including rotation, quarantine and authenticated encrypted recovery. Establish per-source rights independently before any persistent use of a real quote. Keep production paper fills, live orders, autonomous brokerage orders and bank transfers disabled.

## v0.2.106 — 2026-11-13 — Inactive fractional Decimal atomic stop/accounting research

Baseline independently reverified: v0.2.105 main `9d22638364565206505085104096600b273ad650`, post-merge Actions `43380544724` success, Render `dep-dbrb2iijnfac73992ou0` LIVE with the exact matching SHA; Starter service, 1 GB disk and automatic deployment preserved; no open PRs. Added `tenant_paper_decimal_atomic_rehearsal.py` and `test_tenant_paper_decimal_atomic_v02106.py` as separate /dev/shm-only fabricated-input research. Reuses Decimal parsing and cent accounting primitives from dormant `tenant_paper_ledger.py`; wraps fractional holdings, conservative basis, account-protected budgets, exact realized changes, historical sticky stop, idempotent MAC-journal replay and scoped wallet state in one synthetic SQLite transaction. Separate operator-held HMAC candidate checkpoint detects stale whole fixtures only if the latest pin remains independently trusted. Tests cover concurrent requests, rollback, cross-account boundaries, bad data, missing wallet and signed tampering. See PAPER_DECIMAL_ATOMIC_V02106.md.

**Next gates:** Owner acceptance from v0.2.94 remains recorded. This prototype **does not connect** to source-attributed, fresh and explicitly persistence-licensed Public observations; nor to verified server authentication, tenant disabled/revoked status, independently durable monotonic custody, compromised-key quarantine, prepared rotation or encrypted restore. No production paper fills, orders, transfers, new paid infrastructure or Render configuration changes. Future work: independently reviewed authenticated account integration design and operator crash-consistency/recovery protocol; never auto-accept an older database. This is not production risk enforcement.

## v0.2.105 — 2026-11-13 — Offline atomic paper accounting and historical stop protocol rehearsal

Baseline independently reverified: v0.2.104 main `8d9cba9e2fe7cd171b7ce8c7433364cd06e553a0`, post-merge GitHub Actions `43378868582` successful, Render `dep-dbrarp61egvs73fjn5ig` LIVE at exact matching commit, with the existing Starter/1GB disk and automatic main deployment intact and no open PRs. Added `backend/engine/tenant_paper_atomic_rehearsal.py` and regression suite `test_tenant_paper_atomic_rehearsal_v02105.py` to independently rehearse single-BEGIN-IMMEDIATE transactions combining account-scoped wallet cash, protected exposure, immutable stop limit, position cost basis, exact integer-cent realized gains/losses, idempotent request journaling, HMAC policy/state/event integrity and sticky worst historical realized losses. It is not imported by the actual dormant paper writer or Flask and never touches production. Operator/reviewer limitations are recorded in `PAPER_ATOMIC_ACCOUNTING_V02105.md`.

**Remaining gaps:** Synthetic whole-unit fabricated prices are not the source-attributed, licensed, time-validated observations needed by the dormant Decimal paper ledger. No real session authority, shared production transaction, external trusted monotonic pin custody, crash-atomic external publication, secure key retirement or production-safe encrypted restore exists here. Do not activate paper fills, bank transfers, live trades or autonomous orders. Next work should test inactive Decimal-fractional source-attributed integration and external operator evidence custody, preserving all multi-user account identities, protected balances and recovery controls. No credentials, paid infrastructure or Render configuration changed. Prior owner snapshot and MSFT quote acceptance remain documented and need not repeat absent targeted regressions.

## v0.2.104 — 2026-11-13 — Inactive operator evidence chain and fail-closed synthetic recovery

Starting checkpoint independently verified: main `92e64222fd073075eb05218193e0b436c49eeee2`, merged-main GitHub Actions `43373123128` successful, Render `dep-dbra3mavcj2c73emegkg` LIVE with exactly matching commit, Starter service and 1 GB disk unchanged, no open PRs. Added `backend/engine/tenant_paper_latch_operator_evidence.py` as a completely offline module requiring an independent operator HMAC key, authenticated whole-fixture checkpoint, externally pinned latest evidence tip and monotonic sequence/epoch. Existing preauthenticated HMAC journal-key tickets can be referenced by `ROTATION_PENDING`, whose old chain stays ambiguous even after apparent precommit failure; committed new chains require explicit operator promotion. Suspicion of key compromise or old-state rollback can be recorded as a signed terminal quarantine, never automatic acceptance. The runbook is `PAPER_OPERATOR_EVIDENCE_V02104.md` and focused tests are `test_tenant_paper_latch_operator_evidence_v02104.py`.

**Limits and next steps:** No real operator record service, externally durable/latest trusted tip, actual rollback-resistant key-vault authority, cross-resource crash-atomic commits, paper-fill integration, licensed market data expansion, or activation approval. Synthetic /dev/shm tests are not host-crash durable production protections. Retain v0.2.94 owner acceptance without unnecessary retest. Next research milestone: independently audited inactive single-transaction paper wallet/position/cost-basis/idempotency/stop-latch enforcement; preserve account scoping and protected-cash rules. Never activate live trading, autonomous brokerage orders, transfers or paper fills. No new paid services or Render changes.

## v0.2.103 — 2026-11-13 — Offline encrypted latch archive and anti-rollback restore rehearsal

Independently reverified v0.2.102 main `936a4253435fb96bd31bab9646f5b4307137f9a3`, merged-main Actions `43371891173` successful, and exact-matching Render `dep-dbr9uc0jo6nc73esdf00` LIVE before changes. No open PRs at baseline; Starter service and 1 GB disk retained. New isolated `tenant_paper_latch_archive.py` encrypts a consistent `/dev/shm` fixture snapshot into caller-held Fernet ciphertext after strict external full-account HMAC checkpoint verification; restore validates ciphertext, schema, journal and latest external pin privately before 0600 atomic no-replace publication. Tests in `test_tenant_paper_latch_archive_v02103.py`; operator instructions in `PAPER_LATCH_ENCRYPTED_ARCHIVE_V02103.md`.

**Boundaries:** No production paper-fill integration, HTTP endpoint, Public quote request, broker secrets, licensed data use, durable production backup, external monotonic anchor, bank transfers, autonomous orders, new paid services or Render changes. Existing v0.2.94 owner acceptance remains intact. Next focus: independent externally durable key/epoch/archive custody and crash-safe operator review; design a single transactional, account-scoped paper-ledger/idempotency/stop integration only as dormant research, retaining protected balance and exact-cent risk accounting. No production paper activation before independent review and approval.

## v0.2.102 — 2026-11-13 — Prepared offline synthetic key rotation recovery

Based on independently verified v0.2.101 merged main `b34d79b9b7fe3a7f3942794f662eee517987e01c` (PR #128; PR Actions `43370953761` success; post-merge main Actions `43371189038` success; Render deployment `dep-dbr9rd49v7es739vp8og` matching main and live). Added inactive `backend/engine/tenant_paper_latch_rotation_ticket.py` for externally authenticated synthetic before/after rotation tickets, deterministic next-key MAC predictions, exact prepared transition checks, and after-crash state classification. It never treats an old valid file as safely uncommitted because rollback after commit can produce the same evidence. See `PAPER_LATCH_ROTATION_TICKET_V02102.md`.

**Activation boundaries:** Explicit external durable ticket publication and independently monotonic pin/key revocation authority remain absent; `/dev/shm` is not production-durable. No app import, dormant paper fills, broker execution, transfers, new paid service, Render configuration or restored credentials. Next development should prioritize verifiable offline encrypted latch snapshot/recovery linked to external pins and then independently reviewed atomic integration with protected-balance/position accounting and licensed market provenance. Keep owner acceptance as recorded in v0.2.94.

## v0.2.101 — 2026-11-13 — Inactive attested synthetic stop-latch recovery

Verified source baseline for this branch was v0.2.100 main `a97717b1b88d394dda45bee18e65d7ca461fdfcb`, GitHub Actions `43368671340` successful, and Render live deploy `dep-dbr9gn67bikc73enajs0` at the matching SHA. New `tenant_paper_latch_attestation.py` is not imported by the Flask app or dormant paper-fill writer. It audits the entire isolated /dev/shm synthetic journal, emits an independent externally authenticated checkpoint across all scopes, detects rollback against the latest trusted pin, and rehearses transactional HMAC journal-key rotation with explicit epoch increment, failure injection and old-key refusal. See `PAPER_ATTESTED_LATCH_RECOVERY_V02101.md` and `backend/tests/test_tenant_paper_latch_attestation_v02101.py`.

**Safety:** This does not activate paper fills or real trades, orders, transfers, licensed market-data retention, autonomous workers or any additional service. An external monotonic pin store and crash-atomic pin promotion remain missing; key retirement and older backups require operator review. Further milestones should design a single-transaction integration with authenticated identity, paper positions, cash, protected balance and exact-cent loss stops, then separately prove licensed data and durable recovery before requesting activation.

## CURRENT development — v0.2.100 synthetic paper loss-stop latch atomicity, November 12, 2026 (America/New_York)

**Verified starting point:** v0.2.99 main `bf5ec2bc11973d796d8f9c583d9044818313a539` identical to supplied checkpoint, merged-main Actions #43367286446 succeeded, existing Render Starter/1 GB persistent disk service `edgepilot-private-h9tl` deployment `dep-dbr9aiijnfac73977sl0` LIVE at that exact SHA. Prior same-account Public value acceptance and real MSFT quote acceptance are already complete.

**v0.2.100 proposed change:** Dedicated synthetic-only new /dev/shm fixture and HMAC-chained per-user/account policy journal for sticky loss-stop decisions; SQLite BEGIN IMMEDIATE atomicity for fictional OPEN / REALIZE entries, exact integer cents, duplicate request idempotency, fail-before-commit rollback and independent family/account tests. Explicitly disconnected from Flask, dormant paper ledger writer and all production data. Existing encryption, credentials, multi-user architecture and Render deployment unchanged. See PAPER_ATOMIC_LATCH_REHEARSAL_V02100.md.

**Verification to complete:** Exact-head PR Actions, merge only if successful, merged-main Actions and existing Render live at merged main SHA. Next priorities: independent policy/latch backup anti-rollback, key rotation and crash-recovery rehearsal; session-derived identity and market data retention rights require separate approval before any production paper fill. Preserve all disabled real orders, autonomous execution and bank transfers.

## CURRENT development — v0.2.99 offline realized paper loss-stop preflight, November 12, 2026 (America/New_York)

**Verified base:** v0.2.98 main `72455d35ad02027c195cbccf4684d92f71bdbeac`, exact-head PR #125 Actions #43366420941 passed; merged-main Actions #43366653601 passed. Existing Render Starter service `edgepilot-private-h9tl` with its original 1 GB disk deployed `dep-dbr97ne7bikc73en1h10` LIVE on the same SHA. Previous owner same-account Public value match and real MSFT quote retrieval are complete; no rerun needed for these synthetic changes.

**v0.2.99 scope:** Offline-only /dev/shm read-only per-account replay of synthetic realized P&L and historical worst cumulative loss, identifying when an explicitly supplied loss stop *would have* tripped. No production enforcement or quote marking, no live API import, no new schema or stop latch. Full paper recovery audit, account scope, cross-account isolation, encrypted recovery and no-overwrite rollback preserved. No paper fills activated, real trading, bank transfers, new providers or paid resources. See PAPER_REALIZED_LOSS_STOP_V0299.md.

**Next:** Verify exact-head PR Actions, merge, post-merge main CI and matched Render live status. Before actual paper loss-stop activation, design an operator-reviewed durable, account-scoped latched policy with atomic write enforcement, identity-derived session and licensed data provenance. Continue offline backup key rotation, crash cleanup, rollback safety and responsible market research without assuming rights. Do not repeat completed owner acceptance absent a targeted regression.

## CURRENT development — v0.2.98 dormant paper wallet/event chronology, November 12, 2026 (America/New_York)

**Verified base:** v0.2.97 main `7d8f9b07544cd1a4ab022b26b28b6c31ba629405`, push Actions #43364227347 passed, Render existing service `edgepilot-private-h9tl` deployment `dep-dbr8tb8jo6nc73erc860` LIVE at the same commit, original Starter/1 GB disk. Owner-reported same-account value match and real MSFT quote retrieval are already accepted and must not be repeated for offline changes.

**v0.2.98 scope:** Strict UTC valid calendar wallet opening timestamps and nondecreasing per-(user,account) event append chronology before synthetic archive sealing or restoration, with malicious date/order tests, encrypted-seal rejection and successful repair. Preserve all prior paper cash/reconciliation and quarantine audit, no production paper migration, no live orders, autonomous trading, bank transfers, paid infrastructure or credential changes. See PAPER_WALLET_CHRONOLOGY_V0298.md.

**Next:** Check PR CI, merge verified source, verify push CI and matching unchanged Render deployment. Continue dormant scoped loss-stop and idempotency design, no use of paper quote retention until rights confirmed, and harden crash-cleanup/old-key revocation before production backup/restore authorization.

## CURRENT development — v0.2.97 dormant paper event-time audit, November 12, 2026 (America/New_York)

**Verified base:** v0.2.96 PR #123 merged at main `c7b3170292f7c98324bcb569c1605664d1edbba7`; PR CI #43363374078 passed, merged-main GitHub Actions #43363596703 passed, and the same Render Starter service `edgepilot-private-h9tl` auto-deployed `dep-dbr8qm942hec73bb4pbg` LIVE. Its 1 GB disk and credentials remain unchanged. Previous owner Public snapshot same-account cent match and MSFT quote acceptance are complete; no new manual acceptance needed for offline source changes.

**v0.2.97 scope:** The previously dormant synthetic paper archive auditor verifies UTC event observed/created time syntax and chronological order before permitting sealing/restoration. Refuse corrupt source-observation chronology despite intact SQLite relations or otherwise valid arithmetic. Preserve all per-user and per-account isolation, revalidated quarantine, no-overwrite publication and production-disabled execution. No inference of market-data rights or real provider authenticity from an internally valid timestamp. See PAPER_EVENT_TIME_INTEGRITY_V0297.md.

**Next:** Verify PR CI, merge, post-merge GitHub Actions and matching live Render deployment. Continue production backup/restore operator safeguards offline and design explicitly approved quote-retention and server-authenticated identity paper controls before even considering active paper fills. Do not activate new paid services, autonomous brokerage execution or bank transfers.

## CURRENT development — v0.2.96 owner quote relative-spread research, November 12, 2026 (America/New_York)

**Verified base:** v0.2.95 main `2addc778425b2852677988ef4b0d6d6e5dc6c45c`, GitHub Actions #43359984066 passed, existing Render `edgepilot-private-h9tl` deployment `dep-dbr8avu8bjmc73bgecgg` confirmed LIVE at that exact commit. Service remains Starter with the same 1 GB disk. Earlier owner comparison and real MSFT Public quote acceptance are complete and preserved; do not repeat absent regression.

**v0.2.96 scope:** Show exact-decimal derived *relative* bid–ask spread, in basis points relative to the source midpoint, only where existing source quote receipt freshness is independently verified and both bid/ask timestamps are provided. Reject invalid timezone or calendar timestamps in browser. Do not add a history feed, account cache, storage, automatic requests, float arithmetic, broker execution, production paper fill or extra paid infrastructure. See OWNER_RELATIVE_SPREAD_V0296.md.

**Next:** Verify the PR CI, merge into main only after success, verify post-merge GitHub Actions and Render live at exact main SHA. Continue source-permission research, independent dashboard functionality and dormant tenant-scoped synthetic paper risk/restore work. Market data retention permission and production backup/restore sign-off remain outstanding. All live orders, autonomous orders and bank transfers must remain disabled.

## CURRENT development — v0.2.95 atomic offline paper recovery, November 12, 2026 (America/New_York)

**Verified previous milestone:** v0.2.94 PR #121 merged at main `9e9860b4cbcc1b3faf02c0bdad143595a10d2ad6`; PR CI passed, post-merge GitHub Actions run #43358994486 passed. Existing Render `edgepilot-private-h9tl` auto-deployed `dep-dbr86rojo6nc73eqk0q0` LIVE on that exact SHA. Existing Starter plan, 1 GB disk, encrypted accounts/recovery and multi-user architecture unchanged. Owner acceptance is already complete: same-account value matched official Public app to a cent, real MSFT quote retrieval worked, and last-vs-two-sided freshness was classified. Do not ask to repeat without a specific regression reason. No private amounts retained. Quote rights beyond actual read were not established.

**v0.2.95 scope:** Dormant **synthetic-only** Fernet-encrypted paper restore now stages the decrypted SQLite into a random private `/dev/shm` file; validates schema/foreign keys/cash-and-event replay; removes sessions, pending challenges, invitations and leases; quarantines restored Public links and passkeys; commits and fsyncs **before** atomic no-replace final-path hardlink. Failures remove only staged files, never overwrite an existing or raced destination. Fault tests cover bad authenticated SQLite, wrong key, fsync failure, collision and failed quarantine. This fixes the previous exposure of a partial/unverified *final path*, not production backup readiness, crash-residue collection, quote-rights attestation or fill activation. See PAPER_ATOMIC_RESTORE_V0295.md.

**Next:** Verify v0.2.95 PR CI, merge, post-merge GitHub Actions and unchanged paid Render deploy. Continue source-attributed owner research with data-permission guardrails and dormant paper ledger isolation. Before production paper-fills: independently verified quote retention rights, secured server-session paper-only APIs/CSRF/rate limits, operator-reviewed encrypted durable restore, rollback and old-key revocation controls. No live orders, autonomous trades or bank transfers. Preserve all existing owner/family credentials, accounts and recovery.

## CURRENT development — v0.2.94 owner acceptance and source-scoped spread, November 12, 2026 (America/New_York)

**Verified checkpoint:** v0.2.93 main `1cedfd760eecb67be305afa8462e20dc09200650`, PR #120 merged, GitHub Actions merged-main run #43357095572 passed; existing Render `edgepilot-private-h9tl`, original Starter plan and 1 GB persistent disk, deployment `dep-dbr7v0p42hec73ba42p0` reported LIVE on that exact SHA. No new service, paid resource, secret or recovery modification.

**New owner-reported real-device acceptance — completed:** A manual, selected-account Public portfolio snapshot was compared with that same account in the official Public app and matched to the cent. A manual Public MSFT EQUITY request returned actual Public-reported last, bid and ask. The page distinguished a stale last observation from a more recent two-sided quote within its server-receipt freshness window. Do **not** request the same test again unless a later code change specifically needs retesting. No actual balances, amounts, broker IDs, keys, raw provider responses or passphrases are kept in repository. Successful quote retrieval demonstrates real session market-data access, **not** quote retention/redistribution rights, historical licenses, execution rights or production paper-fill approval.

**v0.2.94 work:** Owner quote browser shows a purely ephemeral, source-derived bid–ask price-unit difference using 12-digit fixed-point BigInt math only when both sides have provider timestamps fresh at server receipt. Untimed/stale/incomplete books report unavailable. Freshness text always says **at receipt**, never guaranteed current; no second API call, cached quote, new permissions, background work, broker order or ledger change. Synthetic Node tests execute the actual shipped parser and check precision/book refusal. See OWNER_ACCEPTANCE_V0294.md.

**Next:** Verify branch CI, merge, merged-main CI and the same Render service deployment. Continue improving source-attributed analysis without fabricated history; advance strictly offline paper ledger backup/restore integrity, rollback and tenant isolation, and resolve provider data rights before any production paper fills. Preserve both legacy and independent login architecture, separately encrypted accounts, passkeys and recovery. Live trading, autonomous orders and transfers remain OFF. Do not require routine user actions for safe code-only development.

## CURRENT development — v0.2.93 failed owner MSFT quote, browser parser hotfix, November 12, 2026

**Verified starting point:** v0.2.92 main `9789ebd7afd3070d407818315f55afaea9f39159`, PR #119 merged and post-merge GitHub Actions run #43353225389 succeeded. Existing Render deployment `dep-dbr7eqs9v7es739t6es0` was live at the exact SHA; no new service/disk. The owner reported inability to retrieve an `msft` quote on the independently authenticated dashboard.

**Verified defect:** The v0.2.90/v0.2.92 browser validator `readSourceTime` mistakenly used doubled literal backslashes in a regex, rejecting ISO-8601 timestamps from a successful Public quote before the browser would display source prices. This is a confirmed defect but NOT proof that the user's actual source request succeeded or that their account has `marketdata` entitlement. The UI previously collapsed source denial and client validation into the same generic message; no private upstream response or readable request records established the exact provider result.

**v0.2.93 work:** Correct ISO timestamp validation and execute the **shipped JS parser** in regression tests using synthetic MSFT quote values. Compatible with Public's documented quote examples that omit bid/ask timestamps while explicitly marking those prices undated and `twoSidedFresh=false`; last timestamp remains compulsory. Separate HTTP refusal vs local validation error in UI without disclosing account/token/provider response body. Do not retry background or read private credentials. Preserve all prior tenant, encryption, recovery and dormant paper safety.

**Next:** Verify PR CI, merge, check post-merge GitHub Actions and existing Render. Owner reopens `/owner`, selects **Stock / ETF**, types `MSFT` and manually clicks **Retrieve source quote**. If still unavailable, ask for the sanitized status text or HTTP code—not balances, API keys, account IDs or tokens—to distinguish provider entitlement/network from parsing. Public's official quote endpoint requires `marketdata` scope; do not claim the scope is present until confirmed. No paid service, live orders, paper execution, bank transfers or autonomous brokerage orders.

## CURRENT development — v0.2.92 dormant historical provenance contract, November 12, 2026

**Verified starting checkpoint:** v0.2.91 PR #118 merged into main at `4954978e9663c3e40efdb8f383b9f9c20899112c`; PR GitHub Actions run #43352205155 and post-merge main run #43352452991 passed. Existing Render `edgepilot-private-h9tl` deployment `dep-dbr7boe7bikc73ekujk0` reported `live` on exactly that SHA, with the original Starter service/disk. Source-only comparison is available, but real owner-device match and real provider quote scope still require user acceptance.

**v0.2.92 scope:** Dormant `engine/owner_historical_bars.py` verifies externally supplied Public historicdata-v2-shaped historical observations against symbol, period, positive exact OHLC values, chronological timezone-aware nonfuture timestamps and nonnegative volume. It does not assume provenance or permission: output flags account identity, actual request origin, market-data license, caching, third-party distribution, completeness and paper fills unverified/disabled. It is not imported by app.py, has no broker or database access and provides no persistent history, inferred P&L, forecast, synthetic price or public API-call entitlement. Tests run with fake payloads only.

**Source licensing finding:** Public's official `Get quotes` API documents a `marketdata` scope; `Get bars v2` documents read-only history, but Public's Individual API Agreement reserves additional market-data terms and restricts third-party dissemination without prior written approval. Do not infer that historical API availability authorizes market-data caching, redistribution or a multi-user platform. Source-only validation can proceed; future active owner historical retrieval requires verified per-user Public permissions and a confirmed personal-use/right-to-store policy.

**Next:** Verify v0.2.92 PR/merged-main CI and existing Render deployment. Owner manually tests `/owner` against official Public account value and manually requests one quote, reporting pass/safe-unavailable without disclosing private balances or credentials. Prepare a strict production paper backup/restore preflight, with separate approval before any persistent paper fills. Preserve full existing multi-user architecture, identities, recovery and paid Render; no live orders/autonomous trades/transfers or paid service additions.

## CURRENT development — v0.2.91 owner manual account-value display comparison, November 12, 2026

**Verified starting checkpoint:** main `a584f726b107834c66115bf30836a98977996e02` v0.2.90. PR #117 merged and GitHub Actions #43350512741 completed successfully. Render's existing `edgepilot-private-h9tl` service and exact deployment `dep-dbr745psrm7s73dlobo0` reported live at that SHA with the original 1 GB disk and original auto-deploy. No new paid service or environment change.

**v0.2.91 scope:** Owner's independent identity-backed `/owner` UI includes a manually entered official Public-app display amount for the currently selected, freshly manually loaded Public brokerage account. Strict exact-cent client-side comparison with no persistence, submission, brokerage lookup, clock claim or conflation of independent account totals. Every new snapshot, account selection, logout and page exit clears this reference. This feature does **not** certify actual account-value reconciliation or license/availability of real `marketdata`; those require the owner's device and provider evidence. Maintains the dormant synthetic paper ledger, recovery and fully isolated multi-user architecture. No live orders, bank transfers, autonomous workers, production paper fills or additional paid services.

**Next:** Complete CI/merge/Render verification, then the owner compares the selected account against the official Public app and manually requests a source quote. If `marketdata` is unauthorized or unavailable, show a safe unavailable status; do not fabricate prices. Separately research Public historical bars and source retention permissions, and design an offline recovery/restore operator preflight before persistent paper trading may be enabled. Preserve all credentials, existing paid deployment, backup and multi-user systems.

## CURRENT development — v0.2.90 independent owner manual Public quotes, November 12, 2026

**Verified base:** main v0.2.89 `612c6227798c190c863611088554091c7dc5eee6`, PR #116 and post-merge GitHub Actions run #43348676641 passed; Render's existing paid Starter `edgepilot-private-h9tl` reported the exact SHA live with its original 1 GB persistent disk. User and private assets remain unchanged. Source-only synthetic v0.2.89 paper backup/restore checks are verified, but no real data migration or production restore occurred.

**v0.2.90 scope:** Authoritative *Public* manual single-symbol quote retrieval using the provider's official `/userapigateway/marketdata/{accountId}/quotes` contract for EQUITY or CRYPTO, scoped to independent identity owner cookie + CSRF and verified account/connection. Requires existing sole-owner flag and a second server-side eligibility check after network. Browser shows only actual provider values and timestamps with stale state and provider attribution; no invented market price, returns or histories. No background quote polling, persistent quote rights claim, additional paid feed, DB writes, paper ledger link, live trade, autonomous order or fund transfer. Real user provider `marketdata` scope and physical phone acceptance remain unproven; request may safely show unavailable. Tests use synthetic provider transport only.

**Next:** Verify PR and merged-main CI and Render, then owner manually tests `/owner` quote and reconciles read-only account total against Public. Later implement licensing-proven quote provenance/retention, read-only historical bar research, trustworthy paper execution guardrails and a production-safe encrypted recovery plan before any real paper-mode activation. All multi-user infrastructure, encrypted broker credentials, offsite backups, and identity/recovery remain preserved. Stop only at verified branch points or real blockers.

## CURRENT development — v0.2.89 paper-ledger encrypted recovery preflight, November 12, 2026

**Verified starting checkpoint:** `main` v0.2.88 `3c1c8db4b21000425912242083feb286754702a5`, PR #115 merged; post-merge GitHub Actions run `43345843142` succeeded. The preexisting Render Starter service `edgepilot-private-h9tl` deployed that exact SHA live with the same 1 GB attached disk; separate free passkey staging was not altered.

**Work in this milestone:** New offline paper recovery auditor checks per-account assumed-fill arithmetic and final wallet/position continuity; synthetic-only encrypted backup/restore checks these tables on sealing and recovery. Tests exercise isolated synthetic owner/member/multiple-account round trip, full quarantine of restored connections, malformed event/position state, and partial schema. Existing v0.2.88 paper ledger stays unimported by app.py, dormant and unexposed. Verify PR CI, merge only on green, then verify merged-main CI and Render without any secret, flag, disk or data mutation.

**Next:** Source-attributed research *without fabricated prices*, owner dashboard safe states and physical-device verification; licensed provider cache/analysis rights before any persistent evidence; independent authenticated paper-only endpoints only after production encrypted recovery and operator rollback gates. Ledger history verified by this milestone is not cryptographically source-signed nor a production backup product. Preserve all multi-user, vault and recovery architecture. No paid services, live trading, autonomous orders, bank transfers or additional enrollments.

## CURRENT development — v0.2.88 dormant tenant paper ledger, November 12, 2026

**Verified foundation:** `main` v0.2.87 `5a086bc93781a96fb94500e676754b34d1c1c428`, PR #114 and merged-main GitHub Actions run `43343900691` both passed. This added no-side-effect, fully offline market provenance/risk-budget paper preview; owner dashboard remains read-only. Earlier owner snapshot was received from Public but still needs official account-value reconciliation. Never claim a paper order UI is already functional.

**v0.2.88 implementation:** `engine/tenant_paper_ledger.py` introduces opt-in additive SQLite wallet, paper positions and assumed-fill events for each validated user+account, separate from legacy real fills and real Public cash. Manual paper seed, fresh/analysis-and-cache-rights-gated data, explicit friction, atomic BUY/SELL cash/cost-basis changes, conservative per-trade/protected exposure limits and UUID replay protection. Regression tests use two synthetic users, two owner accounts and a family account to assert no cross-account access. Documentation in TENANT_PAPER_LEDGER_V0288.md lists recovery inclusion and source-rights/identity API checks before any activation. This library is **not** imported by app.py; no production schema mutation, API, credential access, worker, order or paid resource.

**Next:** Run PR CI, merge only on pass, verify merged-main CI, then continue owner analysis and safely authenticated paper-only UI integration. Before enabling any persistent paper mode, explicitly rehearse backup/restore inclusion of these new tables and replace synthetic provider assertions with authoritative adapter checks. Render connector workspace selection still requires explicit confirmed workspace; no service configuration, deployment trigger, or paid resource change has been made by this feature. Live trading, autonomous orders, bank transfers and second-family testing remain OFF.

## CURRENT development — v0.2.87 quote-validated paper preview (offline), November 12, 2026

**Verified base:** `main` v0.2.86 `ac4571559d4271df20c8d1550866070955f17396`, GitHub Actions push run `43342021548` passed. Independently authenticated `/owner` is currently read-only; live Public account values previously returned in `/account` but the actual value remains unreconciled with Public and `/owner` still needs physical-device acceptance. Preserve original legacy login, tenant isolation, invitations, independently encrypted Public credentials and private backups. No second member rollout until the one-owner experience is functioning.

**v0.2.87 implementation:** New pure `engine/paper_preview.py` + `tests/test_paper_preview_v0287.py`: hypothetical BUY cost estimate from verified market observation with explicit rights, freshness, bid/ask, nonexecutability, real cost assumptions, synthetic paper funds and v0.2.86 risk-capacity bounds. Reject stale/missing provenance, unknown fees, unsafe amount precision, exceeded protected cash or risk budget, and prediction contracts lacking their distinct settlement model. No broker HTTP, tenant DB write, paper fill, order or transfer; not exposed in the owner dashboard or Render configuration. Must pass PR CI and merged-main CI before recorded as verified.

**Next milestones:** Connect validated, rights-permitted market research to the independent identity-backed owner dashboard without sharing legacy tokens, fabricating live prices or introducing paid feeds. Implement tenant/account-scoped paper ledger and explicit paper-only controls with crash-safe, idempotent hypothetical fills, fees, exposure/loss limits and safe replay. Test cross-account isolation and backing-store durability before presenting paper trades to real users. Live trading, autonomous orders and bank transfers remain OFF. Need explicit workspace choice before making authenticated Render connector reads (the connector does not yet have a selected workspace); no Render mutations are needed for this source-only milestone.

## CURRENT development — v0.2.86 dormant protected-balance risk cap, November 12, 2026

**Standing user instruction:** Continue EdgePilot in efficient, autonomous tested batches, do not stop simply because a version merged. Only stop for a major decision, verified branch point or actual safety/deployment blocker. Keep changes on development branches and merge verified small milestones to main; update README, CHANGELOG and this continuity record. The first real user must work completely before testing a second family member. All currently implemented multi-user identity, invitation flags, tenant isolation, encrypted recovery and original legacy login remain preserved.

**v0.2.85 confirmed:** GitHub PR #112, merged-main CI run `43341090854` and paid Render auto-deploy all SUCCEEDED; main commit `fde10296f1100a9c17e47e8f50af73bf9fc8d79f` is LIVE. New `/owner` uses only authenticated independent EdgePilot owner identity and existing server-scoped read-only Public API, never the legacy global-token auth; it requires an explicit user click to fetch a selected verified account portfolio. No extra paid services or new runtime flags. The user previously demonstrated a successful Public account portfolio retrieval in `/account`, but actual value reconciliation against the Public app and `/owner` real-device acceptance are still outstanding.

**v0.2.86 changes:** Existing pure, offline `engine/risk.py` erroneously accepted protected_pct from 1–100. New Decimal-only policy enforces the approved **0–99% inclusive**, catches missing, malformed, negative or non-finite money, requires explicit fresh/reconciled brokerage data, blocks unresolved external sales and rejects independent allocation above verified Public equity. It includes attributed, outside, open and unreconciled order exposure and independent verified broker buying power; spendable numbers always round down to cents and protected value rounds up. No order execution, brokerage calls, transfer path, API key, UI activation or production setting is added. Tests enforce exact corner cases including a very small account where an apparent fractional-cent allocation must never round up to risk.

**Next:** PR CI, merge and merged-main CI/Render deployment verification; continue integration with source-attributed market research and a truly isolated Observe/Paper ledger before any trading authorization. The current owner may manually open `https://edgepilot-private-h9tl.onrender.com/owner` and validate the dashboard, but this is not required for source-only risk math. Real trading, autonomous workers and bank transfers remain OFF. Keep protected backups and existing paid Render intact. See RISK_POLICY_V0286.md.

## CURRENT development — v0.2.85 secure owner-first home, November 12, 2026

**Reason for continuation:** The user asked why development had stopped after verified v0.2.84; no actual blocker or major product decision existed. Maintain the standing instruction to continue efficient development batches to major decisions, verified logical branch points, or actual blockers—not pause merely because CI is green. The single-owner-first priority remains: build out the existing owner's functioning UI/verified brokerage visibility, then trustworthy market data and risk-capped paper/research features. Preserve all completed multi-user schema, separate encrypted credentials, invitation flags, backup/recovery and original legacy login. No real new member was invited.

**Verified base:** v0.2.84 merged into `main` at `d884c8fabc255c9b03ca3c207b60def7b08f7569`; PR #110 and merged-main GitHub tests `43338481959` passed, and the existing paid Render Starter service deployed that commit live. Earlier the user demonstrated the independently authenticated `/account` page successfully retrieved their actual Public brokerage total and reported no open positions, without live trading. The exact financial amount is not copied into the public repository. It has not yet been reconciled against the official Public app; avoid claiming an account P&L or verified complete portfolio history.

**v0.2.85 scope:** A distinct `GET /owner` HTML shell and `owner-dashboard.js`, accessible by navigation from the existing `/account` and legacy `/` entry point. The new interface uses ONLY independent tenant identity cookies; it checks `/api/identity/session` for owner role, then `/api/identity/accounts` for a scoped linked account and the server-controlled temporary sole-owner portfolio flag. The existing `/api/identity/public/read/accounts/{internal-account-uuid}/portfolio` is invoked only on explicit owner click. It reuses existing backend account/credential checks and no-trade/no-transfer provider GET allowlist; the UI verifies every returned field before displaying a single selected account's sanitized USD total and positions. No automatic refresh, historic performance, fake trading metrics, provider credentials, browser storage or second account issuance. Signout, page exit, request failure and account selection changes clear data. The old legacy dashboard is not retired, and identity tokens are never elevated to legacy global control.

**Next:** GitHub PR CI and merged-main verification, Render deploy check, then real Android owner navigation acceptance `https://edgepilot-private-h9tl.onrender.com/owner` and Public-value reconciliation. Continue building trustworthy market-data-source labeling and Observe/Paper simulation with strict risk limits while keeping all live-order automation and bank transfers OFF. Do not add paid services, run redundant Android signed builds, or publish account keys/backups. See OWNER_DASHBOARD_V0285.md.

## CURRENT development — v0.2.84 first owner portfolio overview, November 12, 2026

**Owner live-read result:** The user sent a screenshot of the independent EdgePilot account page showing a *successful read-only Public brokerage response*, an account total value and no reported open positions. The specific financial value is private and is intentionally **not** stored in public GitHub documentation. The screenshot confirms the brokerage response path worked, not that the returned value matches the user's Public app, a market snapshot, or an investment performance calculation. v0.2.83 PR #109 merged as `b0e3f6955d9a99590b87c0c3099beffcf0b193da`, its PR and merged-main CI (run `43337097304`) passed, and the existing paid Render service deployed the version LIVE with no apparent startup errors. The user prioritized a functional single owner before later real multi-user testing. Invitations, separate tenant databases, encrypted Public connections, and the backup/recovery architecture must remain untouched; no additional family member enrolled.

**v0.2.84 change:** Introduce an owner-only `My Public portfolio` overview within `/account`. It remains hidden until `GET /api/identity/accounts` confirms the owner-scoped `soloOwnerPortfolioAvailable=true` with a linked Public account. **No backend API or broker call is added** by the overview: only a manual click on the existing `View read-only portfolio` button populates the summary from the already validated, account-matched sanitized response. It shows selected-account USD value, positions count, and local retrieval time, explicitly avoiding portfolio aggregation, quote timestamps, fabricated gains/losses or simulated balances. Signout, account switch, refreshed links and failed requests must clear stale values. A second registered member automatically disables the existing temporary solo pilot, preserving the durable multi-user architecture.

**Next acceptance:** Run PR/main CI, verify Render deployment, and perform owner on-device check of the new overview with a manual read; separately compare the account value with Public's official mobile app. Continue into a read-only owner dashboard, market-data provenance, risk-safeguarded Observe/Paper research; do not enable autonomous orders, live brokerage execution, or bank transfers, and do not add paid services. Keep PUBLIC GitHub free-runner and private-account safeguards.

## CURRENT development — v0.2.83 read-only Public portfolio response contract (owner first, future members preserved)

**Next tested target:** The owner-directed single-user priority continues. Existing paid Render service `edgepilot-private-h9tl` deployed v0.2.82 `459a7c96eb08520e110a4d462bd780d149abc77e`; owner explicitly approved `EDGE_SOLO_OWNER_PORTFOLIO_ENABLED=true` and the service redeployed the SAME code successfully under `dep-dbr4ss0u01pc73a6c3o0` at 23:41:18 UTC. No new paid service, signed APK, user registration or change to the three previously activated private family invitation flags. A real provider portfolio/holdings response **has not been confirmed** by the owner, so this milestone must not claim single-user completion.

**v0.2.83:** Public's official `GET /userapigateway/trading/{accountId}/portfolio/v2` response includes an `accountId`; require its exact match against the previously verified user-owned provider account before returning any portfolio data. Preserve current sanitized internal UUID, bounded USD cents, per-account and identity ownership checks, no orders/transfers and both before/after request sole-owner checks. Position quantity is now strictly finite decimal with up to 18 fractional places (supports negative short values), no fake default zero and no blind truncation. The manually invoked account screen renders USD in a string-safe way, displays neutral *units* rather than misleading equity-only *shares*, clear empty holdings feedback and a device retrieval time explicitly **not** a quote timestamp. No auto polling, AI buying signals or broker writes added. Fixtures and synthetic tests cover invalid account/quantity inputs without real network access. See PUBLIC_PORTFOLIO_COMPATIBILITY_V0283.md.

**Acceptance gates:** PR and merged-main GitHub tests must pass, Render redeploy must succeed, then authenticated owner manually opens `/account`, selects a verified Public link, and taps `View read-only portfolio`. Only successful actual user-device response or specific sanitized failure may establish progress. If the response fails, fix precise contract/UX issue without disabling or modifying existing multi-user work, legacy login, off-service encrypted v0.2.74 owner backup or protected trading/bank-transfer settings. No further live-account permission changes currently needed.

## CURRENT production checkpoint — v0.2.82 owner read-only Public pilot ENABLED, awaiting first real data acceptance

**November 12, 2026, 23:41 UTC.** User clarified the current project priority: one working owner before second-member device testing, retaining all multi-user schema, authentication, invitations, separate encrypted Public account storage and recovery tooling. Version `v0.2.82` PR #108 merged at `459a7c96eb08520e110a4d462bd780d149abc77e`; PR and merged-main GitHub tests (run `43330218480`) passed; existing Render paid Starter service `edgepilot-private-h9tl` deployed that commit successfully.

The owner then **explicitly authorized** a first live **read-only** Public portfolio test for the existing independent owner. A Render merge-mode environment update set ONLY `EDGE_SOLO_OWNER_PORTFOLIO_ENABLED=true`. The existing source version redeployed as `dep-dbr4ss0u01pc73a6c3o0`, reported `live` and succeeded by 23:41:18Z. App logs from that startup contained no obvious startup errors. This does NOT prove real portfolio response success. No new hosted services, database changes, brokerage keys, signed builds or paid resources were added; `EDGE_FAMILY_INVITE_COEXISTENCE_ENABLED`, `EDGE_TENANT_SIGNUP_ENABLED`, and `EDGE_PERMANENT_OWNER_INVITES_ENABLED` remain unchanged from their previous approved values, with **no invitation issued**. The user said to defer real second-family-member enrollment rather than disable multi-user capabilities.

**Current human acceptance step:** On Android, open `https://edgepilot-private-h9tl.onrender.com/account`, sign in as the independent owner, and under `Your Public accounts (read-only)` / `Linked accounts`, tap `View read-only portfolio` for the verified owner Public account. User should report whether actual numeric balance/holdings appear or the precise error text, without disclosing financial account number, token or brokerage credentials. No actual Public balance or holding has yet been confirmed in this chat by a real owner request. The new solo pilot checks exactly one enabled owner identity both before and after external provider HTTPS; registration of another member immediately disables read-only portfolio access without deleting any multi-user features.

**Safety and rollback:** Legacy owner login, protected databases and verified older v0.2.74 encrypted owner archive must remain intact. No trade execution, automation worker or bank transfers were enabled or authorized. If real portfolio read fails, diagnose the provider contract and client UX safely using synthetic tests; do not loosen owner/account isolation or invite a second user. If needed, disable ONLY the solo portfolio flag `EDGE_SOLO_OWNER_PORTFOLIO_ENABLED=false` in merge mode, leaving all other current environment flags unchanged. Store this checkpoint on a documentation branch rather than merging a docs-only redeploy; merge with the next verified substantive code milestone.

## CURRENT approved priority — v0.2.82 single-owner functionality FIRST, multi-user retained (November 12, 2026)

The user explicitly deferred live two-phone/multi-user testing **without authorizing removal or disabling of any multi-user work already completed**. Shift milestones toward one functioning existing owner: real Android authentication, independent Public connection, safe read-only portfolio/holdings, verified market feeds/AI research, and Observe/Paper risk-controlled operation. The existing invitation system, tenant role isolation, separate SQLite databases, encrypted archive tooling, and previously approved invitation flags remain in place; **issue no real invitation** until the user explicitly resumes that test. Do not clear invite settings, delete tenant members, drop databases, rotate keys, undo security gates or move to a single-user-only architecture.

**Verified current production history:** v0.2.81 `3bf8bc02cccbb2816f00d6ccb00edd71470f6924` deployed LIVE to the existing paid Render service with the same persistent /data disk. Owner screenshot showed a passing sanitised SSH-only first-invitation check: one verified owner identity, one decryptable Public connection and account linkage, no second member, original independent legacy SQLite present; no trading/autonomous worker/bank transfers. Based on prior approval, a merge-only Render environment update enabled only the three bounded invitation gates; Render deployment `dep-dbqug8mk1f9s73fd3410` returned LIVE. The owner subsequently reported the owner login/interface verified, but **did not issue a first family invitation**. Real portfolio balances, live research and signed-app two-device acceptance are not yet proven. The original v0.2.74 encrypted linked-owner archive was separately checksum verified off-service, but a full lost-server recovery was not rehearsed.

**v0.2.82 implementation in feature branch:** New independent `EDGE_SOLO_OWNER_PORTFOLIO_ENABLED` switch defaults OFF and intentionally leaves all family flags as configured. The authenticated owner can eventually view their own previously linked read-only Public portfolio only while **exactly one active owner identity exists**; any additional registered member causes fail-closed 404 both before and after a provider call. The HTTP adapter remains limited to allowlisted Public token/account/portfolio GET functionality with no order/transfer path. The Android/browser account page shows the portfolio button only when the server returns a true owner-only capability, while hiding dormant monitor/watchlist controls. This source change alone must not activate live portfolio reads. Test against fake provider only; CI before merging. See SINGLE_OWNER_PRIORITY_V0282.md.

**Next logical work:** Verify v0.2.82 PR/merged-main CI, then owner-confirmed separate opt-in for the first real read-only portfolio request, after checking Public's supported response contract. Avoid unnecessary free-runner builds and new paid services. Follow with trusted market/15-minute research and paper mode; live orders/automatic trading and bank transfers stay OFF until explicitly approved.

## CURRENT verified operational checkpoint — private invitation flags enabled, **no invite issued** — November 12, 2026

The owner followed the SSH-only v0.2.81 operator preflight from their Android Termux client on the existing Render production service and supplied its sanitized output. It reported one active independent owner login session, one encrypted verified Public connection/link, zero other registered users, separate private legacy/tenant DBs, no existing pending invitation and `inspection=passed`; live trading, autonomous orders and bank transfers all false. Tool correctly reported that original legacy login from a physical phone, current Public network access, second device, second Public account and external archive/key custody were *not* tested by the inspection. Separately, the owner had earlier shown matching SHA-256 across the encrypted v0.2.74 owner archive, Android local copies and re-downloaded Google Drive copy; do not conflate that older archive with a post-member multi-user backup.

The user's existing approval allowed a controlled invitation-only **activation with separate confirmation before first real invitation issuance**. After the passing sanitized preflight, the three production flags `EDGE_FAMILY_INVITE_COEXISTENCE_ENABLED`, `EDGE_TENANT_SIGNUP_ENABLED` and `EDGE_PERMANENT_OWNER_INVITES_ENABLED` were updated to `true` **together by a merge-mode environment update** on the paid Render service `srv-dbocnb3m8hqs7386trvg` / `edgepilot-private-h9tl`. Render API-triggered deployment `dep-dbqug8mk1f9s73fd3410` returned LIVE; associated deploy event succeeded and inspected app startup logs did not contain an obvious failure. The application code remains v0.2.81 `3bf8bc02cccbb2816f00d6ccb00edd71470f6924`. No new service, disk migration, credential exposure, generated token, registered member, order or transfer.

**Next gate (requires user/device):** On existing Android, manually confirm the original dashboard still accepts the legacy token and that the distinct EdgePilot owner identity login at `https://edgepilot-private-h9tl.onrender.com/account` displays the private invitation panel. Do **NOT** press Create a private invitation until the user separately approves the first real invitation and determines the intended second member. If an owner login is inaccessible, disable all three invitation flags to `false` together using merge mode; keep all existing user accounts, backups and the original Fernet key. After a real second member joins, new invitations should be paused and an authenticated encrypted multi-member backup verified off-service before broader rollout.

These notes have been committed only to a nonproduction documentation branch; merging docs-only to `main` would restart the Render service and trigger unnecessary CI. Carry them into the next verified substantive feature/acceptance merge instead.

## CURRENT development — v0.2.81 safe first family inspection CLI, November 12, 2026

**Production verified (Render metadata only):** Workspace `Belenos's workspace` / existing paid Starter web service `edgepilot-private-h9tl`, service ID `srv-dbocnb3m8hqs7386trvg`, branch `main`, auto-deploy-on-commit, existing mounted 1 GB private disk at `/data`. Render reported v0.2.80 commit `743c7cc1f8f1be96ee59893f32fe5edf0be48a0d` LIVE with successful build/deploy events. This does **not** prove DB contents, environment switch values, real login or credential decryptability: the connected Render API has no execution/SSH or secret-reading action. Do not infer that running a read-only preflight has happened.

**v0.2.81 changes:** Adds `backend/tools/inspect_family_invitation_readiness.py` for the existing user-held Render SSH identity. Exact `--approve "INSPECT PRIVATE FAMILY READINESS ONLY"` plus ephemeral `EDGE_FAMILY_ROLLOUT_PREFLIGHT_ALLOWED=true` are required per call. Enforces fixed `/data/edgepilot.db` and `/data/edgepilot-tenants.db` and the v0.2.80 sole owner, active encrypted/verified Public linkage, no-live-order/no-worker/no-signup state and no pending invitations. Prints only sanitized aggregate JSON, never an API key, login identifier, recovery passphrase or full env. On failure refuses with a static message and changes no setting. Corrected the audit result to state `legacy_login_end_to_end_verified=false` and `public_network_verification_performed=false` rather than claiming to have exercised real login or Public.

**Next human/operator interaction:** Once PR and merged-main tests pass and the service auto-deploys, the owner runs the one read-only SSH command from Termux or an existing authorized shell and shares **only the sanitized report**. Separately reconfirm owner login and the verified off-Render encrypted linked-owner archive and independent key custody. The earlier backup SHA-256 reportedly matched on Android and private Drive download; no key or file is to be uploaded to GitHub or chat. If the inspection refuses, investigate privately, do not change invitation settings.

**Approved architecture, not yet activated:** Invitation-only coexistence on the current backend, preserving legacy login and independent tenant users. The user approved a controlled production readiness/activation stage but requires another confirmation **before the first real invitation is issued**. Do not preemptively activate with failed/missing readiness evidence. Never enable live trading, autonomous orders, bank transfers, public self-signup, paid additions, or tenant-only legacy retirement. No new Render service is needed. See OPERATOR_FAMILY_READINESS_CLI_V0281.md.

## CURRENT development — v0.2.80 first private family invitation readiness, November 12, 2026

The owner-approved invitation-only coexistence backend v0.2.78 is merged and main CI verified (`f9ccb329`, run `43244459815`). v0.2.79 owner-only masked invitation interface passed PR #105 CI and merged at `84c9fa8f187bb5c318019fa5eeb96ab903c92d00`. The invite UI is still hidden on production because private issuance and registration remain disabled. No actual owner code, second member, provider key or public login was created.

v0.2.80 is a **dormant read-only** operator inspection for before the first actual family invitation. It requires explicit `EDGE_FAMILY_ROLLOUT_PREFLIGHT_ALLOWED=true` only for manual inspection; authenticates the paired private SQLite files, one Argon2id owner with existing independently verified encrypted Public link and working original Fernet key; refuses unsafe runtime flags, active pending invitations, additional members or already enabled invite pathways. It returns only aggregate nonsecret data with explicit `member_registration_authorized=false` and no assumptions about actual backup custody or physical phones. The tool is not installed in any live route or startup hook and must not be run on Render or used to enable flags without independent user approval.

Next: PR and merged-main GitHub CI, operator backup/key-custody review, then request *separate explicit production authorization* for a controlled single invited member on a second phone. Maintain all protected backups, original owner login and paid Render data; no new services, public GitHub secrets, order execution, autonomous trading or bank transfers.

## CURRENT development — v0.2.79 private owner invitation UI, November 12, 2026

The owner approved invitation-only coexistence; backend v0.2.78 merged to main as `f9ccb329c74fdde7bc2c05a3bba89cbc13d8ca0a`. Both PR #104 test run `43244085948` and merged-main run `43244459815` completed SUCCESS. The independently default-off `EDGE_FAMILY_INVITE_COEXISTENCE_ENABLED` cannot enable enrollment by itself: it requires separate private owner invitation and signup gates, one active owner, prepared shared paid disk, encrypted Public discovery-only pilot, no live execution, passkeys or tenant-only retirement.

The next v0.2.79 feature branch adds an owner-only invitation panel to `backend/static/identity.html` and `backend/static/assets/identity.js`. The server's authenticated owner session returns only a nonsecret capability boolean; the existing owner-only POST performs the actual protected one-hour invitation creation. UI shows a masked one-time token to its creator, allows explicit reveal/copy and clears it on account change/signout, without persisting tokens in URLs or browser storage. This is still developer-only and requires test validation; no owner has been invited in production. Continue respecting PUBLIC GitHub repo constraints and use no real API keys or archive materials.

Next: GitHub PR/main acceptance for v0.2.79, then a separate operator readiness plan (two-device acceptance and verified multi-member recovery) before considering an approved live invitation activation. Do not touch Render environment or enable trading, autonomous orders, transfers, portfolio monitoring, passkeys or new paid services.

## CURRENT development — v0.2.78 invitation-only private family coexistence, November 12, 2026

The owner explicitly approved the previously recommended **invitation-only coexistence** architecture (not tenant-only forced retirement). This is authorization to develop and synthetically verify the new default-off safety pathway, **not** permission to activate real member signup or invite a live second person. The existing paid Render service and both /data databases, user credentials, v0.2.74 off-service recovery archive, legacy login and protected signing workflows must remain unchanged.

The v0.2.78 branch adds `EDGE_FAMILY_INVITE_COEXISTENCE_ENABLED` as an independently default-off opt-in, guarded by the exact active discovery-only pilot, prepared tenant storage and authenticated owner, explicit signup and owner invitation gates, a 10-user cap and disabled tenant-only cutover, passkeys, watchlist/monitor, automation worker and order execution. Reuses existing one-hour single-use private invitations, owner+CSRF verification, Argon2id member creation and separately encrypted Public secrets. It neither unlocks open signup nor adds real Public portfolio access. Synthetic integration tests exercise independent member registration/account discovery with a fake Public HTTP adapter, legacy session continuity and cross-user denial. Rollback must disable all three invite flags while preserving existing accounts.

The repository is PUBLIC following PR #102; source and test fixtures only. Never commit real keys, archive materials or member names. PR/merged-main CI must pass; no additional paid services or redundant APK builds. **Next gates:** development merge, additional UI and operator acceptance for enrollment, separately verified production backup/recovery and second physical phone acceptance. No production signup activation, new brokerage capability, automatic trading or bank transfers have been approved.

## CURRENT source checkpoint — v0.2.77 public-repository CI safety, November 12, 2026 UTC

**Verified repository status:** `BelenosCreations/edgepilot-personal` is publicly visible. Public-source preparation PR #102 merged at `8282564b6a13ceae2254a1f6dc3beb6b491ebd1f` with successful historical credential-pattern scan, application tests, unsigned Android test build and merged-main tests. GitHub openness is a cost-saving source-hosting decision only. The existing paid Render service, private databases, verified v0.2.74 linked-owner archive and user-specific broker secrets were NOT migrated or intentionally published.

**v0.2.77 development change:** Extend the existing normal PR/main test job with a quick shallow-checkout source scan based on the non-disclosing history scanner, leaving costly complete-history checkout to the existing targeted/manual workflow. On Android-source PRs compile all unsigned test variants as before, but upload debug APKs only for explicitly manually dispatched jobs, with three-day retention. Preserve manual-only main-branch pinned Android signing workflows; their public GitHub Actions artifacts are **not automatically private**. Add synthetic token-detection/no-output tests and safeguards for workflow permissions and ignored recovery/signing materials. Before claiming a verified release, confirm the pull request and main GitHub CI results. No real tokens, credentials or bank data belong in GitHub.

**Remaining architecture decision:** The current safe runtime deliberately prevents inviting a real second user while legacy owner authentication remains active. Next production onboarding branch still requires an explicit user choice between narrow invite-only coexistence and tenant-only legacy retirement, plus controlled physical two-phone acceptance. It is not authorized by switching GitHub to public. All worker automation, live orders, bank transfers, real public signup and new paid services remain blocked. Keep prior recovery keys separate from the encrypted archives.

## CURRENT merged checkpoint — v0.2.76 verified main CI, November 12, 2026

The repository latest main is v0.2.76 at merge commit `f5b40a2b5d46d35ceae0d3fe84af7c6ed809d3d1`; PR #100 and merged-main EdgePilot tests passed (main run `43220146243`). The feature adds only a dormant future-family two-to-ten-account encrypted backup rehearsal. A real production archive was **not** created by this merge, because live production has only one independent enrolled identity. No Render workspace/service status check was completed in this milestone; do not claim it is live merely because GitHub main is green.

Main also contains v0.2.75 dormant paired-identity and encrypted-connection audit (main commit `4505bfe0`, run `43218457319` success), and the v0.2.74 first linked-owner archive operator verified byte-for-byte across Render, Android and downloaded private Drive copy. Keep these backups and all credential recovery materials intact. Neither Google Drive key-custody separation nor a full production lost-server restore has been audited.

**Next major decision/branch:** The present shared-storage selector and Flask discovery-only policy intentionally **reject production invitations/signup while the old legacy owner login coexists**. A real second member therefore requires a separately reviewed rollout choice: either a narrowly gated *invite-only, discovery-only coexistence pathway* preserving the working legacy login, or deliberate tenant-only legacy retirement after complete recovery acceptance. Do NOT silently relax either policy, enroll a real member, enable passkeys, portfolio reads, autonomous workers, orders or transfers. Confirm owner preference/approval and two-device readiness before making the production permission change. Further code-only synthetic improvements may continue without production activation.

## CURRENT development — v0.2.76 future multi-member encrypted recovery (dormant)

The v0.2.75 synthetic family audit was merged into main at `4505bfe01382c27e09a8aa11c2fa0e462be4002f` and merged-main EdgePilot CI run `43218457319` concluded SUCCESS. A new version v0.2.76 feature branch adds an engine-only, double opt-in encrypted recovery rehearsal for two to ten distinct independent users. It uses a **new** AES-256-GCM archive magic, RAM-only consistent SQLite snapshots, a separate authenticated RAM restore, source read-only checks and sanitized counts. Before encryption, only its temporary copy clears active identity sessions, login failures, signup attempt hashes, pending passkey challenges and unconsumed invitations. It verifies no shared Public secret and enforces the original Fernet vault key and independent 32-byte offline archive key. No source DB mutation, operator CLI, web route, external network request, app settings change or new paid service.

This is a **future-family** recovery capability only. Production still has one linked owner, and the new code intentionally refuses a one-member archive. The user's v0.2.74 off-Render backup and existing archives are intact. No second phone, second independent Public account, tenant-only cutover, new registration or multi-member disaster recovery has been verified. Before any production use: PR and merged-main GitHub CI, operator key-custody review, user-approved family member onboarding, controlled real two-user acceptance, and verified new archive transfer/off-service restore. Keep live orders, autonomous workers and bank transfers disabled.

## CURRENT development — v0.2.75 private-family recovery readiness (not activated)

On top of verified v0.2.74 source, the next incremental feature branch adds `backend/engine/family_recovery_readiness.py` plus synthetic tests and documentation. It is **not called by the runtime**: default-off operator audit requires `EDGE_FAMILY_RECOVERY_INSPECT_ALLOWED=true`, the existing safely configured discovery-only pilot and both private paid-disk SQLite databases. It verifies all family identities are paired, at most ten private users including exactly one active owner, that stored Public secrets are Fernet-recoverable and no two users share an identical secret, and that linked accounts remain correctly scoped. No user, account, key, hash or broker ID leaves its sanitized aggregate report. No archive is created, no secret is moved, and no live feature flags change.

This read-only preflight is **not** a production member invitation, approved trading rollout or multi-member backup. The v0.2.74 completed owner archive remains the only externally byte-verified linked-account recovery; preserve it. Follow-up: encrypted multi-member snapshot/isolated restore with robust tests, then controlled physical two-phone two-independent-Public acceptance and separately authorized invitations. Verify PR/main CI and README/CHANGELOG before claims of a merged milestone.

## CURRENT verified operator checkpoint — v0.2.74 off-service linked-owner archive, November 12, 2026

**GitHub main** is v0.2.74 at `b2e4483da54dcbda3d02428a3bde8d5e7d50a205`; merged-main EdgePilot tests run `43211039850` concluded SUCCESS. The owner ran the v0.2.74 console-only linked-owner backup on the existing paid Render instance and showed `backup_verified=true`, `isolated_restore_verified=true`, `credential_decryptable=true`, `restored_login_sessions=0`, one verified linked account and one encrypted Public connection; live trading and bank transfers were reported disabled. The archive was on `/dev/shm` and initially had `off_service_copy_verified=false`, which means only the **tool's own** on-server attestation was incomplete.

The owner then transferred the encrypted archive by authenticated SSH into private Termux storage on Android, matched its SHA-256 against the reported server archive digest, uploaded a copy to the private Google Drive `Edgepilot backup` folder, renamed the local upload-source file, **downloaded the cloud archive separately**, and compared both SHA-256 hashes. Both matched:
`0248ba7bc5af58a8e6883384b6c34e2cb5990d8a939fac292a8cda305ef034ad`.
This is operator-screenshot-confirmed **off-service archive byte identity**; it must not be confused with independently verified full production recovery, tenant-only migration, or restored Public network authentication.

Retain all pre-existing backups. The encrypted archive is only one recovery component: a complete restore requires the Android-held AES recovery key **and** the original independently recovered `EDGE_CREDENTIAL_KEY` (Fernet) for stored Public credentials. The screenshots also showed files described as `Public API key` and `Edgepilot backup passkey` alongside backups in Google Drive; do not assume separated key custody, and never read, print or copy these secrets. Recommend password-manager separation before broadening production access; changing credentials needs separate operator approval. Cloud folder visibility and exact recovery-key custody have not been audited.

**Next development:** Preserve default-off safety gates. Build and test synthetic multi-member backup/readiness and tenant-isolation paths without inviting real users, turning on portfolio reads, moving credentials between tenants, enabling global workers, orders, transfers, or new paid resources. Keep README, CHANGELOG and this continuity note current. No physical second device or independent second Public account has yet passed acceptance.

## CURRENT checkpoint — v0.2.74 verified owner Public connection; backup code in development, November 12, 2026 UTC

The user independently tested the active v0.2.73 Public discovery-only
pilot at https://edgepilot-private-h9tl.onrender.com/account on Android.
Screenshot showed one "Encrypted Public connection", a discovered
"BROKERAGE" account, and a "Linked accounts" entry stating
"Public BROKERAGE · ownership verified; portfolio, monitor, orders
and transfers disabled". The old legacy Public key was NOT copied.
This is a real external acceptance beyond the prior synthetic tests,
but there is no live two-account / second device acceptance and
no portfolio or trades authorization.

The prior encrypted tenant-owner archive edgepilot-tenant-owner-
20261112.epbk was created/isolated restored and uploaded off Render
before a Public API credential and account link were added, so that
archive DOES NOT contain the now-saved encrypted Public connection.
v0.2.70 backup is explicitly limited to dormant first-owner state
(no sessions, broker features disabled). Do not weaken that tool.
Instead v0.2.74 adds a separate first-linked-owner recovery snapshot:
consistent /data tenant DB copy to tmpfs, decrypted credential
verification under existing EDGE_CREDENTIAL_KEY without revealing
secret, removes tenant_identity_sessions and tenant_auth_failures only
in a temporary snapshot to prevent session resurrection after restore,
AES-256-GCM with the private offline 32-byte phone recovery key,
private no-overwrite archive in /dev/shm, and isolated read-only
restore proof. Both live DB files remain untouched; original legacy
login and Public key remain separate.

This code MUST pass PR and merged-main GitHub CI, be merged, and
be confirmed live on the EXISTING paid Render Starter service before
the owner runs it through LOCAL Termux with the separately held backup
key. After backup succeeds, user must copy encrypted archive off
Render, verify downloaded SHA-256, and upload to their existing private
Google Drive Edgepilot backup folder. Prior backups and GPG recovery
must remain preserved. Do not treat source code deployment as a
confirmed production backup. No new paid resources, portfolio
balances/holdings, monitoring, orders, bank transfers, public
signup, invitation enrollment or second-device account are enabled.

## CURRENT operator checkpoint — v0.2.73 live private Public discovery, November 12, 2026 UTC

GitHub PR #95 for v0.2.73 was green, merged to main commit
b40874ef6ce1ee9d7282bb3b4faa54a669ae4e4e, and the
merged-main GitHub action run 43150624623 concluded SUCCESS.
The existing paid Render Starter service edgepilot-private-h9tl
then deployed this commit live. With the user's explicit approval,
we merged (DID NOT REPLACE) environment flags to activate ONLY:
EDGE_PERMANENT_READONLY_PILOT_ENABLED=true,
EDGE_TENANT_ACCOUNT_READS_ENABLED=true,
EDGE_TENANT_PUBLIC_VAULT_ENABLED=true,
EDGE_TENANT_PUBLIC_READONLY_ENABLED=true,
EDGE_TENANT_PUBLIC_DISCOVERY_ONLY=true,
plus the previously established identity/isolated tenant DB gates.
Render deploy dep-dbqjf4ec6qcc73fhamrg was confirmed LIVE.

Still disabled: EDGE_PERMANENT_TENANTS_ONLY=false, enabling
the original legacy owner token login; EDGE_AUTOMATION_WORKER_ENABLED
and ENABLE_LIVE_ORDERS remain false; signup, invites, passkeys,
monitor preview, watchlist editing, active tenant portfolio,
bank transfers and autonomous orders remain disabled.
The stable existing EDGE_CREDENTIAL_KEY was preserved, not printed,
changed or copied to chat. The original legacy Public credential
remains in /data/edgepilot.db and has NOT been migrated. The tenant
owner uses /data/edgepilot-tenants.db. Both share the same existing
1 GB paid Render persistent disk; NO new service was purchased.

CRITICAL DISTINCTION: Render reporting LIVE does NOT mean the
user has supplied a Public secret or that provider account discovery
has succeeded. User must open the secure /account page, sign in as
Belenos-Owner, generate/copy their own Public PERSONAL API secret
privately from official Public account settings, Save encrypted key,
select the new independent connection, and tap Find my Public accounts.
Only the provider token POST + account list GET are allowed by the
discovery-only pilot; even direct portfolio URLs return 404.
User should not paste keys or account identifiers into chat.
Once account linking is confirmed, prepare an updated encrypted
off-service tenant snapshot because previous backup predates the
newly stored credential. The existing Google Drive encrypted owner
identity backup and original owner credential recovery remain intact.

Next: physical Android end-to-end validation of the new scoped
Public secret storage and account-list/discovery flow. Do not enable
portfolio holdings, real order placement, transfers, workers,
new members, auto-trade or tenant-only cutover without a separately
verified development stage/authorization.

## CURRENT checkpoint — v0.2.73, approved first Public account discovery, November 12, 2026 UTC

The owner approved LIMITED identity-scoped Public API secret encryption,
provider-verified account discovery, and verified account binding on the
existing paid Render instance. The independent Belenos-Owner HTTPS login
and logout and legacy owner login were confirmed on Android; the separate
tenant owner backup is privately saved on Android and uploaded to Drive.
Current GitHub main before development was v0.2.72, all CI passed and
existing paid Render Starter deployment was live.

v0.2.73 adds a feature flag
EDGE_TENANT_PUBLIC_DISCOVERY_ONLY=true to the existing
tenant Public read-only adapter, explicitly disabling portfolio API
and frontend viewing controls. Provider access must remain limited to
POST short-lived access token and GET account list; no holdings, order,
or transfer endpoints may be called. A new synthetic two-user, two-key
integration regression checks owner isolation and no original global
Public key reuse. This development CHANGE DOES NOT ITSELF ACTIVATE
Public features. Required active flags on the existing service:
EDGE_PERMANENT_READONLY_PILOT_ENABLED=true,
EDGE_TENANT_ACCOUNT_READS_ENABLED=true,
EDGE_TENANT_PUBLIC_VAULT_ENABLED=true,
EDGE_TENANT_PUBLIC_READONLY_ENABLED=true,
EDGE_TENANT_PUBLIC_DISCOVERY_ONLY=true; retain identity, storage,
original token login and disabled background worker/trading/signup.
Stable existing EDGE_CREDENTIAL_KEY must be retained unchanged.
No actual user key has been entered by the assistant.

After PR and merged-main CI and Render deployment, merge flags into
existing Render environment (no replacement), verify new deployment
live, and ask the owner to independently input their Public API
personal secret on the real HTTPS account page to test discovery.
NEVER paste keys, passwords, account IDs or JWT in chat. The new
tenant DB will have sensitive encrypted credentials not yet included
in the earlier tenant-owner backup if the operator saves one; plan
a later recovery snapshot that includes connections, without exposing
credentials. No new paid service, member registration, portfolio
balances/holdings, independent second physical device, orders,
bank transfers or automated execution is authorized.

## CURRENT checkpoint — v0.2.72, November 12, 2026 UTC

The independent Belenos-Owner Argon2id identity was already created
and its password verified via read-only trusted SSH. An encrypted,
authenticated-restored owner tenant snapshot was copied with matching
SHA-256 to private Android storage and uploaded to the existing
Google Drive Edgepilot backup folder. Drive redownload comparison
remains unverified.

On the same paid Render service, an auth-only environment rollout
activated EDGE_IDENTITY_AUTH_ENABLED=true with isolated
/data/edgepilot-tenants.db and left the existing
/data/edgepilot.db token login available. The user supplied a
REAL PHYSICAL ANDROID SCREENSHOT showing "Secure EdgePilot account
session active" and "Welcome, Belenos-Owner" at the independent
HTTPS /account UI. In the next message, the user confirmed the
requested sign-out and original legacy login tests "Works properly".
Treat this as operator-confirmed acceptance, not as assistant-side
browser execution. The Observe/Paper worker, tenant signup, Public
vault, tenant read-only account API, passkeys, live orders and all
bank transfers remain disabled. No extra paid services were added.

v0.2.72 adds an exact-profile Flask regression under temporary
separate owner + tenant DBs to prove that independent identity
sessions cannot inherit the legacy session and vice versa,
different synthetic users cannot see each other's tenant identity,
and CSRF sign-out preserves unrelated logins. Tests also assert
new-user enrollment and broker features remain disabled.
No new runtime feature is activated by this development step.

Next: verify PR and merged-main GitHub tests plus successful Render
deployment of v0.2.72; inspect default-off user/account Public
binding flows and prepare an owner-approved *read-only* independent
broker-connection rollout without copying the original global
Public key. Real second-device/member/second Public account still
requires operator-driven acceptance; do NOT create real members,
enable broker features or retire the original login automatically.

## CURRENT operator checkpoint — Controlled HTTPS identity login enabled, November 12, 2026 UTC

The user explicitly approved enabling a limited, reversible identity-only
HTTPS login test on the same existing paid Render Starter service. The
Render environment variables were merged (NOT replaced) to retain the
original /data/edgepilot.db while selecting the separate existing
/data/edgepilot-tenants.db. EDGE_SHARED_TENANT_DB_PREPARE=true,
EDGE_TENANT_SCHEMA_PREPARE=true and EDGE_IDENTITY_AUTH_ENABLED=true.
EDGE_PERMANENT_TENANTS_ONLY=false, allowing the original legacy
token-based login to coexist. EDGE_PERMANENT_READONLY_PILOT_ENABLED,
tenant Public vault/read, tenant account reads/monitor/watchlist,
signup, invites, passkeys and signed Android passkey origin all remain
false; EDGE_AUTOMATION_WORKER_ENABLED=false and ENABLE_LIVE_ORDERS=false.
The existing paid Render service deployment dep-dbqhl6ajnfac738nlst0
of v0.2.71 main commit 9381b3f was verified LIVE. No new paid
resources or additional database were created.

IMPORTANT: Do NOT claim an end-to-end user login was verified yet.
The first login on a physical Android browser and subsequent session/
logout must be tested by the owner using Belenos-Owner and their
private Argon2id password, without revealing password to ChatGPT.
Assistant-side public web probing failed to access the URL, but Render
reported LIVE. The private owner archive was restored/verified and
copied off-Render with checked SHA-256, then visibly uploaded to Drive;
Google Drive byte-for-byte redownload verification is still pending.
See CONTROLLED_OWNER_HTTPS_LOGIN_V0271.md.

After owner confirms new HTTPS session and logout, independently confirm
original legacy login still works; if failure or unexpected access,
rollback ONLY EDGE_IDENTITY_AUTH_ENABLED=false on the existing service,
without replacing secret environment values or deleting databases.
Do not enable Public account routes, tenant-only cutover, bank transfer,
autonomous orders, signup, passkeys or restart Observe/Paper worker
without further explicit approval and acceptance evidence.

## CURRENT checkpoint — v0.2.71, November 11, 2026

The owner completed v0.2.70 production tenant backup from the existing
paid Render service with reports backup_verified=true,
isolated_restore_verified=true, first_owner_count=1,
archive_private_0600=true. The encrypted
edgepilot-tenant-owner-20261112.epbk (UTC server date) was transferred
to local Termux by protected SSH, with exact SHA-256 comparison, saved
as a private 0600 local archive, and then uploaded to the existing
private Google Drive Edgepilot backup folder. User screenshot visibly
showed the uploaded archive and upload completion. A separate Drive
redownload comparison has not yet been done.

Owner login Belenos-Owner is enrolled with Argon2id hash in
/data/edgepilot-tenants.db; the original owner token and Public
credentials remain in the original /data/edgepilot.db. Observe/Paper
worker remains paused with user approval. No independent HTTPS login,
second Android device, Public account owner verification, tenant-only
cutover, order execution or funds transfer has been activated.

v0.2.71 introduces a separately gated read-only trusted-terminal
Argon2id proof to establish that the operator remembers the new
owner password, without changing DB, creating sessions, or enabling
any public identity API. Its return explicitly reports that real
HTTPS owner login remains unverified. After GitHub PR/main CI and
existing Render deployment pass, request a one-time operator
execution. Do not activate tenant identity public routes until
that result is verified and a separate reversible login rollout
is reviewed with the operator. No new paid resources.

## CURRENT checkpoint — v0.2.70, November 11, 2026

The owner successfully completed first-owner bootstrap using the
v0.2.69 visible final approval prompt. Render printed the expected
success response, and a follow-up v0.2.65 read-only readiness
inspection confirmed inspection=passed, tenant_member_count=1,
tenant_owner_initialized=true, tenant_owner_has_password_identity=true
and next_operator_stage=manual_owner_identity_login_test.
The new private tenant identity login is Belenos-Owner and its
password was never displayed or collected in chat. Original Public
credentials and token-based login are unmigrated and intact.

v0.2.70 adds a dedicated, default-off, single-first-owner tenant
database backup because the legacy .epbk helper requires the old
settings schema and the synthetic-only tenant helper cannot touch
Render /data. This code uses a phone-held 32-byte backup key piped
over SSH, encrypts a RAM-only consistent SQLite snapshot with
AES-256-GCM, verifies an isolated private restore and publishes
a distinct non-overwriting temporary /dev/shm archive. It has NOT
yet been run on real production storage. The next operator action
after verified CI/Render deployment is to exit remote shell,
run the private backup from LOCAL Termux, compare the remote
archive SHA-256 with the downloaded local encrypted file, then
upload the archive to private Drive. The backup passphrase/key
must remain separately recoverable.

The Observe/Paper worker remains disabled as approved. No tenant
login routes, tenant-only policy, Public pilot, live orders,
bank transfers, credentials migration, second physical device
or extra paid service are activated. Preserve existing legacy
database and its validated encrypted offsite backups.

## CURRENT checkpoint — v0.2.69, November 11, 2026

The user, on an existing authorized interactive SSH terminal attached to
the *same* paid Render Starter service, successfully created
/data/edgepilot-tenants.db via the guarded v0.2.63 initializer after
manually typing the visible 34-character approval phrase. The tool
returned prepared=true, private_tenant_database=true,
initial_tenant_members=0, separate_from_legacy=true and
authorized_to_activate=false. The v0.2.62 read-only database cutover
preflight then returned inspection=passed, legacy_schema_intact=true,
separate_database_files=true and tenant_identity_schema_intact=true.
The v0.2.65 first-owner readiness audit also returned inspection=passed,
tenant_member_count=0 and next_operator_stage=manual_first_owner_bootstrap.

The initial manual owner bootstrap then requested Belenos-Owner as both
display label and login identifier, prompted twice for hidden password,
and immediately printed the generic "Owner identity was not created"
failure after a HIDDEN approval prompt. Do not infer an owner account
exists. The engine accepts Belenos-Owner; the failure could be empty
hidden input or another gate. v0.2.69 improves ONLY the operator
console interface: visible **nonsecret** approval input, specific
nonsecret denial reasons, and blank/mismatched/short-password checks
before attempting any write. Still require a fresh READ-ONLY readiness
check to verify zero members before operator retry; do not assume the
earlier attempt committed or not without verifying.

The older owner database, original token-based login, saved Public
credentials and separate GPG recovery/backups remain untouched. The
Observe/Paper background worker was disabled on Render with user
approval; live execution and transfers are disabled. Do not enable
tenant-only mode, identity routes, Public pilot features or order
submission merely because bootstrap source code deployed. Next operator
actions: verify merged-main GitHub CI and paid Render deploy for
v0.2.69, run read-only owner readiness, then (if zero) manual first
owner bootstrap, followed by repeat read-only readiness and a later
separately gated real login/recovery test. No added paid services.

## CURRENT checkpoint — v0.2.68, November 11, 2026

v0.2.67 deployed with passed PR and merged-main tests on existing
paid Render service. The owner explicitly approved a temporary pause
to the Observe/Paper worker; EDGE_AUTOMATION_WORKER_ENABLED was changed
to false through the Render connector and a live Render deployment was
confirmed. The owner verified /data/edgepilot.db permissions corrected
from 0644 to 0600 and the worker setting false via trusted SSH. The
separate /data/edgepilot-tenants.db was still absent.

The protected v0.2.63 tenant initializer was attempted twice after
the worker/permissions fix, with the exact approval phrase, but
returned its undifferentiated generic denial. A careful operator
read-only diagnostic found NO blocking runtime flags, valid private
owner DB and SQLite integrity, successful isolated schema and identity
creation on the same paid disk, valid temporary 0600 permissions,
successful fsync and hardlink; no production tenant file was created.
v0.2.68 adds fixed, nonsecret phase identifiers to THIS manual
initializer only, and tests error sanitization. It does not relax
the checks, perform initialization or change live flags.

NEXT: verify PR/main CI and Render deployment for v0.2.68, then
request the operator to execute the original protected interactive
initializer once, recording only the fixed safe stage result. Do not
enable identity, Public reads, live orders, bank transfers or a
second paid service. If the initializer succeeds, run the v0.2.62
read-only cutover preflight then v0.2.65 owner readiness before
any manual independent-owner bootstrap.

## CURRENT checkpoint — v0.2.67, November 11, 2026

v0.2.66 PR #87 passed PR CI and merged, adding a startup guard that
blocks retiring the old owner API unless a valid independently enrolled
tenant owner is present on the paid disk. v0.2.67 follows with a
default-off production account-scoped **read-only pilot permission**,
removing the previous mutually exclusive preparation flag that would
always reject tenant vault and Public read-only features on the paid
backend. The new pilot flag alone enables no tenant API. Per-feature
gates remain independent; without prepared private tenant file,
owner bootstrap, identity sessions, stable Fernet key and disabled
workers/orders, enabling the pilot is rejected.

Actual /data/edgepilot-tenants.db creation and independent first
owner bootstrap have NOT been confirmed by the operator. The legacy
database backup, owner GPG recovery and Fernet-key GPG recovery were
encrypted, verified and backed up off-phone. The existing Render
Public credential decrypts with the running key. These are distinct
from actual two-user acceptance, app/passkey validation and provider
authorization. Continue to keep production pilot, tenant-only and
tenant Public features inactive until operator-led recovery checks,
owner login and a reversible staged acceptance plan. No new cost,
live orders, automated trading or fund transfer.

## CURRENT checkpoint — v0.2.66, November 11, 2026

v0.2.65 PR #86 implemented the dormant read-only owner readiness
inspection, passed PR and merged-main CI, and deployed on paid
Render. The actual v0.2.63 protected storage initialization still
requires trusted operator input and has not been confirmed.
v0.2.66 makes the separately gated tenant-only route retirement
fail closed if no prepared private tenant DB and independently
enrolled active owner Argon2id identity exist. This is source-only
protection; normal v0.2.64/v0.2.65 owner routes remain unchanged
until environment flags are independently activated.

The operator's legacy database backup, new owner access token GPG
file, and Fernet key GPG file were verified and uploaded off-phone.
Render can decrypt the existing Public ciphertext. Neither this
nor owner existence proves login recovery or two-device test.
Next operator tasks: create tenant file, read-only schema check,
readiness audit, manual first-owner bootstrap, and actual login.
Do not enable tenant-only, live Public tenant APIs, workers/orders
or bank transfers solely due to GitHub CI. No new paid service.

## CURRENT checkpoint — v0.2.65, November 11, 2026

v0.2.64 merged with passing GitHub tests and verified live Render
deployment. The operator previously verified the original Render
owner Public credential decrypts successfully; separately encrypted,
verified, and uploaded the Fernet EDGE_CREDENTIAL_KEY recovery file to
their private Drive folder. A separate v0.2.63 protected one-time
initializer is available for the isolated paid-disk tenant DB, which
the operator last reported as NOT CREATED. No subsequent proof that
the tenant file was actually initialized has been provided.

v0.2.65 adds an opt-in read-only inspection for this exact gap:
validate separate paid-disk DB schemas, one valid owner identity or
an empty first-owner staging state, and member/identity completeness.
It will not modify storage or authenticate real users, and its output
does not approve live cutover. The tool is dormant until called
manually from trusted Render console after actual tenant DB
preparation.

After exact PR/main CI and paid Render deployment verification,
request only the missing operator evidence: actual v0.2.63 tenant
file initialization, v0.2.62 read-only cutover preflight, v0.2.65
owner readiness report, independent owner bootstrap/login and then
2 separate Android devices and Public accounts. Preserve legacy
owner login/DB and all encrypted backups; keep public tenant
activation, auto trading, orders and bank transfers disabled.

## CURRENT checkpoint — v0.2.64, November 11, 2026

v0.2.63 PR #84 passed CI, merged, and added a dormant console-only
empty tenant DB initializer for the existing paid /data disk. No
production initialization has been witnessed. v0.2.64 adds a
separate, default-off owner Fernet credential-key recovery audit:
an independently entered EDGE_CREDENTIAL_KEY can be checked against
the running service and saved owner Public ciphertext without
printing secrets or altering any database. This feature has not
actually been executed in production; evidence of an independently
held recovery key is still required.

The owner verified the November 11 encrypted database backup and
isolated restore, uploaded it to a private Drive backup folder,
and separately verified and uploaded a new encrypted owner-token
GPG file. These are not substitutes for a separately recoverable
EDGE_CREDENTIAL_KEY. Continue only after exact PR/main GitHub CI,
Render deployment, and independent operator checks. Do not infer
first-owner identity, tenant disk activation, second phone/Public
account, live orders or bank transfers from a source code merge.
No new paid infrastructure.

## CURRENT checkpoint — v0.2.63, November 11, 2026

GitHub v0.2.62 (read-only independent paid-disk cutover preflight) was
merged and passed exact-main CI and paid Render deployment. The owner
subsequently verified the Nov 11 encrypted legacy database backup with
an isolated restore on the paid service, copied it to the phone and
uploaded it to the private Google Drive backup folder. A newly encrypted
owner access-token GPG recovery file was independently decrypted,
byte-compared against the existing owner token, and uploaded to Drive.
The older failed-passphrase GPG artifact was preserved. These steps do
NOT prove stable Render EDGE_CREDENTIAL_KEY recovery, any on-disk
tenant DB activation, or the real two-device acceptance test.

v0.2.63 adds a **dormant, manual** first-time tenant file initializer.
On the existing paid /data disk it can create an empty private
edgepilot-tenants.db only after an independently verified backup,
operator console and a one-use approval; refuses an existing tenant file,
writes no owner DB rows, and publishes no live identity or Public APIs.
The code is NOT invoked by Render deployment or the Flask service.
See PRIVATE_TENANT_STORAGE_INIT_V0263.md. Verify exact PR/main CI and
paid deployment before calling v0.2.63 merged.

Next operator milestone: independently secure and verify credential
encryption key recovery; then, with explicit trusted console inputs,
run the new empty storage initializer (only if target absent) and the
v0.2.62 read-only database preflight. Independently bootstrap the first
owner (v0.2.60), verify real identity login and staged account isolation,
and ONLY THEN consider flags for eventual tenant-only routing.
Orders, transfers and live automation remain disabled. No new paid
services. Do not claim production initialization or migrations occurred.

## CURRENT checkpoint — v0.2.62, November 11, 2026

v0.2.61 (private owner invitations, at most 10 members) was developed as
PR #81 with passing PR tests and merged before this follow-on. v0.2.62
adds an explicitly opt-in, console-only, read-only production cutover
inspection for the existing paid Render Starter instance and attached
/data disk. It inspects the isolated owner and tenant databases, checks
paths/permissions/schema integrity and reports only nonsecret flags.
No database data, credentials, live trading or transfers are touched.
PR/main GitHub tests and Render deploy require independent verification.
See PERMANENT_CUTOVER_PREFLIGHT_V0262.md.

This is NOT a completed cutover. A fresh independently verified encrypted
off-service backup, tested restore and stable credential encryption key
must be confirmed before modifying the paid service environment, creating
the first real owner identity or retiring legacy owner APIs. Do not turn on
tenant Public access, passkey or order flags solely because this source
and synthetic tests pass. Separate physical-device and Public-account
acceptance remains required. No additional paid services.

## CURRENT checkpoint — v0.2.61, November 11, 2026

v0.2.58: paid existing Render service reuse and private separate tenant DB
code merged, tests green, deployed live while feature flags stayed off.
v0.2.59: future tenant-only legacy API denial and signed production
passkey-origin policy merged; gated and unchanged in live config.
v0.2.60: one-time offline first-owner role/bootstrap CLI merged after
green PR tests; no real operator bootstrap has executed.

v0.2.61 adds a separate **disabled** first-owner invitation issuance
API for a bounded private ten-user pilot. It does not trust Public or
legacy token for roles. Issuance is tied to owner-only identity and CSRF
inside SQLite BEGIN IMMEDIATE; private registration refuses a race above
ten users. Nine per 24-hour invite issuance and append-only audit. All
brokers, workers, orders and transfers remain inactive by default.
See PERMANENT_PRIVATE_INVITATIONS_V0261.md.

The NEXT real-world required milestone remains verified current
encrypted off-service legacy backup and restore rehearsal; initial
owner enrollment from a trusted Render console; deliberate shared
database flags, independent passwordless login and two-device
isolation, then provider-approved read-only brokerage checks.
No additional paid hosting/storage. Do not claim code CI alone
proves any real user or broker account migrated.

## CURRENT checkpoint — v0.2.60, November 11, 2026

v0.2.58 PR #78 merged and verified on paid Render and GitHub. v0.2.59
PR #79 merged after green PR tests; it adds **inactive** legacy API
retirement and signed-app WebAuthn-origin options for the permanent
isolated user model. The paid existing Render deployment rolled
forward, but no multiuser environment activation has taken place.

v0.2.60 supplies a **console-only, off-by-default, one-time initial
owner identity creation** for the separate paid tenant SQLite DB, with
Argon2id hashed password, atomic audit, zero existing-user requirement
and no legacy data copy. No Flask/HTTP route or alternate token was
added. All tests are synthetic. The first real account provision
remains blocked on an independently verified fresh encrypted and
restorable owner backup, an operator-trusted service terminal, and
proper split DB setup on existing paid /data. See
FIRST_PERMANENT_OWNER_BOOTSTRAP_V0260.md.

Maintain strict operational distinction: GitHub CI/Render green
does NOT prove data migration, backup, actual second physical phone,
real two-owner Public account read access or permanent identity
activation. Keep live orders, autonomous brokerage, bank transfers,
paid service creation and tenant Public features disabled. Never
reuse owner API secrets for tenant identity or print any secrets.
Proceed from last verified commit and preserve logs of tests and
deployment. Next production gate requires operator evidence, not an
assumption or automatic destructive cutover.

## CURRENT checkpoint — v0.2.59 (follows verified v0.2.58), November 11, 2026

v0.2.58 merged via PR #78 with passing PR and post-merge GitHub tests;
the same commit auto-deployed **live** on the existing paid Render Starter
service. The separate `edgepilot-tenants.db` remains configuration-gated;
default Render environment must not be described as an activated migration.
Neither legacy owner data nor keys were moved.

v0.2.59 is a distinct new development milestone. It adds a default-off
`EDGE_PERMANENT_TENANTS_ONLY` routing option that can retire legacy
owner HTTP APIs after safe migration and recovery, without allowing
identity cookies to become owner cookies. The optional production
signed-app WebAuthn origin is independently gated to the pinned real
production Android certificate, exact owned RP, tenant-only identity
and separate DB. There are new negative tests and a standalone runbook.
Default production behavior, owner APK, credentials and paid resources
are unchanged. Verify exact PR and merged-main CI before any merge.

The next operational gate remains a fresh encrypted backup/restore
checkpoint, owner identity recovery and controlled shared-disk split
preparation. Do not enable tenant-only mode until the owner can sign
into the migrated identity; do not accept legacy tokens as tenant IDs,
enable any live order/transfer, claim a second physical device, or buy
additional hosting.

## CURRENT checkpoint — v0.2.58, November 11, 2026

**New explicit architecture approval:** Use the existing paid Starter Render
service `edgepilot-private-h9tl` (service ID `srv-dbocnb3m8hqs7386trvg`)
and existing /data persistent disk as the future permanent single-instance,
multi-user backend. Do **not** upgrade the Free staging service or purchase
additional paid database/storage/hosting. The v0.2.57 additional-cost staging
plan was superseded. Keep staging disposable.

The initial `feature/v0.2.58-shared-paid-tenant-db-isolation` branch contained
only a 61-line unwired database-path selector; review identified it was not
safe to merge as finished. v0.2.58 has now added guarded shared-disk tenant
file selection, private-file creation and permissions checks, explicit
integration into every tenant Flask store, and local cross-database tests.
`/data/edgepilot.db` remains the owner file, `/data/edgepilot-tenants.db`
is the independent tenant DB. Tenant login, real Public access, migration,
live orders and transfers must remain disabled in production until separate
authorization, recovery and isolation testing.

**Release discipline:** Verify the exact branch PR CI, merge only on green,
inspect merged-main CI and paid-service Render status, and only then
proceed with recovery/activation. `main` auto-deploys to the paid service:
a source merge must not silently switch environment settings. Never print
stored tokens, passphrases, key bytes, provider secrets or encrypted rows.
Do not claim permanent two-user acceptance from the one-phone staging
passkey test. See SHARED_PAID_BACKEND_CUTOVER_V0258.md.

# EdgePilot — Development continuity checkpoint

This file is the canonical handoff for a new ChatGPT conversation when a
long development chat becomes read-only, slow, or difficult to navigate.
It complements README.md (product overview), CHANGELOG.md (release record),
VERSION (latest backend milestone), MULTIUSER_PLATFORM_ACCEPTANCE.md
(success criteria), and TENANCY_MIGRATION_PLAN.md (technical blockers).

## Approved product objective

Build **one shared, future-ready EdgePilot backend and Android application**.
Users create their own EdgePilot login, use secure passkeys/Android biometric
credential verification, and connect their own independently encrypted Public
API key. Their brokerage accounts, settings, watchlists, portfolios, history,
worker tasks, strategies, caches, sessions and backups must be isolated. The
project is currently private/noncommercial; broad commercial distribution is
not a present requirement, but should not necessitate redesign later.

The user defined the current phase as complete **only when two different
Android devices with independent users and independently owned Public
accounts actually work and isolation is verified end-to-end**. Mock/CI tests
alone do not satisfy this acceptance criterion.

## Standing authorization boundaries

- Continue routine development, corrections, pull requests, CI, merges and
  normal Render deployments without asking for each step.
- Discussion of a *new* capability is not automatically authorization to
  implement that capability. Seek confirmation for major out-of-scope work.
- Build and test the multi-user Public architecture under the engineering
  assumption that multi-user API access will be permitted. Do NOT claim
  legal approval has been verified or silently activate unrelated real
  users' credentials until separately verified as appropriate.
- Real brokerage order submission, live autonomous trading, bank deposits
  and transfers remain disabled until separately authorized.
- Never expose credentials in repository files, logs, ChatGPT messages,
  APK artifacts or screenshots. Never copy the legacy owner credential
  into another user's tenant record.
- Tenant identity endpoints and passkeys/vault/readonly are independently
  gated by environment variables and default off. No blanket enabling of
  production feature flags before readiness review and a safe migration.
- Existing personal owner app, Render backend and encrypted backups must
  remain compatible through staged migration.

## Implemented code areas and still-incomplete items

The repository includes account identity sessions, independently gated current-password
changes that revoke the member's device sessions, one-use invitation signup,
official Public signup and API-key instructions from the /account screen,
a user-owned encrypted Public credential vault, gated Public read-only
account discovery/linking and portfolio retrieval, WebAuthn passkey server
verification, a mobile-ready separate /account interface, an Android WebView
Web Authentication capability check, a fail-closed Digital Asset Links
endpoint, and synthetic monitor/worker fencing and emergency-stop tests.

The Android debug wrapper can open two exact Public-owned signup/key-help
URLs only on a deliberate user click, outside the EdgePilot authenticated
WebView. Android build 0.19.17 compiles this code but external navigation and
device passkeys still require physical-device verification.

The legacy owner app and Observe/Paper worker still use global single-owner
state, and cannot be called by tenant sessions. Account-specific monitoring
is being added in small, independently gated read-only increments, not by
silently enabling the existing global worker.

Major outstanding work includes stable Android release signing, verified
Digital Asset Links, physical biometric WebAuthn enrollment/sign-in on two
devices, forgotten-password recovery and proof of ownership, controlled
tenant activation and data migration,
strict per-account worker/strategy/history isolation, durable encrypted
backup/restore verification, incident monitoring and real two-account
read-only validation. No real orders/transfers are part of current acceptance.

## How to resume safely in a NEW chat

1. Read this file and the repository's current VERSION, README.md,
   CHANGELOG.md, MULTIUSER_PLATFORM_ACCEPTANCE.md and recent runbooks.
2. Inspect GitHub open pull requests, main's head commit and the **latest
   passing** tests for that exact head; do not rely on an older chat's
   claim that a version is complete.
3. Continue from the highest verified merged milestone. If a PR is open,
   review its current diff and CI first, fix failures, then merge safely.
4. Use a focused GitHub feature branch for each new development milestone,
   with tests, documentation and a changelog entry. Verify PR CI and
   post-merge CI. Check Android APK CI whenever Android files change.
5. Explain major completed steps in concise progress updates and provide
   the PR URL and test status. Never claim an APK, Render runtime or device
   behavior was verified without inspecting that exact evidence.
6. A ChatGPT conversation branch/new chat is a UI action by the user, not a
   GitHub branch. This file preserves continuity independently of that UI.

**Suggested first message in a new conversation:**
"Continue EdgePilot from the GitHub repository
BelenosCreations/edgepilot-personal. Read DEVELOPMENT_CONTINUITY.md, VERSION,
CHANGELOG.md, MULTIUSER_PLATFORM_ACCEPTANCE.md and the latest merged PR and
open branches. Continue approved multi-user development with periodic
updates, preserving all brokerage/trading safety restrictions."

## Current milestone checkpoint (v0.2.35)

Public key rotation and disconnection are now controlled from a member's own
/account interface. Credentials stay encrypted on the server; previously
verified account bindings are disabled and must be verified again after
rotation or disconnect. Revocation/rotation revalidates session and CSRF
within the same database transaction, preventing stale authorization after
logout. The feature remains default-off with the existing identity/vault
gate. Refer to TENANT_PUBLIC_CONNECTION_MANAGEMENT_RUNBOOK.md for acceptance
and limitations. Physical two-device biometric login and actual two-account
Public validation remain uncompleted. Always verify current GitHub VERSION,
PR status and exact-head CI before announcing release completion.


## v0.2.35.1 maintenance checkpoint

v0.2.35 merged with passing PR CI, but post-merge CI exposed an intermittent
STATE_UNAVAILABLE denial in the disconnected multi-process SQLite rehearsal.
The patch retains exactly two durable admissions and checks fail-closed
denial types. Verify v0.2.35.1 PR and post-merge CI before continuing.
No production broker or Android behavior changed.

## v0.2.37 session-management checkpoint

Verified tenant identity sessions can now be listed by the logged-in member
and other sessions can be revoked through a separately default-off,
CSRF-protected identity API. The account page displays timestamps only;
no physical-device fingerprints, IPs or biometric data are collected.
Changes are serialized with identity revocation and a secret-free immutable
audit records other-session logouts. The main app/worker, Public account
authorization, real trading and transfers are unchanged. See
TENANT_SESSION_CONTROLS_RUNBOOK.md. The two-physical-phone acceptance target
remains open.


## v0.2.38 — Stable Android signing preparation

A standalone manual-only GitHub Actions workflow now builds a private signed
Android test APK using a trusted operator-owned keystore and an independently
pinned certificate SHA-256. It cannot run automatically or on a PR, and
rejects missing or mismatched secrets/certificates. The normal debug APK
workflow is untouched. The project does NOT yet have a provisioned stable
signer, verified signed build, Android Digital Asset Links association, or
physical two-device biometric acceptance.

Next: complete isolated signing-key provisioning and website association
using an authorized owner action, then verify Credential Manager on real
devices; do not flip tenant or Public/trading flags automatically. Continue
account-specific worker/backup isolation development without broad activation.
Review ANDROID_PRIVATE_SIGNING_RUNBOOK.md and latest CI before acting.


## v0.2.39 — Test-only encrypted tenant backup/restore validation

A synthetic two-member fixture can now be snapshotted into an authenticated
Fernet archive and restored to a new private SQLite database only on verified
/dev/shm tmpfs. Archived identity sessions, pending WebAuthn challenges,
unredeemed invitations and worker leases are invalidated on restore;
all stored provider connections/accounts and passkey credentials are
quarantined pending explicit fresh verification/re-enrollment, preventing
resurrection of formerly revoked broker keys or authenticators;
cross-member account and encrypted credential isolation must remain intact.
Production Render DB paths and non-tmpfs destinations are explicitly rejected.
This is NOT production offsite backup or key-management readiness. No live
brokerage request, transfer or trading was enabled. Review
TENANT_BACKUP_REHEARSAL_RUNBOOK.md and latest CI for the exact commit.


## v0.2.40 — Shared-backend two-user HTTP acceptance rehearsal

Synthetic end-to-end tests now simulate Alice and Bob on independent Flask
cookie jars against the SAME backend with separately gated identity,
invitation signup, WebAuthn option preparation, encrypted fake Public keys,
read-only fake broker accounts/portfolios, per-account watchlists and
inactive monitoring previews, and selective other-device session logout.
No real HTTP brokerage requests, Android biometric assertions, live workers,
orders or transfers occur. Passing tests are NOT proof of two real phones,
real provider permission, authenticated production Public accounts or
production-grade recovery. See TWO_DEVICE_SYNTHETIC_ACCEPTANCE_RUNBOOK.md
before declaring this stage complete.


## November 10, 2026 — First owner-controlled stable signed APK verified

The operator created a 4096-bit RSA JKS signing identity in private Termux
storage, verified the signing certificate, GPG AES-256-encrypted a backup,
successfully checked decryption against the original, and stored the sealed
backup in their own Google Drive. Five required GitHub Actions signing
secrets were configured privately, and the signing password was verified
against the unchanged keystore before both password secrets were updated.

Manual signing workflow #42888113943 ran on main at
45ecaf82d0f1c3d648c2e6ab0a17d18817823e73. Attempt 1 failed the
certificate-pin check and produced NO artifact. The expected public
certificate fingerprint was recalculated from the actual JKS and corrected.
Attempt 2 PASSED compile, apksigner signature + fingerprint checks and
private artifact upload. Artifact:
EdgePilot-v0.19.17-private-stable-signed-test
(expires 2026-11-17; no binary in the source repository).

This satisfies the signed-artifact CI precondition but NOT Android
installation, authenticated Digital Asset Links, passkey/biometric
enrollment or sign-in, verified two-physical-device tenant isolation,
provider-permitted real accounts, production database recovery or active
tenant monitor workers. The existing debug-signed APK may not update in
place to the stable signature; DO NOT advise uninstalling without
checking local session/recovery state. Continue from the real-device
signer/Digital Asset Links verification stage. No production trading
or transfers have been enabled.

See ANDROID_PRIVATE_SIGNING_RUNBOOK.md and APK_TESTING.md for the exact
GitHub run and safe installation limitations.

## November 10, 2026 — Owner-reported physical Android installation and legacy login

The owner installed the previously verified permanent-certificate Android
v0.19.17 test APK on their *existing* phone after locating the legacy
EDGE_APP_TOKEN on Render and confirming that the original token still
worked in Chrome separately. The user subsequently reported a successful
login in the installed app. No token, passphrase, backup ciphertext or
other credential should appear in README, CHANGELOG or GitHub issues.
No key rotation was required.

Important: do not conflate this one-phone **owner-reported legacy dashboard**
smoke test with proof of app-to-website Digital Asset Links, Android
Credential Manager passkey registration/authentication, or the approved
two-distinct-devices/two-independent-EdgePilot-users target. The default-off
identity/passkey/Public-tenant feature gates remain unchanged. The next
technical work is website association validation and safe isolated-test
passkey verification; real orders, transfers and production multiuser
cutover remain disabled.

## November 10, 2026 — Android Digital Asset Links Render configuration staged

The owner opened the website's /.well-known/assetlinks.json on their
current phone and captured a JSON 404 from EdgePilot. This was the
expected fail-closed response while EDGE_ANDROID_CERT_SHA256 was absent
or invalid. A copy of the independently CI-verified signed APK
(GitHub run #42888113943, attempt 2) was read and its Android v2/v3
signature blocks independently parsed; both contain the same X.509
certificate and SHA-256 fingerprint. The public certificate fingerprint,
not a signing secret, was merged into the existing Render service's
EDGE_ANDROID_CERT_SHA256 variable. Render deployment
`dep-dbppig56e07s73b34d1g` was verified status=live.

This is the server configuration milestone only. At this checkpoint a
subsequent external fetch of the public HTTPS JSON response had NOT
been independently confirmed. The owner should reopen the same URL
and confirm it now returns a JSON array containing the correct Android
package and certificate. An installed app's Android Credential Manager
association and tenant biometric authentication remain completely
unverified. Do not turn on dormant multiuser/tenant/passkey/Public flags
or enable orders or transfers as an implied consequence of this deploy.

## November 10, 2026 — Public Digital Asset Links JSON confirmed on Android

After Render deployment `dep-dbppig56e07s73b34d1g` was live, the owner
reloaded https://edgepilot.belenoscreations.biz/.well-known/assetlinks.json
on their current Android phone. The supplied screenshot displayed a
JSON array containing relation
`delegate_permission/common.get_login_creds`, target namespace
`android_app`, package `com.edgepilot.mobile`, and the configured
SHA-256 certificate fingerprint matching the verified permanent-signed APK.
This resolves the prior 404 and validates **public HTTPS association
response content** from the owner's phone. It is not OS-level Digital
Asset Links verification and does not demonstrate credential sharing,
Android Credential Manager availability, or a functioning passkey.

Next: determine a controlled isolated test deployment and user enrollment
method before turning on currently default-off identity, signup, or
passkey flags. Do not activate those on the personal live service simply
because the public association file is available. Test account recovery,
passkey registration and login on an actual Android device, then use a
second independent user/device. Live orders/transfers stay disabled.

## v0.2.41 — Fully offline, real-crypto two-user WebAuthn verification

A new test-only software-authenticator harness generates actual ES256
P-256 signing keys and CBOR WebAuthn attestation/assertion data and exercises
the production py_webauthn verification routines behind the Flask tenant
identity routes without mocks. Two separate synthetic users enroll and log
in on separate in-process browser cookie jars. The test verifies exact RP
origin, signed challenges, required UV, distinct identity-only sessions,
no legacy account inheritance, and fail-closed behavior for wrong origin,
missing UV, forged signatures, foreign handles, reused challenges, counter
rollback and credential revocation. External requests are denied during
the fixture; no Public credential, real account, trade or transfer is used.

This validates actual *cryptographic protocol processing*, not Android
Credential Manager, OS-level Digital Asset Links, physical biometrics,
real website session operation or two independent physical phones.
The existing owner APK and Render feature flags remain unchanged; do not
misrepresent synthetic credentials as a real user's passkey. Follow
WEBAUTHN_REAL_CRYPTO_ACCEPTANCE_RUNBOOK.md for scope and next steps.

## v0.2.42 — Separate Android staging package and guarded website association

After the owner reported a successful login in the permanently signed
production-host Android app, development added a distinct Android staging
build type with package com.edgepilot.mobile.staging and app label
EdgePilot Staging. Production app ID, stable-signed workflow, HTTPS host,
installed app and login credentials remain unchanged. Staging host is a
compile-time, owner-controlled distinct belenoscreations.biz subdomain;
missing configuration compiles only a nonfunctional .invalid host.
A new manual-only workflow can sign the staging package with the same
operator-owned certificate after a separate staging HTTPS service exists.
PR Android CI compiles the unsigned staging build without exposing a
signed staging artifact. A process-startup staging guard refuses unsafe configuration **before**
opening the database or initializing legacy owner credentials, while the
optional backend staging association responds only when explicitly
isolated with exact RP/host and all live credentials, workers, orders
and provider paths absent.

No separate paid Render service or DNS has been provisioned in this
milestone; neither staging signed build, physical Android biometrics nor
two-user/two-device acceptance has been validated. Do not overwrite the
owner's existing APK. Review ANDROID_ISOLATED_STAGING_RUNBOOK.md and
request operator input for new hosting/domain provisioning and costs
before actual staging rollout. Never enable real brokerage trading or
transfers as part of this test.

## v0.2.43 — Approved research strategy and no-cost data boundary

Read AI_ANALYSIS_COST_STRATEGY.md (approved 2026-11-10). It extends
rather than supersedes the two-device, two-independent-Public-account
acceptance objective. The standalone research_intelligence.py module
requires verified coverage, source rights, UTC timestamps, fresh books
and explicit fees/depth/settlement for prediction event research.
No market provider, background polling, brokerage account, user identity
or LLM call is made by the new pure-Python functions. A user who elects
$0 in AI fees must retain a useful non-AI intelligence product when
permitted data exists. No free market-data license is assumed.

Next: precise model-aware AI budget accounting and reservation
reconciliation, default-off tenant BYOK and per-user caps, followed by
consent/licensing-conscious shared signals and deferred commercial
entitlements. Do NOT enable trades, transfers, public distribution or
actual billing. Physical Android passkeys and independent Public accounts
still need real-device acceptance. See FREE_FIRST_RESEARCH_RUNBOOK.md.

## v0.2.44 — Owner AI pricing and local budget accounting

Legacy ai_analysis.py now uses public Standard short-context text
price snapshots (checked 2026-11-10) for the allowlisted
gpt-6-luna and gpt-6-sol models, conservative byte-bound input
cost and 500-token output ceiling, microUSD integer ledger
with SQLite BEGIN IMMEDIATE reservations. Successful replies need
provider input/output token counts to finalize usage-cost estimates;
unknown charges/timeouts/HTTP errors retain their reservation.
Historic $0.20 rows are preserved, including original budget
consumption. This adds no automated AI calls. The current optional
owner AI setting remains disabled by default; the $2 default budget
is unchanged; the local limit is not guaranteed third-party billing.
Pricing expires review 2026-12-10 and fails closed on expired rates.

Read AI_COST_ACCOUNTING_RUNBOOK.md before any model/cost work.
Next: independently owner-funded vs per-user BYOK/allowance encrypted
credentials and tenant budgets; never silently use the owner's
OpenAI credential for other EdgePilot members. Two physical devices,
independent Public accounts and Android passkeys remain open.

## v0.2.45 — Dormant member-owned AI funding/vault groundwork

The owner-approved up-to-ten-friends AI strategy now includes a fully
offline encrypted per-member BYOK preference/budget module. All authority
derives from independent server-side tenant session and CSRF,
revalidated inside the SQLite BEGIN IMMEDIATE transaction. Each member's
mode, analysis depth, own provider key and monthly microUSD cap are
separate. The module does not import or fall back to legacy owner
OPENAI_API_KEY or EDGE_APP_TOKEN. It stores encrypted owner-bound provider
key material under a separate AI encryption key, returns only a configured
boolean, and enforces a fail-closed per-member cost reserve for simulated
requests; no payment, OpenAI HTTP call or schedule is activated.
Managed-credit mode is deliberately refused. Ten-member concurrency
and owner isolation tests reside in test_tenant_ai_byok_v0245.py.

No Flask routes or production flags have been added to expose this store
to real users. Future secure key management, rotation and recovery,
ten-user load, provider billing opt-in, real hardware passkeys and
real independent Public accounts remain outstanding.
See TENANT_AI_BYOK_BUDGET_RUNBOOK.md.


## v0.2.46 — Licensed shared, account-neutral research sample cache

A separate dormant module now validates strictly public provider-neutral
observations, requires affirmative verified analysis/cache/redistribution
rights, rejects personal keys/holdings/account identifiers, records only a
short-lived spread feature, and fences all stock/ETF watchlist previews by
independent identity, CSRF, account linkage and watchlist owner in one
SQLite transaction. Ten independent synthetic users reuse one feature with
zero AI/provider calls. Crypto/prediction account entitlement is NOT
implied, and no provider terms have been accepted by this code.
No real shared market data, external provider requests, HTTP UI, worker,
orders, bank transfers or production gates activated. Follow
SHARED_RESEARCH_CACHE_RUNBOOK.md and the main AI_ANALYSIS_COST_STRATEGY.md.
Before continuing verify PR/CI and resume from highest verified main commit.
The two-physical-device/two-independent-Public-account acceptance goal
and physical biometric checks remain open.


## v0.2.47 — Offline, provider-quota-aware sampling proposal

Another independent, dormant research module proposes source-aware
market sampling under explicit, recently verified quotas, coverage and
license/redistribution permissions. It never schedules or makes a real
request. Ten synthetic members can share one *proposed* licensed central
data call or receive separate individually authorized, fair,
per-member-quota-limited proposals. Stale data, closed/unknown sessions,
prediction-expiry uncertainty, current backoffs and missing
entitlements fail closed. All member identifiers remain internal.
README, CHANGELOG and ADAPTIVE_RESEARCH_PLANNER_RUNBOOK.md updated.

No market data contract, physical multi-device activation, tenant
worker, crypto/prediction broker integration, AI payment, or live
trade is permitted by the synthetic planner. The main project success
gate is still two physical Android devices, independent EdgePilot
identities and independently verified Public accounts.


## v0.2.48 — Matched forward-quality audit without AI execution

The approved AI value/cost strategy now includes an independent offline
paired Brier-score audit for pre-settlement binary forecasts, externally
verified realized outcomes, chronological held-out calibration evidence,
unique matched event provenance, and attributable measured microUSD AI
costs. Claims of causal AI uplift, profits, after-cost alpha or trading
eligibility always remain false; all real outcomes are still unverified.
Negative tests reject private fields, timestamp leakage, unconfirmed
costs, mixed event meanings and repeated IDs. See
PAIRED_RESEARCH_AUDIT_RUNBOOK.md. README, changelog and VERSION
updated. No new provider HTTP, order, money flow, subscription,
production tenant flag or worker was activated. Physical Android
passkeys and independent two-device/two-Public-account acceptance
remain incomplete.


## v0.2.49 — Requested tier is not a commercial entitlement

New standalone dormant tenant_tier_intent module stores authenticated
member-specific requested Free/Plus/Pro/Custom concepts but never
grants a paid plan, overrides data rights, funds AI from the owner,
changes a Public account or enables trading. Ten synthetic members'
preferences, CSRF, disabled/revoked session enforcement and hard paid
grant refusal have negative tests. Real subscriptions/payment providers
and any Play distribution have NOT been approved or activated; see
TENANT_TIER_INTENT_RUNBOOK.md. README/CHANGELOG/VERSION updated.
Physical two-device independent Public accounts remain outstanding.


## v0.2.50 — Fail-closed tenant AI measured overage ledger

If simulated measured token cost exceeds a BYOK member's preflight
hold, settlement now records the higher cost with uncertain status,
and future budget admission counts max(held, actual). Unknown cost
still keeps a full hold. The ledger refuses double settlement and
cross-tenant manipulation, retains prior usage after key disconnect,
and never guarantees provider-side billing limits. Tests in
test_tenant_ai_budget_overage_v0250.py, runbook
TENANT_AI_OVERAGE_RECONCILIATION_RUNBOOK.md. No actual paid model
requests, provider keys, bank action, real orders, subscription
or production activation. Independent two-device Public-account
acceptance and actual physical passkeys remain open.


## v0.2.51 — Approved staging preparation, not a deployment

The user approved preparing a separate EdgePilot staging service in
Belenos's Render workspace, with explicit approval before incurring
additional charges. Current production Render service
edgepilot-private-h9tl is untouched, including its /data disk and
owner Android package. The proposal in
deploy/staging/render-service.proposal.json is intentionally
non-deployable: its signing certificate is an unverified placeholder,
host staging-edgepilot.belenoscreations.biz is only a candidate,
auto-deploy is off, plan is Free and only ephemeral /tmp SQLite is
allowed. backend/engine/staging_release_readiness.py performs a
strict static audit of the proposed settings and the existing server
staging-isolation guard; negative tests prevent copied production
secrets, trading/broker flags, unsafe host/DB/package and unapproved
paid plan changes. README, changelog and
STAGING_RENDER_COST_APPROVAL_RUNBOOK.md updated.

Do NOT create Render services yet without reviewing shared
workspace bandwidth/build-minute usage and potential overages,
confirming approval of extra cost, actual DNS/TLS and genuine public
signed-APK certificate. No new service, DNS or signed staging app
was created. Physical biometric/two-device independent Public
account acceptance remains incomplete. Resume from latest verified
merge/CI, not conversation claims.


## v0.2.52 — Separate Free staging instance created, not yet hardware-ready

With explicit user approval following a Render Billing screenshot,
created `edgepilot-passkey-staging` (`srv-dbpupj2jnfac73ehv1v0`)
under the confirmed workspace, `plan=free`, auto-deploy off, no disk,
Ohio, Docker context `backend`, Dockerfile `backend/Dockerfile`,
main commit `2a53250924c90d350a58ad84f966e08e521b9185`.
Initial deploy `dep-dbpupjajnfac73ehv2og` reported `live`;
Render logs show Gunicorn running and build/deploy events succeeded.
Original owner service `edgepilot-private-h9tl` is unchanged.

Independently extracted **public** SHA-256 signer certificate from the
archived signed v0.19.17 GitHub APK, correcting an old configuration
typo in the preliminary fingerprint: the correct value contains
`...4A:F5:6E:A7...`, not `...4A:F5:6F:A7...`. The current staging
Render environment uses the correct verified signer for
`com.edgepilot.mobile.staging`. The private signing keystore or
password was never accessed, copied or committed. Runtime has its
own /tmp DB, no Public/owner credentials, no trading/broker workers.

**Blockers to finish this stage:** Owner must add the distinct custom
hostname to this staging service in Render, and a separate CNAME
`staging-edgepilot` -> `edgepilot-passkey-staging.onrender.com`
in Squarespace; verify TLS and staging-only Digital Asset Links.
No Render connector action for custom domain or Squarespace DNS
was available. Do not change production DNS. Free instances have no
shell/one-off jobs, so trusted staging-only invitation provisioning
must be designed before the two independent real-device ceremonies.
Then run manual staging-signed Android workflow, verify package/
cert/host, two physical devices and eventually independently allowed
read-only Public accounts on durable storage under separate approval.
No new paid plan, disk, live brokerage or bank transfers approved.
For precise evidence and steps read STAGING_RENDER_LIVE_CHECKPOINT.md.


## v0.2.53 — Disposable operator invite bootstrap prepared

After the owner reported the new staging custom domain **Verified**,
prepared staging-only home redirect to /account, a distinct
/staging-operator page and POST /api/staging/invitations. This
test-only path requires a 256-bit token, only its SHA-256 hash in
EDGE_STAGING_OPERATOR_SHA256, exact configured staging origin and
host, atomic quota of two one-use invites, attempt throttling.
Production / remains the owner dashboard; the operator path
cannot work outside EDGE_ISOLATED_STAGING. No change to the
actual signed production APK or brokerage configuration.

The user reported Render domain verified; HTTP response and Android
OS association are **not independently confirmed** by that statement
alone. No staging signed APK or physical passkey validation yet.
Follow STAGING_OPERATOR_INVITATIONS_RUNBOOK.md to activate the
digest in staging only, deploy the verified GitHub commit
manually because staging auto-deploy is off, and have the user
run the manual signed Android workflow on main with the
exact staging host. Do not claim a GitHub/Render action succeeded
unless the corresponding logs or resulting artifact prove it.
Any Render Free instance spin-down can erase ephemeral invites,
accounts and passkeys; only synthetic trial data allowed.


## v0.2.54 — GitHub signed Android staging run failed safely (phone trailing space)

The owner reported "APK built", but inspection of the actual GitHub
workflow showed run #43011557930 on `main`, event
`workflow_dispatch`, **completed/failure**. The failing step was
"Verify distinct owned staging hostname"; later compile, signing
and artifact steps were skipped. The log showed
`EDGE_STAGING_HOST: staging-edgepilot.belenoscreations.biz `
with one trailing space. Do not claim a signed staging APK exists
from that run.

Fix the manual-only GitHub workflow to normalize *surrounding*
whitespace once, validate the pinned hostname/production exclusion,
write the checked value to GITHUB_ENV, and build with the checked
value rather than the raw workflow form input. Regression tests
execute the real Bash block with trailing spaces, CRLF, malicious
injection, external hosts and production host. No signing key,
provider credential or Render environment change.
After verified PR and main CI, the owner must launch a **fresh**
staging signed workflow on new main; don't rerun the previous
SHA. Only then verify a successful artifact and actual signed APK
package/cert/embedded host before installing alongside the
unchanged production app.


## November 11, 2026 — v0.2.54 signed staging APK verified

The owner dispatched a **new** staging GitHub Actions workflow on
updated main commit `1a3c6a2ba0bfe3390ed8c23d4a9a416d8457fe58`.
Workflow run `43013142566` **completed/success**, including the
strict normalized owned-host check, Android staging assemble,
`apksigner` signing verification and private uploaded artifact
`EdgePilot-v0.19.17-isolated-staging-signed-test`
(artifact ID `13850459385`). The APK was downloaded and independently
inspected. It is `com.edgepilot.mobile.staging`,
`0.19.17-staging`, embeds
`https://staging-edgepilot.belenoscreations.biz/`, and its
v2 signing certificate SHA-256 is
`B1:D5:C5:60:11:10:D4:B3:BF:5A:22:D4:4A:F5:6E:A7:BA:8C:24:F0:46:FA:DB:27:95:2A:EA:18:E7:EC:D3:3F`
matching the verified staging Render association setting. Full APK
SHA-256: `5f1b64ad8c584afb93c72f6c9450567c5dc4a3f853b4aa5651cf47cb05de471a`.
The user received a directly installable APK copy in ChatGPT.

**Open:** On the first Android phone install the second app
**EdgePilot Staging** without removing the owner's production
EdgePilot. Verify staging account login UI and actual custom-domain
HTTPS/Digital Asset Links. Next issue two disposable 60-minute invites
using the separate saved staging operator key, then test both phones'
Android Credential Manager passkeys and session isolation. Free staging
DB remains ephemeral; no live brokerage keys or real trades. Real
Public accounts require durable storage and provider approval.
The earlier workflow run #43011557930 failed before APK compilation
from a trailing hostname space; it is not the successful run.


## v0.2.55 — First physical Android test revealed likely WebAuthn native-origin mismatch

User installed signed `com.edgepilot.mobile.staging` on the real Android
phone, created and signed into the synthetic `Test 1` account,
and tapped "Add biometric passkey". The screen displayed
"Passkey verification failed". **Password/session UI worked**; the
failure was at passkey verification. Do not claim passkeys work.

Code inspection established that `TenantPasskeyStore` used
`expected_origin=self.origin` (the HTTPS website) for both
registration and authentication, while Android Credential Manager
may return `android:apk-key-hash:<base64url(SHA256 app signer)>`.
Google's official passkey guide documents the Android origin.
Prepare a narrowly scoped origin allowlist in v0.2.55 using the
already independently verified **public** staging APK signing
certificate fingerprint. In production, or without strict staging
startup validation, keep only HTTPS. Test with real cryptographic
software WebAuthn fixtures for both origins and reject wrong
native fingerprint, altered challenge and spoofed browser origin.
Do not log clientData/credential material and never accept a
client-selected origin.

**Critical deployment warning:** Render Free staging uses
`/tmp/edgepilot-staging.db`. Any redeploy/spin down can erase Test 1,
passkeys and used invitations. Preserve the owner's original production
service and APK. Recreate Test 1 with newly minted synthetic invitation
only if required; do not use real Public brokerage credentials.
The owner must retest native biometric register/sign-in after the
verified staging fix is deployed. Prior test screenshot confirms
account sign-in only, not successful passkey registration.


## v0.2.56 — User-approved real-time passkey state and self-management

After the owner registered a signed Android staging passkey for
synthetic Test 1 and another for Test 2, screenshots showed the
outdated "Add biometric passkey" button even after successful
enrollment. User explicitly approved updating that UX.

The authenticated account view now loads
`GET /api/identity/passkeys` to get **only its current member's**
active credential IDs, creation timestamps, device type and backup
flags (no device name, biometric data or public/private keys). The
legacy activePasskeys count remains stable; additionally responds
with passkeys array and explicit broker/trading/biometric/identifier
false flags. Client verifies response shape and count, displays
"Set up biometric login" only at zero, otherwise a checkmarked
passkey-enabled state and count. A new Account Security section
lists registered passkeys and adds "Add another passkey" plus
user-confirmed removal. On success, the UI refreshes status; removing
a credential revokes all current member identity sessions and logs
the current UI out, without affecting a second user's sessions.
The UI explains that external credential-manager copies may need
manual deletion. The old APK need not change.

No real Public API credential, order, financial transfer, or live
worker permission was changed. The Render Free staging SQLite is
`/tmp/edgepilot-staging.db`: **backend redeployment can delete
Test 1/Test 2 identities and passkeys**. Confirm account state
after new staging deploy; recreate only synthetic accounts if
necessary. The user's two screenshots demonstrate account
registration and passkey enrollment, but do not by themselves
prove independent physical phones or both passkey sign-ins.
Maintain this distinction in later acceptance claims.


## v0.2.57 — User confirmed Test1 passwordless passkey sign-in; durable staging decision required

In response to a requested sign-out / Use passkey / return to
"Welcome, Test1" test, the owner reported **"Works"**. This supports
one physical Android staging-device synthetic Test1 passkey
authentication roundtrip with previously observed UI transitions
from not configured to "✓ Passkey login enabled — 1 passkey registered".
Do not infer that the separate Test2 image was on another physical
Android device, that it signed in with a passkey after its registration,
or that either member's data survives backend redeploy/restart.

The isolated staging service remains Render Free with a disposable
`/tmp/edgepilot-staging.db`; a deploy demonstrably erased the earlier
test users. Preparing persistent storage is the next blocker.
Current published Render pricing: paid starter web service
approximately $7/month and 1GB disk $0.25/month, for **~$7.25/month
additional base charges**, beyond existing owner production
service and before overages. Free Render Postgres expires after
30 days and cannot be presented as permanent recovery.

The owner must **explicitly authorize incremental recurring costs**
before any paid plan change, disk or database creation. The
`STAGING_PERSISTENCE_DECISION_V0257.md` runbook specifies exact
isolated staging-only `/data` mount and
`EDGE_DB_PATH=/data/edgepilot-staging.db`, no owner credential
reuse, controlled testing across actual Render redeploy and
restart, backup safety and rollback. No deployment, new bill or
change to real brokerage/trading privileges is authorized by this
documentation milestone.
