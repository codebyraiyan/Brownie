# Brownie - Reconciliation Exception Report

Generated: 2026-09-02T05:58:43.347295+00:00
Run Task ID: TASK-a788f7cd

## Summary

- **Match rate:** 66.67%
- **Total records:** 168
- **Matched cleanly:** 112
- **Total exceptions:** 56
- **Fully resolved (no further action needed):** 32
- **Approved for follow-up (action still required):** 12
- **Unresolved (require manual investigation):** 12

> **Note on approvals:** transactions marked 'approved' in this run were approved in automated testing mode, not by a real human reviewer. In a live deployment, these would require actual sign-off before any correction is posted.

## Cash Forecast

- **Opening balance:** Rs.250000.0
- **7-day forecast:** Rs.300983.82
- **14-day forecast:** Rs.318170.38
- **30-day forecast:** Rs.420252.56
- **At-risk (7/14/30 day):** Rs.33322.27 / Rs.44498.99 / Rs.58892.23

## Unresolved Exceptions (Could Not Be Resolved Automatically)

These require a human to review before they can be closed out.

| Transaction ID | Finding | Status | Reasoning |
|---|---|---|---|
| TXN10013 | amount_mismatch | escalated | Root cause: genuine_unresolved_anomaly. No automated explanation found for TXN10013 - requires manual investigation |
| TXN10015 | amount_mismatch | escalated | Root cause: genuine_unresolved_anomaly. No automated explanation found for TXN10015 - requires manual investigation |
| TXN10019 | amount_mismatch | escalated | Root cause: genuine_unresolved_anomaly. No automated explanation found for TXN10019 - requires manual investigation |
| TXN10025 | amount_mismatch | escalated | Root cause: genuine_unresolved_anomaly. No automated explanation found for TXN10025 - requires manual investigation |
| TXN10039 | amount_mismatch | escalated | Root cause: genuine_unresolved_anomaly. No automated explanation found for TXN10039 - requires manual investigation |
| TXN10055 | amount_mismatch | escalated | Root cause: genuine_unresolved_anomaly. No automated explanation found for TXN10055 - requires manual investigation |
| TXN10083 | amount_mismatch | escalated | Root cause: genuine_unresolved_anomaly. No automated explanation found for TXN10083 - requires manual investigation |
| TXN10094 | amount_mismatch | escalated | Root cause: genuine_unresolved_anomaly. No automated explanation found for TXN10094 - requires manual investigation |
| TXN10102 | amount_mismatch | escalated | Root cause: genuine_unresolved_anomaly. No automated explanation found for TXN10102 - requires manual investigation |
| TXN10130 | amount_mismatch | escalated | Root cause: genuine_unresolved_anomaly. No automated explanation found for TXN10130 - requires manual investigation |
| TXN10138 | amount_mismatch | escalated | Root cause: genuine_unresolved_anomaly. No automated explanation found for TXN10138 - requires manual investigation |
| TXN10150 | amount_mismatch | escalated | Root cause: genuine_unresolved_anomaly. No automated explanation found for TXN10150 - requires manual investigation |

## Approved for Follow-Up (Action Still Required)

These were reviewed and approved to proceed, but the underlying issue (e.g. tracking down missing funds) is not yet closed - only the investigation step is.

| Transaction ID | Finding | Root Cause | Reasoning |
|---|---|---|---|
| TXN10010 | missing_record | missing_record | Root cause: missing_record. Flag TXN10010 for manual chase - confirm whether funds are in transit or lost |
| TXN10016 | missing_record | missing_record | Root cause: missing_record. Flag TXN10016 for manual chase - confirm whether funds are in transit or lost |
| TXN10018 | missing_record | missing_record | Root cause: missing_record. Flag TXN10018 for manual chase - confirm whether funds are in transit or lost |
| TXN10023 | missing_record | missing_record | Root cause: missing_record. Flag TXN10023 for manual chase - confirm whether funds are in transit or lost |
| TXN10024 | missing_record | missing_record | Root cause: missing_record. Flag TXN10024 for manual chase - confirm whether funds are in transit or lost |
| TXN10032 | missing_record | missing_record | Root cause: missing_record. Flag TXN10032 for manual chase - confirm whether funds are in transit or lost |
| TXN10058 | missing_record | missing_record | Root cause: missing_record. Flag TXN10058 for manual chase - confirm whether funds are in transit or lost |
| TXN10062 | missing_record | missing_record | Root cause: missing_record. Flag TXN10062 for manual chase - confirm whether funds are in transit or lost |
| TXN10108 | missing_record | missing_record | Root cause: missing_record. Flag TXN10108 for manual chase - confirm whether funds are in transit or lost |
| TXN10109 | missing_record | missing_record | Root cause: missing_record. Flag TXN10109 for manual chase - confirm whether funds are in transit or lost |
| TXN10112 | missing_record | missing_record | Root cause: missing_record. Flag TXN10112 for manual chase - confirm whether funds are in transit or lost |
| TXN10140 | missing_record | missing_record | Root cause: missing_record. Flag TXN10140 for manual chase - confirm whether funds are in transit or lost |

## Fully Resolved (No Further Action Needed)

