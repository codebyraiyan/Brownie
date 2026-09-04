# Data Schema — Brownie Finance Head

Defines the structure of the data sources used by the Reconciliation Agent, and shared across all Finance Head agents.

## 1. Internal Ledger (`ledger.csv`)
What the business recorded as sales.

| Column | Type | Example |
|---|---|---|
| transaction_id | text | TXN10234 |
| ledger_entry_id | text | LDG20234 |
| order_id | text | ORD5567 |
| amount | number | 1000.00 |
| date | date | 2026-08-10 |
| status | text | paid / refunded |

`ledger_entry_id` is a unique ID per real accounting entry. A genuine duplicate bug repeats the SAME `ledger_entry_id`; a legitimate second purchase would always get a NEW `ledger_entry_id`. This is what lets the agent tell the two apart instead of guessing from amount/order_id alone.

## 2. Razorpay Settlement Report (`settlement.csv`)
What Razorpay actually paid out after fees/tax.

| Column | Type | Example |
|---|---|---|
| transaction_id | text | TXN10234 |
| settlement_amount | number | 977.00 |
| fee | number | 20.00 |
| tax | number | 3.00 |
| settlement_date | date | 2026-08-11 |
| expected_settlement_date | date | 2026-08-12 |
| status | text | settled / pending |

`expected_settlement_date` is the date the payout SHOULD have settled by (T+2 rule). Comparing it to the actual `settlement_date` / bank `credit_date` is what lets the agent detect real payout delays, not just guess from a fixed 2-day rule.

## 3. Bank Statement (`bank.csv`)
What actually hit the bank account.

| Column | Type | Example |
|---|---|---|
| transaction_id | text | TXN10234 |
| payment_attempt_id | text | ATT30234 |
| credited_amount | number | 977.00 |
| credit_date | date | 2026-08-12 |
| bank_ref | text | REF88213 |

`payment_attempt_id` uniquely identifies the originating payment attempt — supporting evidence for the Exception Investigator, separate from the ledger's own ID.

## 4. Account Snapshot (`account_snapshot.csv`)
A single-row reference point the Cash Forecast Agent needs to compute an actual cash *position* (not just inflows).

| Column | Type | Example |
|---|---|---|
| as_of_timestamp | datetime | 2026-08-28T00:00:00 |
| opening_bank_balance | number | 250000.00 |

## Agent-Generated Fields (not part of raw source data)
These are added by the agents themselves while processing, not present in the original files:
- `reconciliation_status` — set by the Reconciliation Agent (matched / exception)
- `investigation_status` — set by the Exception Investigator (resolved / escalated)

Keeping these out of the raw source data keeps the "ground truth" input clean and makes agent output auditable as a separate layer.

## Key Notes
- `transaction_id` is the shared key across all 3 sources — it's what lets the Reconciliation Agent line up the same transaction across files.
- In the synthetic dataset (see Task #104), records are deliberately corrupted via: bank rows removed (missing_record), ledger rows duplicated with identical `ledger_entry_id` (duplicate_entry), bank credited_amount altered up or down (amount_mismatch), and bank credit_date pushed later (date_mismatch). Transaction IDs themselves are never altered or duplicated.
- Match logic (based on this schema) is defined in `reconciliation-agent.md`.
- Exception rate in the synthetic dataset is intentionally set to 30% for branch-coverage stress-testing — this is a test distribution, not a claim about real-world reconciliation error rates.