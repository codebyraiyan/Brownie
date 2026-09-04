# Reconciliation Agent — Match/Exception Logic

Performs 3-way matching across Internal Ledger, Razorpay Settlement Report, and Bank Statement.

## Match Criteria
A record is a **Match** when:
- Ledger amount minus fees/tax = Settlement amount
- Settlement amount = Bank credited amount
- All three share the same transaction reference
- Settlement-to-bank credit gap is 2 days or less (normal payout delay)

## Exception Criteria
A record is an **Exception** when any of the following occur:
- Amount mismatch beyond expected fees/tax
- Record missing in one or more of the three sources
- Duplicate entries
- Settlement-to-bank gap greater than 2 days

Exceptions are passed downstream to the Exception Investigator agent for root-cause diagnosis.

--- 

---

# Appendix: Canonical Matching Algorithm (Task #203)

This section defines the exact step-by-step logic the Reconciliation Agent runs, replacing the earlier ledger-first assumption with a full outer join across all 3 sources.

## 1. Full Outer Join
Instead of starting from the ledger and checking outward, collect every unique `transaction_id` found across all 3 files first:

```
all_ids = unique(ledger IDs + settlement IDs + bank IDs)
```

For each ID, determine its presence in each source:

```json
{
  "transaction_id": "TXN10234",
  "presence_ledger": true,
  "presence_settlement": true,
  "presence_bank": false
}
```

This catches orphan records too — e.g. a bank credit or settlement with no matching ledger entry — which a ledger-first approach would miss entirely.

## 2. Duplicate Grouping
Group ledger rows by `ledger_entry_id` (not `transaction_id`). If a `ledger_entry_id` appears more than once, flag as `duplicate_entry`. This is what distinguishes a genuine duplicate from a legitimate repeat purchase, which would carry a different `ledger_entry_id`.

## 3. Amount Comparison with Tolerance
```
expected_settlement = round(ledger.amount - fee - tax, 2)
if abs(expected_settlement - bank.credited_amount) <= 1.00:
    amounts match
else:
    flag as amount_mismatch
```
A ₹1.00 tolerance absorbs rounding noise without hiding genuine errors.

## 4. Date Gap Check
```
gap = bank.credit_date - settlement.settlement_date
if gap <= 2 days: normal
if gap > 2 days: flag as date_mismatch
```

## 5. Precedence Order
A record may qualify for more than one exception type. To keep results deterministic, checks run in this fixed order, and the first one that applies is reported:

1. `missing_record`
2. `duplicate_entry`
3. `amount_mismatch`
4. `date_mismatch`
5. If none apply: `matched`

## 6. Canonical Output per Transaction
Every transaction produces exactly one final record:

```json
{
  "transaction_id": "TXN10234",
  "presence_ledger": true,
  "presence_settlement": true,
  "presence_bank": true,
  "expected_amount": 977.00,
  "actual_amount": 977.00,
  "variance": 0.00,
  "date_gap_days": 1,
  "exception_code": null,
  "reconciliation_status": "matched"
}
```

`reconciliation_status` is an agent-generated field (see `schema.md`), not part of the raw source data.

---

# Correction (Task #208): Compound Exceptions, Null Handling, Duplicate Scope

## 1. Fix: Single-code precedence hid compound exceptions
The original precedence order reported only ONE exception code per transaction, so a record that was both missing AND duplicated would only ever show as `missing_record` — the duplicate could then slip through uninvestigated.

**Corrected approach:** compute and report ALL applicable exception codes, plus one `primary_exception_code` used only for queue ordering (which gets investigated with highest priority):

```json
{
  "transaction_id": "TXN10234",
  "exception_codes": ["missing_record", "duplicate_entry"],
  "primary_exception_code": "missing_record"
}
```

Precedence order for `primary_exception_code` selection stays: missing_record → duplicate_entry → amount_mismatch → date_mismatch.

## 2. Fix: Null handling for missing records
The amount comparison formula (`ledger.amount - fee - tax`) assumes a settlement row exists. If a record is `missing_record` at the settlement or bank level, fee/tax/amount fields don't exist for that side. Rule: if any required field for a check is missing, skip that specific check (don't error, don't default to 0) and rely on `missing_record` alone for that transaction.

## 3. Fix: Date gap must not accept negative values as normal
Original rule (`gap <= 2`) would silently accept a negative gap (bank credit dated BEFORE settlement — logically impossible in real data, likely a data error). Corrected rule:
```
if 0 <= gap <= 2: normal
else: date_mismatch  (this now also catches impossible negative gaps)
```

## 4. Fix: Duplicate checking scope
Original duplicate check only grouped ledger rows by `ledger_entry_id`. Since the main doc calls duplicates an exception "in any source," duplicate grouping must also run independently on `settlement` (no natural row ID yet — flag as a data gap) and `bank` (`payment_attempt_id` can serve this role, per the `schema.md` update from Task #108).