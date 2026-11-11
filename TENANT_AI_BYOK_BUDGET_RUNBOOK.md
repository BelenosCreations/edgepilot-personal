# EdgePilot v0.2.45 — Dormant per-user AI BYOK and budget isolation

## What is implemented

A separate, **not activated** tenant AI configuration/reconciliation module
under backend/engine/tenant_ai_budget_vault.py. It is designed for one shared
EdgePilot backend with up to ten private members, without requiring ten
different servers or sharing the owner OpenAI account.

Each member's data is stored in tables keyed by the session-derived
tenant user UUID. No client-supplied user_id is accepted. Changes use
SQLite BEGIN IMMEDIATE and re-validate the current independent identity
session and CSRF under the lock, including revoked/disabled users and
credential-version changes. There is no fallback to EDGE_APP_TOKEN,
OPENAI_API_KEY, PUBLIC_API_SECRET, or the Public tenant vault.

Individual modes:
- none (default): useful non-AI research path, no AI request.
- byok: opt-in selected by the member, their own provider account billed
  separately when a future permitted execution adapter is enabled.
  The module currently stores keys and computes **synthetic local
  reservations only**. It does not call OpenAI.
- managed credits: explicitly rejected; this is a future owner-approved
  abstraction only, not a purchase or billing system.

The per-member analysis-depth preference and monthly budget are distinct
from any subscription, actual OpenAI charges, brokerage fees or hosting
allocation. A friend cannot consume the owner's budget or key by default.
Stored fake test provider secrets are encrypted using **a separate AI-only
Fernet encryption key** supplied to the test store, not the Public-key vault
or Android bundle. Encrypted payloads include the owner UUID; the module
never returns decrypted secrets, the key ciphertext or any provider
credential from its status/mutation results. Key changes increment a
version; selecting no AI disconnects and deletes the ciphertext, while
historic/uncertain ledger charges are retained for attribution.

A tenant reservation is keyed to a verified identity, UTC month, explicitly
allowlisted model, current price review and the user's **own** cap,
serialized with a SQLite write lock. The current simulated finalize
path accepts synthetic token usage, marks uncertainty conservatively,
denies double-settlement and denies any attempt to modify another user's
reservation. The in-app cap is not a provider billing guarantee.

## What is NOT implemented

- No production Flask/UI route, account enrollment, paid OpenAI request,
  live provider key validation or billing service is added or enabled.
- No friend can add a real provider key to a live EdgePilot account yet.
  BYOK direct-provider billing requires the user to create a separately
  billed API provider account; ChatGPT subscriptions are not API credit.
- The legacy owner OpenAI key and budget are NOT migrated into a tenant
  record or exposed to others.
- No managed subscription, merchant integration, customer payment,
  distribution or commercial terms are activated.
- No production tenant migration, ten-device capacity acceptance,
  actual user passkeys, independent provider permission or trading
  automation is inferred by this module.
- Key rotation of the master encryption key, recovery policies, secure
  operational storage, audit log retention, model routing and consented
  per-user HTTP execution still need independent tests before deployment.
- No provider API, market data or external HTTPS endpoint was called
  by this development milestone.

## Reproducible test

From backend/ with requirements installed:

    python -m unittest tests.test_tenant_ai_byok_v0245 -v

The ten-member synthetic test uses ten fake provider keys and ten separate
independent member identities in one SQLite backend. It tests ciphertext
isolation, ten concurrent isolated requests, per-user budgets, key/CSRF
swap denial, cross-owner settlement refusal, invalid credentials, session
revocation, model allowlist, budget rollover, uncertain holds, revoked
connections, managed-billing denial and missing encryption keys. A network
interceptor throws if any test tries to contact an outside provider.

## Next gated milestones

1. Feature-gated HTTP account settings/consent actions without returning
   credentials or authorizing any AI provider call by default.
2. Provider-independent cost/entitlement interface, with explicit owner-
   funded allocation only after approval. No commercial collection.
3. Security review: independent key management, restore/rotation,
   account recovery and ten-user load evidence.
4. Real Android passkey and two independently owned Public API accounts
   on separate devices; read-only provider access only after permission
   checks. No live orders/transfers.

See AI_ANALYSIS_COST_STRATEGY.md, AI_COST_ACCOUNTING_RUNBOOK.md,
MULTIUSER_PLATFORM_ACCEPTANCE.md and DEVELOPMENT_CONTINUITY.md.


## v0.2.50 safety clarification

Synthetic reconciliation now retains larger measured usage above the
original reservation as `uncertain` and counts max(held,actual) toward
the user's local limit. This prevents undercounting in later simulated
admissions but does not guarantee that any real AI vendor will enforce
the in-app limit. See TENANT_AI_OVERAGE_RECONCILIATION_RUNBOOK.md.
