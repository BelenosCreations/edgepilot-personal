# v0.2.93 — Failed owner MSFT quote: browser parser and source diagnostics

**Observed:** The owner tried `msft` in the identity-backed `/owner` quote form and did not receive a stock quote. The form correctly uppercases this to `MSFT` and uses EQUITY. The Public Get quotes endpoint documents `POST /userapigateway/marketdata/{accountId}/quotes` and requires `marketdata` account scope.

## Confirmed client defect
The original browser's `readSourceTime` contained a double-escaped digit pattern, so it failed even on an otherwise valid Public ISO-8601 timestamp such as `2026-11-12T20:00:00+00:00`. Syntax-only CI had not caught this. The hotfix corrects the parser and executes the actual production JS functions under Node using synthetic MSFT responses, including intentionally incorrect source account, category and trading flags.

Public's documentation includes successful equity quote samples with `lastTimestamp` but without `bidTimestamp` or `askTimestamp`. The server now retains source-reported bid/ask numeric strings without these *optional* timestamps, marks the side timestamps unavailable and **never** calls the book fresh without valid, sufficiently recent independent timestamps. The mandatory last quote/time and all source, account, crossing and revocation checks remain strict. No book price is executable or paper-fill eligible.

## Remaining unknowns
- The reported failed request was not accompanied by a sanitized HTTP status or a verified real Public upstream response. We cannot prove whether the actual Public API call succeeded, returned malformed data, was rate-limited, or lacked the required `marketdata` scope.
- The live Render status and synthetic regression success do not certify real owner permissions.
- Do **not** ask for API keys, linked account IDs, a raw API response, personal brokerage balance, server environment secrets or privately identified log lines.

## Owner acceptance
1. Following verified GitHub PR/main CI and existing Render deployment, open the **independent owner** dashboard at `https://edgepilot-private-h9tl.onrender.com/owner`.
2. Under **Source-attributed market research**, choose **Stock / ETF (equity)**, enter `MSFT`, and press **Retrieve source quote** once. Expect only actual Public-reported values and timestamps or a safe unavailable message.
3. If failure persists, report the sanitized dashboard status, particularly whether it says **HTTP** and its numeric status or **browser validation**. These messages do not expose credentials or raw provider errors. If authorization is absent, verify Public's official account `marketdata` scope before attempting any other data integrations.
4. There is no background polling, saved market prices, synthesized quotes, paper ledger integration, live brokerage execution, autonomous order or bank transfer. No new paid services.

Recheck the existing identity and provider account binding if the independent owner gate fails. Preserve existing credentials, multi-user isolation, encrypted recovery and all disabled production trading controls.
