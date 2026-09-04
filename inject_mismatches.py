# inject_mismatches.py
#
# What this script does (all in ONE run, no dependency on other scripts):
# 1. Generates 160 CLEAN transactions from scratch (same logic as generate_data.py)
# 2. Deliberately breaks 48 of them (30%) across 4 exception types
# 3. Writes ledger.csv, settlement.csv, bank.csv, answer_key.csv, account_snapshot.csv
#
# WHY THIS VERSION IS DIFFERENT FROM BEFORE:
# The old version read already-generated CSVs and mutated them in place.
# Running it twice would corrupt the data further each time (a real bug,
# caught in audit). This version always builds fresh clean data first,
# in memory, then injects mismatches once - so running it 1 time or 100
# times in a row always produces the EXACT SAME correct result.
#
# HOW TO RUN THIS:
# Just run: python3 inject_mismatches.py
# (You do NOT need to run generate_data.py first anymore - this does both.)

import csv
import random
import os
import sys
from datetime import date, timedelta

random.seed(42)   # for the clean data (same as generate_data.py)
INJECT_SEED = 7   # separate seed for which records get broken

DATA_DIR = "data"

# TASK #404: NUM_RECORDS can now be overridden from the command line for
# scalability testing, e.g.: python3 inject_mismatches.py 500
# Default stays 160 - nothing changes for the normal demo dataset.
NUM_RECORDS = int(sys.argv[1]) if len(sys.argv) > 1 else 160

# TASK #406 AUDIT FIX: reject invalid sizes outright rather than silently
# producing an empty or nonsensical dataset (e.g. negative counts, which
# previously slipped through and produced malformed refund IDs).
if NUM_RECORDS < 4:
    print(f"ERROR: NUM_RECORDS must be at least 4 (got {NUM_RECORDS}). "
          f"Smaller values can't produce a meaningful 30% split across 4 exception types.")
    sys.exit(1)
NUM_REFUNDS = max(1, round(NUM_RECORDS * 0.05))  # TASK #404: scales with dataset size (~5%)

FEE_PERCENT = 0.02
TAX_PERCENT = 0.18


def generate_clean_data():
    """Builds 160 clean, fully-matching transactions from scratch."""
    ledger, settlement, bank = [], [], []
    start_date = date(2026, 7, 1)

    for i in range(1, NUM_RECORDS + 1):
        transaction_id = f"TXN{10000 + i}"
        ledger_entry_id = f"LDG{20000 + i}"     # unique ID per real accounting entry
        order_id = f"ORD{5000 + i}"
        payment_attempt_id = f"ATT{30000 + i}"  # unique ID per real payment attempt

        amount = round(random.uniform(200, 5000), 2)
        ledger_date = start_date + timedelta(days=random.randint(0, 60))

        fee = round(amount * FEE_PERCENT, 2)
        tax = round(fee * TAX_PERCENT, 2)
        settlement_amount = round(amount - fee - tax, 2)

        # expected_settlement_date = the date it SHOULD settle by (T+2 rule)
        expected_settlement_date = ledger_date + timedelta(days=2)
        # settlement_date = when it ACTUALLY settled (normally T+1 or T+2)
        settlement_date = ledger_date + timedelta(days=random.choice([1, 2]))
        credit_date = settlement_date + timedelta(days=random.choice([0, 1, 2]))

        bank_ref = f"REF{90000 + i}"

        ledger.append({
            "transaction_id": transaction_id,
            "ledger_entry_id": ledger_entry_id,
            "order_id": order_id,
            "amount": amount,
            "date": ledger_date.isoformat(),
            "status": "paid"
        })

        settlement.append({
            "transaction_id": transaction_id,
            "settlement_amount": settlement_amount,
            "fee": fee,
            "tax": tax,
            "settlement_date": settlement_date.isoformat(),
            "expected_settlement_date": expected_settlement_date.isoformat(),
            "status": "settled"
        })

        bank.append({
            "transaction_id": transaction_id,
            "payment_attempt_id": payment_attempt_id,
            "credited_amount": settlement_amount,
            "credit_date": credit_date.isoformat(),
            "bank_ref": bank_ref
        })

    return ledger, settlement, bank


