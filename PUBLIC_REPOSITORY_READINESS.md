# EdgePilot — public repository readiness

Status (2026-11-12): PREPARATION ONLY. Do not change GitHub visibility until this checklist has been reviewed. The public-visibility preparation branch does not alter Render or production settings.

## Why
Public repositories receive free GitHub-hosted standard-runner Actions compute; private repositories count against a monthly quota. Large runners, artifact/package storage and unrelated hosting services can still incur costs. Preserve existing private Render services and account isolation.

## Mandatory checks before switching visibility
- [ ] Review the public-release-history-preflight workflow result on a branch/PR with a full-history checkout. It inspects reachable history using heuristics and reports paths but not secret values.
- [ ] Independently review GitHub's secret scanning, old branches, deleted/dangling references, archived logs, Actions artifacts, release files, all committed credentials and operator notes. A passing heuristic does NOT establish a comprehensive audit.
- [ ] Check old operator documents for SSH usernames, hostnames, personal contacts, private backup locations, live login details, secret recovery files or links. Remove anything that should not become public; removing files from the latest branch does not remove history.
- [ ] Keep Public brokerage, EdgePilot app, Render, OpenAI, encryption, recovery and Android private signing keys OUT of tracked files, history, APKs, logs, and releases. Rotate any credential ever committed; .gitignore does not erase previous commits.
- [ ] Review prior signed APK artifacts and releases: artifacts from public Actions may become downloadable. Keep signed builds manually gated to trusted main; do not allow untrusted pull requests to receive signing secrets.
- [ ] Verify all workflows use standard Ubuntu runners and minimal GITHUB_TOKEN permissions. Require appropriate approvals for first-time/fork contributors before executing untrusted PR workflows.
- [ ] Configure metered Actions/Packages budgets and alerts, inspect remaining artifact storage, and retain temporary APKs only briefly (existing 7-14-day retention). Public Actions minutes do not waive artifact storage limits.
- [ ] Verify production Render environment, secrets, encrypted volume, account data and backups remain private. Do not change live trading or bank-transfer gates.
- [ ] Confirm desired license and public documentation. Publishing source does not automatically grant an open-source license.
- [ ] Only after all checks pass: an authorized administrator may use GitHub Settings > General > Danger Zone > Change repository visibility; this preparation does NOT change visibility.

## Returning private later
GitHub permits returning public repositories to private, but existing downloads and public forks cannot be recalled. Private Actions billing/quotas apply again. Review existing forks, public logs, releases and deployments before making that decision.

## Run
On the preparation pull request, verify the Public release history preflight check. After merge, the same workflow can be manually dispatched. A completed PASS means only that recognized patterns were not detected in the reachable Git objects scanned; it does not clear old Actions logs, inaccessible refs, or live secret configuration.

## Development independence
Keep the active EdgePilot development and rollout branches uninterrupted. Do not enable live orders, autonomous trades, withdrawals, or new charges as part of GitHub cost optimization.
