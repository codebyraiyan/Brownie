# Cash Forecast Agent — Forecast Logic

Uses confirmed/matched reconciliation data to project future cash position.

## Inputs
- Matched transactions (from Reconciliation Agent) with their typical settlement delay (T+2 days)
- Pending/unsettled transactions still in the pipeline

## Forecast Method
- Projects expected cash inflow across three horizons: 7, 14, and 30 days
- Adds up matched + expected-to-settle amounts per horizon

## Risk Flagging
- If a transaction is stuck in "Escalated" status (from Exception Investigator) and its expected settlement date falls within the forecast horizon, it is flagged as **at-risk** — since it may not arrive on time.

Output: a forecast table + list of at-risk amounts per horizon.

---

---

# Appendix: Computation Logic (Task #205)

## 1. Starting Point: Opening Balance
Pulled from `account_snapshot.csv`:
```
opening_balance = 250,000.00 (as of 2026-08-28)
```
Every forecast starts from this real balance, not zero — this is what makes the output an actual cash *position*, not just a list of incoming amounts.

## 2. Categorizing Every Transaction
Based on the Reconciliation Agent + Exception Investigator's output:

| Category | Included in forecast? |
|---|---|
| matched | Yes — already settled, counted immediately |
| auto_resolved exceptions | Yes — safe to count as expected |
| pending_approval / escalated exceptions | No — held out, listed separately as at-risk |

## 3. Forecast Calculation (per horizon: 7, 14, 30 days)
```
forecast[horizon] = opening_balance
                   + sum(matched amounts already settled)
                   + sum(auto_resolved amounts expected to land within horizon)
```
Only amounts expected to settle within that specific horizon window are counted toward it.

## 4. At-Risk Amount Flagging
```
at_risk[horizon] = sum(pending_approval + escalated amounts
                        where expected_settlement_date falls within horizon)
```
This is reported separately from the confident forecast, so an uncertain number is never mistaken for a guaranteed one.

## 5. Fee Model Assumption (documented limitation)
This forecast assumes a fixed fee structure (2% fee + 18% GST), consistent with the synthetic dataset. Real-world fee models often vary by payment method, volume tier, and time. A production version would need a versioned fee-rule table instead of a fixed rate. This is an intentional scope decision for the current build, not an oversight.

## 6. Output Format
```json
{
  "as_of": "2026-08-28",
  "opening_balance": 250000.00,
  "forecast": {
    "7_day": 45000.00,
    "14_day": 92000.00,
    "30_day": 210000.00
  },
  "at_risk": {
    "7_day": 3000.00,
    "14_day": 8500.00,
    "30_day": 12000.00
  }
}
```

---

# Correction (Task #208): Cash Treatment States

This section supersedes the forecast calculation in the earlier appendix (Task #205), which double-counted bank-confirmed money by adding "matched amounts already settled" on top of an opening balance that already included them.

## Corrected Cash States (mutually exclusive)

| cash_treatment | Meaning | Included in forecast? |
|---|---|---|
| `bank_confirmed` | Already landed in the bank, already inside `opening_balance` | Never added again |
| `expected_inflow` | Confirmed-good transaction, not yet landed, expected within horizon | Added to forecast |
| `at_risk` | Pending approval or escalated — may not arrive as expected | Reported separately, never added to confident forecast |
| `excluded` | Rejected, or a non-cash ledger correction | Not counted anywhere in cash figures |

## Corrected Formula

```
forecast[horizon] = opening_balance
                   + sum(amount where cash_treatment == "expected_inflow"
                         and expected_settlement_date falls within horizon)

at_risk[horizon] = sum(amount where cash_treatment == "at_risk"
                        and expected_settlement_date falls within horizon)
```

`bank_confirmed` items are never added — they're already inside `opening_balance` by definition. `excluded` items never appear in either total.

## Rejected Transactions
A `rejected` investigation outcome maps to `cash_treatment: "at_risk"` if still awaiting re-investigation, or `"excluded"` if the correction was fully discarded with no further action expected. It is never silently omitted — every transaction must resolve to exactly one of the 4 states above before Cash Forecast Agent runs.