def inject_mismatches(ledger, settlement, bank):
    """Takes clean data and deliberately breaks ~30% of records across 4 types."""
    rng = random.Random(INJECT_SEED)   # separate, independent random stream
    answer_key = []

    all_txn_ids = [row["transaction_id"] for row in ledger]
    # TASK #406 AUDIT FIX: the old formula (round(N*0.30/4)*4) rounded down
    # to ZERO for any N below 7, silently disabling exception injection
    # entirely at small scale. per_type now has a floor of 1, guaranteeing
    # every exception type appears at least once regardless of N.
    per_type = max(1, round(len(all_txn_ids) * 0.30 / 4))
    exception_count = per_type * 4
    broken_ids = rng.sample(all_txn_ids, exception_count)

    amount_mismatch_ids = broken_ids[0:per_type]
    missing_record_ids = broken_ids[per_type:per_type*2]
    duplicate_ids = broken_ids[per_type*2:per_type*3]
    date_mismatch_ids = broken_ids[per_type*3:per_type*4]

    # --- 1. AMOUNT MISMATCH ---
    # Half get a short credit, half get an over-credit - more realistic than always-short.
    for row in bank:
        if row["transaction_id"] in amount_mismatch_ids:
            original = float(row["credited_amount"])
            error = round(rng.uniform(10, 100), 2)
            direction = rng.choice([-1, 1])
            row["credited_amount"] = round(original + (error * direction), 2)
            answer_key.append({
                "transaction_id": row["transaction_id"],
                "exception_type": "amount_mismatch",
                "reason": f"Bank credited amount differs from expected settlement amount by ~{error} ({'short' if direction < 0 else 'over'}-credit)"
            })

    # --- 2. MISSING RECORD ---
    bank = [row for row in bank if row["transaction_id"] not in missing_record_ids]
    for txn_id in missing_record_ids:
        answer_key.append({
            "transaction_id": txn_id,
            "exception_type": "missing_record",
            "reason": "Transaction exists in ledger and settlement but missing from bank statement"
        })

    # --- 3. DUPLICATE ---
    # IMPORTANT: the duplicate keeps the SAME ledger_entry_id as the original.
    # This is what proves it's a genuine duplicate (a data/processing error),
    # not a legitimate second purchase - a real repeat purchase would always
    # get its OWN new ledger_entry_id, since it's a separate real event.
    duplicate_rows = [row.copy() for row in ledger if row["transaction_id"] in duplicate_ids]
    ledger.extend(duplicate_rows)
    for txn_id in duplicate_ids:
        answer_key.append({
            "transaction_id": txn_id,
            "exception_type": "duplicate_entry",
            "reason": "Same ledger_entry_id appears twice in ledger.csv - confirmed duplicate, not a repeat purchase"
        })

    # --- 4. DATE MISMATCH ---
    for row in bank:
        if row["transaction_id"] in date_mismatch_ids:
            # TASK #406 AUDIT FIX: split on "T" first in case a date string
            # ever includes a time component (e.g. "2026-07-02T10:00:00"),
            # which would otherwise crash int() on the day+time fragment.
            date_only = row["credit_date"].split("T")[0]
            y, m, d = map(int, date_only.split("-"))
            new_date = date(y, m, d) + timedelta(days=rng.randint(5, 10))
            row["credit_date"] = new_date.isoformat()
            answer_key.append({
                "transaction_id": row["transaction_id"],
                "exception_type": "date_mismatch",
                "reason": "Bank credit date is more than 2 days after settlement date"
            })

    return ledger, settlement, bank, answer_key


