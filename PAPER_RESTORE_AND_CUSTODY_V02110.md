# Synthetic tenant restore and Decimal custody recovery

## Pinned tenant restore

The offline archive rehearsal now offers a pinned format for the marked
authenticated tenant fixture. An operator supplies a fixed policy for each
synthetic paper wallet, including wallets under disabled users, disabled
accounts or revoked connections. The pin binds the encrypted archive bytes
and the policy map. Retain the latest accepted pin and policies separately
from the ciphertext, and use that pin when restoring. A pin generated from a
candidate archive during recovery provides no rollback protection.

The audit reconstructs fractional quantities, integer-cent cash and basis,
account-level realized gains and losses, and the worst historical cumulative
loss. It checks protected exposure, per-trade limits and any purchase after
the historical stop. Sales of existing positions remain valid. The existing
request ID and digest are preserved in append order and checked for duplicate
scope. The dormant event rows omit some original request fields, so a digest
cannot be regenerated from an archived event. The independently retained pin
authenticates the exact archived digest and historical accounting together.

Restore audits privately before and after quarantine. It preserves account
ownership and existing revocation timestamps, disables restored account links,
revokes restored connections and passkeys, and invalidates saved sessions and
leases. Existing paper rows are checked for equality across quarantine.
Publication is exclusive and stays on verified tmpfs. Tests cover active and
revoked accounts sharing a request UUID, exact cents, sticky stops after a
profit, changed policy, changed digest and old ciphertext. The original
synthetic archive format retains its existing structural audit.

## Independent custody and loss of either resource

Use separate locations and custody roles for the encrypted ledger archive,
the signed witness snapshot, the latest witness receipt and the keys. The
witness snapshot is authenticated by its event chain and contains sensitive
synthetic metadata. Store it under the same access controls as the witness.
Export it with `DecimalCustody.backup` at the exact retained receipt.

- **Lost ledger.** Read the independently held receipt and the surviving
  witness. Verify the latest witness state and obtain explicit approval for
  the exact active record, ciphertext and new destination. Use
  `restore_ledger`, which holds the witness lock during archive verification
  and publication. A pending rotation, quarantine, stale receipt or older
  ledger is refused.
- **Lost witness.** Use `DecimalCustody.recover` with the exact retained
  snapshot and receipt, the surviving ledger and independent keys. The
  tool verifies the signed event history and checks the ledger against the
  active or prepared checkpoint before publishing to a new witness path.
  A terminal quarantine is safe to recover from the exact snapshot.
  An unclaimed pending rotation is refused because a later claim may have
  been lost. A recovered claim stays consumed.
- **Interrupted rotation.** The witness commits the claim, then calls the
  operator's independent receipt retention callback. That callback must
  compare-and-swap the pending receipt to the claim, durably retain it and
  acknowledge the exact value. An absent or ambiguous acknowledgment leaves
  the claim consumed. Review a matching new ledger and explicitly promote it
  under the prepared target. Quarantine an ambiguous older ledger.

The tests model an independently retained receipt and single-resource loss.
Operational custody, protection against simultaneous rollback of both
resources and their retained evidence, and power-loss consistency remain
open. A local lock serializes cooperating processes. The claim handoff and
SQLite ledger commit have distinct failure points. Production recovery and
execution are outside the rehearsal.

## Owner history acceptance

The owner dashboard displays the number of validated bars alongside Public's
regular-series expected count when supplied. The figures describe the
provider response. Coverage, missing bars and market activity cannot be
inferred from their difference alone. Source OHLC, volume, UTC timestamps
and the one-week or one-month scope stay session-only. See
[Public Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2).

For targeted acceptance on the owner's device, sign in to the owner dashboard,
select the linked Public account, and retrieve MSFT one-week history. Confirm
that the panel identifies Public as the source and shows UTC timestamps, source
OHLC and volume. If Public reports an expected count, confirm that it appears
beside the displayed count. Change the period to one month and confirm that
the old bars clear before retrieving the new result. An entitlement or source
error should leave the table empty. ETF and crypto checks can use SPY and BTC
when those instruments are available to the selected account. Record the
symbol, period and pass or sanitized error only. Prior snapshot and MSFT
quote acceptance still apply. Provider permission remains a development
assumption and real history acceptance is pending.
