# EdgePilot — public repository safeguards

**Status verified November 12, 2026:** GitHub now reports `BelenosCreations/edgepilot-personal` as **public**. Security-preparation PR #102 was merged into `main` as `8282564b6a13ceae2254a1f6dc3beb6b491ebd1f`. The full-history credential-pattern scan, PR application tests, unsigned Android test build, and post-merge main tests reported successful results. This replaces the earlier *preparation only* statement. GitHub publication was an operator decision and did **not** authorize backend publication or new trading functionality.

## Scope: public source, private accounts

The public repository contains application source and nonsecret documentation, not the user's Render persistent databases, registered EdgePilot accounts, Public API secrets, recovery passwords, cloud backups or Android signing key material. Do not mirror any live files, copy a production environment dump, put secrets into branch notes/PRs/issues/actions logs, or attach a real backup to a release. A source-control update does not approve a Render deploy, provider migration, signup, real brokerage balances, automatic order execution or bank transfers.

The passing history checker uses **heuristic recognizers**, not a complete secrecy or privacy proof. Its success does not audit untracked files, all previously generated workflow logs and artifacts, inaccessible refs, user-shared archive links, metadata or any secrets that don't match its patterns. A user-permitted private document can still be inappropriate to publish even if it contains no recognizable key. If a real credential is ever discovered in a public commit or log, treat it as exposed; rotate/revoke it through its provider and follow an incident review. A later `.gitignore` addition or commit deleting the value does not remove the old public commit.

## Free runner and artifact policy

- Use normal `ubuntu-latest` GitHub-hosted runners for standard jobs. Avoid large or metered runners and do not add a paid service without approval.
- The `EdgePilot tests` workflow runs Python unit/HTTP tests, compiles backend, validates browser JS, and performs a **lightweight current checked-out source** scan. It does **not** download all Git history for every PR. Its concurrency group cancels superseded PR runs.
- The separate `Public release history preflight` retains a full-history checkout and a non-disclosing scan; it runs only on explicit dispatch or changes to the historical checker/workflow. Its result must not be confused with current-tree scanning.
- Android unsigned package validation runs for relevant Android source/workflow changes or manual dispatch, not every documentation or backend-only edit. It still checks production/staging package identity. The public PR run produces **no retained APK artifact**; a manual dispatch can upload an unsigned debug APK for three days.
- Existing **manually dispatched, main-branch-only signed** Android workflows and pinned certificate checks remain unchanged. Their signing secrets must never be exposed to fork or untrusted PR workflows. **On a public GitHub repository, signed APK artifacts and workflow details may be publicly accessible**, despite a filename containing the word `private`; do not assume private artifact distribution merely from the workflow name. An operator should review any signed build before dispatch and use an appropriate private delivery mechanism when confidentiality matters.
- GitHub's standard public-repository Actions compute policy does not guarantee free artifact storage, paid runner usage or unrelated resources. Observe billing and retention settings periodically.

## Ongoing user/operator checks

1. Periodically inspect public branches, new PRs, Actions logs/artifacts, releases, fork access, metadata, GitHub secret scanning alerts, and current provider credentials. Confirm that public signup or real accounts were not inadvertently exposed by deployment options.
2. Keep credential recovery keys independent of encrypted archive copies. A backup's matching checksum does not prove that its required decryption keys remain separately recoverable.
3. Keep Android signing/recovery material out of Git and PRs. If a signing artifact is intended to be shared privately, first verify the delivery channel's access controls.
4. Review GitHub budgets and alerts and use the existing low-retention, manual-only artifacts; do not proliferate CI configurations, duplicate full-history scans, or builds on unrelated changes.
5. Decide licensing separately. Public visibility is **not** an open-source license and grants no authority to reuse the project's trademarks or credentials.
6. Before enrolling a second family member, complete a separately authorized, isolated invitation-coexistence or tenant-only migration acceptance stage. Neither public GitHub nor passing synthetic tests opens these routes.

## Historical checkpoint

PR #102 established the public-source preflight and read-only workflow permissions on November 12, 2026. The old checklist correctly required independent review of historical secrets and artifacts before publication. The repository is now public; any outstanding manual checks above remain ongoing obligations rather than evidence of an incomplete visibility switch.

See [README.md](README.md), [CHANGELOG.md](CHANGELOG.md), and [DEVELOPMENT_CONTINUITY.md](DEVELOPMENT_CONTINUITY.md) for architecture, code milestones, and verified development continuity.