def write_csv(filename, rows, fieldnames):
    with open(f"{DATA_DIR}/{filename}", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def add_refund_cases(ledger, settlement, bank, answer_key, rng):
    """
    Adds 8 NEW transactions (continuing the ID sequence) representing a
    legitimate business event: a sale that was later refunded. These are
    NOT part of the original 48 injected data-error exceptions - they are
    a 5th, separate scenario that tests whether the agent can tell the
    difference between "a real data problem" and "a real refund".

    A refund shows up looking exactly like a big amount_mismatch (the bank
    credited far less than expected) - but ledger.status = "refunded"
    explains WHY, so a smart agent should NOT treat this as a data error.
    """
    start_index = NUM_RECORDS + 1  # continues after the last base record

    for i in range(NUM_REFUNDS):
        idx = start_index + i
        transaction_id = f"TXN{10000 + idx}"
        ledger_entry_id = f"LDG{20000 + idx}"
        order_id = f"ORD{5000 + idx}"
        payment_attempt_id = f"ATT{30000 + idx}"

        amount = round(rng.uniform(200, 5000), 2)
        sale_date = date(2026, 7, 1) + timedelta(days=rng.randint(0, 60))

        fee = round(amount * FEE_PERCENT, 2)
        tax = round(fee * TAX_PERCENT, 2)
        settlement_amount = round(amount - fee - tax, 2)

        settlement_date = sale_date + timedelta(days=rng.choice([1, 2]))
        credit_date = settlement_date + timedelta(days=rng.choice([0, 1, 2]))

        # The refund happens AFTER settlement - so settlement.csv still shows
        # the original settled amount, but the bank statement shows 0 (or a
        # partial amount) since the money was returned to the customer.
        refund_type = rng.choice(["full", "partial"])
        if refund_type == "full":
            actual_credited = 0.00
        else:
            actual_credited = round(settlement_amount * rng.uniform(0.3, 0.7), 2)

        ledger.append({
            "transaction_id": transaction_id,
            "ledger_entry_id": ledger_entry_id,
            "order_id": order_id,
            "amount": amount,
            "date": sale_date.isoformat(),
            "status": "refunded"   # <-- this is the signal the agent must use
        })

        settlement.append({
            "transaction_id": transaction_id,
            "settlement_amount": settlement_amount,
            "fee": fee,
            "tax": tax,
            "settlement_date": settlement_date.isoformat(),
            "expected_settlement_date": (sale_date + timedelta(days=2)).isoformat(),
            "status": "settled"
        })

        bank.append({
            "transaction_id": transaction_id,
            "payment_attempt_id": payment_attempt_id,
            "credited_amount": actual_credited,
            "credit_date": credit_date.isoformat(),
            "bank_ref": f"REF{90000 + idx}"
        })

        answer_key.append({
            "transaction_id": transaction_id,
            "exception_type": "refund_chargeback",
            "reason": f"Ledger status is 'refunded' ({refund_type}) - bank credit legitimately differs from settlement amount, not a data error"
        })

    return ledger, settlement, bank, answer_key


os.makedirs(DATA_DIR, exist_ok=True)

# Build clean data, then break it - all in one pass, every time.
ledger, settlement, bank = generate_clean_data()
ledger, settlement, bank, answer_key = inject_mismatches(ledger, settlement, bank)

# Add the 8 refund cases as a distinct 5th scenario (Task #302b)
refund_rng = random.Random(99)
ledger, settlement, bank, answer_key = add_refund_cases(ledger, settlement, bank, answer_key, refund_rng)

write_csv("ledger.csv", ledger,
          ["transaction_id", "ledger_entry_id", "order_id", "amount", "date", "status"])

write_csv("settlement.csv", settlement,
          ["transaction_id", "settlement_amount", "fee", "tax", "settlement_date", "expected_settlement_date", "status"])

write_csv("bank.csv", bank,
          ["transaction_id", "payment_attempt_id", "credited_amount", "credit_date", "bank_ref"])

write_csv("answer_key.csv", answer_key,
          ["transaction_id", "exception_type", "reason"])

# account_snapshot.csv - supports the Cash Forecast Agent (needs a starting point to forecast from)
# as_of set to 2026-08-01 (rather than the dataset's end date) so pending
# items spread naturally across the 7/14/30-day horizons instead of all
# landing in the same bucket - makes the demo forecast actually look
# different at each horizon.
write_csv("account_snapshot.csv",
          [{"as_of_timestamp": "2026-08-01T00:00:00", "opening_bank_balance": 250000.00}],
          ["as_of_timestamp", "opening_bank_balance"])

_per_type = max(1, round(NUM_RECORDS * 0.30 / 4))
_exception_count = _per_type * 4
print(f"Done. Generated {NUM_RECORDS} clean records, then injected {_exception_count} exceptions (30%):")
print(f"  - Amount mismatch: {_per_type}")
print(f"  - Missing record:  {_per_type}")
print(f"  - Duplicate entry: {_per_type}")
print(f"  - Date mismatch:   {_per_type}")
print(f"Plus {NUM_REFUNDS} separate refund cases (TXN{10000+NUM_RECORDS+1}-TXN{10000+NUM_RECORDS+NUM_REFUNDS}) testing false-positive avoidance.")
print("\nFiles written: ledger.csv, settlement.csv, bank.csv, answer_key.csv, account_snapshot.csv")
print("This script is idempotent - safe to run any number of times, always gives the same correct result.")