# v0.2.81 — Safe operator-only family readiness command

**Scope:** a non-destructive, read-only check of the existing paid Render service **before** enabling the first private family invitation. This is not a web endpoint, background task, cron job, new paid service or account migration.

The Docker image already includes `backend/tools`. The new `tools/inspect_family_invitation_readiness.py` may be invoked from an existing authenticated **Render SSH session** by the service owner. Its only output is a sanitized JSON object containing aggregate stored member, connection, session and linked-account counts, the private-disk and disabled-enrollment inspection result, and explicit `false` values for trading, transfers, real phone acceptance and additional member authorization.

## Operator command (only from the existing SSH connection)

```bash
ssh -i "<existing SSH key path>" "<existing Render SSH host>" \
  'cd /app && EDGE_FAMILY_ROLLOUT_PREFLIGHT_ALLOWED=true python3 tools/inspect_family_invitation_readiness.py --approve "INSPECT PRIVATE FAMILY READINESS ONLY"'
```

This command does **not** read recovery keys from the user's phone, receive any passphrase on stdin, print credentials, issue invitation tokens, read account balances or access Public's network. Enter the SSH key passphrase only in the local SSH unlock prompt, never in the command or public GitHub. Only the ephemeral `EDGE_FAMILY_ROLLOUT_PREFLIGHT_ALLOWED=true` environment variable is supplied to the **one operator process**. No Render environment settings are changed.

On **success**, the returned JSON includes `"inspection":"passed"`, `"enrollment_currently_disabled":true`, `"member_registration_authorized":false`, `"live_trading_enabled":false`, `"bank_transfers_enabled":false`. The check verifies both private database file owners/modes, separate fixed paid-disk paths, one enabled separately authenticated owner, existing decryptable encrypted Public credential and stored verified account link, integrity, foreign keys, and the exact safe discovery-only flags, while rejecting previously issued pending invitations.

On **failure**, the command returns status 2 and a fixed nonsecret denial message. Never respond by deleting an archive, recreating a user, rotating a Fernet key, manually changing database contents, or mass-enabling production flags. The application and existing owner login remain unchanged. Any reason for denial must be investigated without publishing environment values or individual account details.

## What the inspection cannot establish

A healthy private SQLite database is **not** proof that the original owner can log in from a real phone or that Public will currently accept the saved API secret. The report accordingly says `legacy_login_end_to_end_verified=false` and `public_network_verification_performed=false`. It also reports `external_backup_custody_independently_proven=false` even though the owner previously completed a separate backup download/checksum verification; this tool does not read private Google Drive or Android backup storage.

The public GitHub repository is never a recovery-key vault. Do not post the real SSH command with secrets, screenshots of actual invitation tokens, any real API key, raw environment dumps or database files. A passing preflight does not verify a second physical phone, independent second Public account, multi-member archive, or operational rollback.

## Subsequent rollout gates

After a verified preflight and separate reconfirmation of the owner's real login and off-service backup, the previously authorized **invitation-only architecture** may be enabled using only the three already reviewed runtime switches together, with all no-trade/no-bank-transfer limits retained. No real invitation may be generated without a further owner confirmation; the first issuance must be an authenticated owner/CSRF action on the private account page. A second member would need their own EdgePilot login and separate Public key, followed by an immediate pause of new invitations and an authenticated off-service **multi-member** backup/restore exercise.

If additional checks are not yet complete, leave all three invitation switches off. The existing service is already configured to deploy merges to `main`; the CLI itself is not executed by a deployment.

## Test coverage

Synthetic unit tests assert exact approval, ephemeral flag and fixed paid-disk paths; no query on a denied invocation; sanitized JSON on a successful mocked audit; static denial even if an internal exception contains a fake private identity; rejection of any report that would claim live orders, transfers or invitation authorization; absence of Flask/HTTP routes and subprocess mutation; and clear separation between private-disk verification and live authentication. This is not real production inspection.