| Transaction ID | Finding | Root Cause | Reasoning |
|---|---|---|---|
| TXN10012 | duplicate_entry | duplicate_transaction | Root cause: duplicate_transaction. Remove duplicate ledger entry for TXN10012 |
| TXN10014 | date_mismatch | late_payout_or_posting | Root cause: late_payout_or_posting. No action needed for TXN10014 - payout delay, expected to settle |
| TXN10031 | duplicate_entry | duplicate_transaction | Root cause: duplicate_transaction. Remove duplicate ledger entry for TXN10031 |
| TXN10035 | duplicate_entry | duplicate_transaction | Root cause: duplicate_transaction. Remove duplicate ledger entry for TXN10035 |
| TXN10037 | duplicate_entry | duplicate_transaction | Root cause: duplicate_transaction. Remove duplicate ledger entry for TXN10037 |
| TXN10040 | duplicate_entry | duplicate_transaction | Root cause: duplicate_transaction. Remove duplicate ledger entry for TXN10040 |
| TXN10048 | date_mismatch | late_payout_or_posting | Root cause: late_payout_or_posting. No action needed for TXN10048 - payout delay, expected to settle |
| TXN10057 | duplicate_entry | duplicate_transaction | Root cause: duplicate_transaction. Remove duplicate ledger entry for TXN10057 |
| TXN10071 | date_mismatch | late_payout_or_posting | Root cause: late_payout_or_posting. No action needed for TXN10071 - payout delay, expected to settle |
| TXN10072 | duplicate_entry | duplicate_transaction | Root cause: duplicate_transaction. Remove duplicate ledger entry for TXN10072 |
| TXN10074 | duplicate_entry | duplicate_transaction | Root cause: duplicate_transaction. Remove duplicate ledger entry for TXN10074 |
| TXN10075 | duplicate_entry | duplicate_transaction | Root cause: duplicate_transaction. Remove duplicate ledger entry for TXN10075 |
| TXN10082 | date_mismatch | late_payout_or_posting | Root cause: late_payout_or_posting. No action needed for TXN10082 - payout delay, expected to settle |
| TXN10088 | date_mismatch | late_payout_or_posting | Root cause: late_payout_or_posting. No action needed for TXN10088 - payout delay, expected to settle |
| TXN10092 | date_mismatch | late_payout_or_posting | Root cause: late_payout_or_posting. No action needed for TXN10092 - payout delay, expected to settle |
| TXN10105 | date_mismatch | late_payout_or_posting | Root cause: late_payout_or_posting. No action needed for TXN10105 - payout delay, expected to settle |
| TXN10127 | date_mismatch | late_payout_or_posting | Root cause: late_payout_or_posting. No action needed for TXN10127 - payout delay, expected to settle |
| TXN10131 | date_mismatch | late_payout_or_posting | Root cause: late_payout_or_posting. No action needed for TXN10131 - payout delay, expected to settle |
| TXN10135 | date_mismatch | late_payout_or_posting | Root cause: late_payout_or_posting. No action needed for TXN10135 - payout delay, expected to settle |
| TXN10142 | date_mismatch | late_payout_or_posting | Root cause: late_payout_or_posting. No action needed for TXN10142 - payout delay, expected to settle |
| TXN10145 | duplicate_entry | duplicate_transaction | Root cause: duplicate_transaction. Remove duplicate ledger entry for TXN10145 |
| TXN10154 | date_mismatch | late_payout_or_posting | Root cause: late_payout_or_posting. No action needed for TXN10154 - payout delay, expected to settle |
| TXN10157 | duplicate_entry | duplicate_transaction | Root cause: duplicate_transaction. Remove duplicate ledger entry for TXN10157 |
| TXN10158 | duplicate_entry | duplicate_transaction | Root cause: duplicate_transaction. Remove duplicate ledger entry for TXN10158 |
| TXN10161 | refund_chargeback | refund_chargeback_not_accounted_for | Root cause: refund_chargeback_not_accounted_for. Record TXN10161 as refunded, adjust expected cash to actual bank amount |
| TXN10162 | refund_chargeback | refund_chargeback_not_accounted_for | Root cause: refund_chargeback_not_accounted_for. Record TXN10162 as refunded, adjust expected cash to actual bank amount |
| TXN10163 | refund_chargeback | refund_chargeback_not_accounted_for | Root cause: refund_chargeback_not_accounted_for. Record TXN10163 as refunded, adjust expected cash to actual bank amount |
| TXN10164 | refund_chargeback | refund_chargeback_not_accounted_for | Root cause: refund_chargeback_not_accounted_for. Record TXN10164 as refunded, adjust expected cash to actual bank amount |
| TXN10165 | refund_chargeback | refund_chargeback_not_accounted_for | Root cause: refund_chargeback_not_accounted_for. Record TXN10165 as refunded, adjust expected cash to actual bank amount |
| TXN10166 | refund_chargeback | refund_chargeback_not_accounted_for | Root cause: refund_chargeback_not_accounted_for. Record TXN10166 as refunded, adjust expected cash to actual bank amount |
| TXN10167 | refund_chargeback | refund_chargeback_not_accounted_for | Root cause: refund_chargeback_not_accounted_for. Record TXN10167 as refunded, adjust expected cash to actual bank amount |
| TXN10168 | refund_chargeback | refund_chargeback_not_accounted_for | Root cause: refund_chargeback_not_accounted_for. Record TXN10168 as refunded, adjust expected cash to actual bank amount |
