# reconciliation_agent.py (v2 - Task #308 audit fixes)
#
# Fixes applied from the Phase 3 code audit:
#   1. Amount check now actually uses ledger.amount - fee - tax (was
#      comparing settlement_amount to bank amount directly, which never
#      caught a corrupted ledger/fee/tax calculation)
#   2. Duplicate detection now checks ledger_entry_id reuse across
#      DIFFERENT transaction_ids too (was only catching same transaction_id
#      + same ledger_entry_id), plus bank duplicates via payment_attempt_id
#   3. Repeated settlement_id/bank rows no longer crash the agent - they're
#      caught and flagged as their own exception instead
#
# HOW TO RUN THIS DIRECTLY (for testing):
#   python3 agents/reconciliation_agent.py

import pandas as pd
from datetime import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from audit_log import log_decision

AMOUNT_TOLERANCE = 1.00
MIN_DATE_GAP = 0
MAX_DATE_GAP = 2
FEE_PERCENT = 0.02   # must match the rate used in inject_mismatches.py
TAX_PERCENT = 0.18

PRECEDENCE = ["missing_record", "duplicate_entry", "refund_chargeback", "amount_mismatch", "date_mismatch"]


def _parse_date(date_str):
    if pd.isna(date_str) or date_str is None:
        return None
    try:
        return datetime.strptime(str(date_str), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _safe_float(val):
    """Returns None instead of crashing on NaN/missing/non-numeric values."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def reconcile(data_dir="data", run_id=None, log_audit=True):
    ledger = pd.read_csv(f"{data_dir}/ledger.csv")
    settlement = pd.read_csv(f"{data_dir}/settlement.csv")
    bank = pd.read_csv(f"{data_dir}/bank.csv")

    all_ids = set(ledger["transaction_id"]) | set(settlement["transaction_id"]) | set(bank["transaction_id"])

    # --- Duplicate detection (Fix #2: correct scope + correct keys) ---

    # Ledger duplicates: a repeated ledger_entry_id is a duplicate EVEN IF
    # it shows up under a different transaction_id (that's a worse bug, not
    # a lesser one - the same real-world event got recorded as two entries).
    ledger_entry_counts = ledger.groupby("ledger_entry_id")["transaction_id"].apply(list)
    duplicate_ledger_entry_ids = set(ledger_entry_counts[ledger_entry_counts.apply(len) > 1].index)
    duplicate_txn_ids_via_ledger = set()
    for entry_id in duplicate_ledger_entry_ids:
        for txn_id in ledger_entry_counts[entry_id]:
            duplicate_txn_ids_via_ledger.add(txn_id)

    # A repeated transaction_id in the ledger is ALSO always suspicious,
    # even if (unexpectedly) the ledger_entry_id differs - flag it too,
    # since transaction_id is supposed to be unique per real transaction.
    ledger_txn_counts = ledger.groupby("transaction_id").size()
    duplicate_txn_ids_via_ledger |= set(ledger_txn_counts[ledger_txn_counts > 1].index)

    # Settlement has no stable row-level ID in this schema (documented
    # limitation - see schema.md). At minimum, a repeated transaction_id
    # in settlement is treated as an ambiguous duplicate/data-quality issue.
    settlement_txn_counts = settlement.groupby("transaction_id").size()
    duplicate_settlement_ids = set(settlement_txn_counts[settlement_txn_counts > 1].index)

    # Bank duplicates: via payment_attempt_id, per schema.md's intent.
    bank_attempt_counts = bank.groupby("payment_attempt_id")["transaction_id"].apply(list)
    duplicate_bank_ids = set()
    for attempt_id, txn_ids in bank_attempt_counts[bank_attempt_counts.apply(len) > 1].items():
        for txn_id in txn_ids:
            duplicate_bank_ids.add(txn_id)
    duplicate_bank_txn_counts = bank.groupby("transaction_id").size()
    duplicate_bank_ids |= set(duplicate_bank_txn_counts[duplicate_bank_txn_counts > 1].index)

    all_duplicate_ids = duplicate_txn_ids_via_ledger | duplicate_settlement_ids | duplicate_bank_ids

    # --- Fix #3: never let a repeated key crash a .loc[] lookup ---
    # For any transaction_id that appears more than once in ledger, settlement,
    # or bank, we take the first row for VALUE lookups (amount/date), but the
    # transaction has already been flagged as duplicate_entry above regardless -
    # so no data is silently trusted just because we picked "a" row to read.
    ledger_by_id = ledger.drop_duplicates(subset="transaction_id", keep="first").set_index("transaction_id")
    settlement_by_id = settlement.drop_duplicates(subset="transaction_id", keep="first").set_index("transaction_id")
    bank_by_id = bank.drop_duplicates(subset="transaction_id", keep="first").set_index("transaction_id")

    results = []

    for txn_id in sorted(all_ids):
        presence_ledger = txn_id in ledger_by_id.index
        presence_settlement = txn_id in settlement_by_id.index
        presence_bank = txn_id in bank_by_id.index

        ledger_amount = fee = tax = expected_amount = actual_amount = variance = None
        date_gap_days = None
        expected_settlement_date_val = None
        credit_date_val = None
        data_quality_issue = False

        if presence_ledger:
            ledger_amount = _safe_float(ledger_by_id.loc[txn_id]["amount"])

        if presence_settlement:
            settlement_row = settlement_by_id.loc[txn_id]
            fee = _safe_float(settlement_row["fee"])
            tax = _safe_float(settlement_row["tax"])
            expected_settlement_date_val = settlement_row["expected_settlement_date"]
            reported_settlement_amount = _safe_float(settlement_row["settlement_amount"])

            # --- Fix #1: actually compute ledger.amount - fee - tax ---
            if ledger_amount is not None and fee is not None and tax is not None:
                expected_amount = round(ledger_amount - fee - tax, 2)
            else:
                # Required fields missing - we CANNOT confirm a match.
                # Conservative rule: never let missing data pass as "matched".
                data_quality_issue = True
                expected_amount = reported_settlement_amount  # fall back for reference only

        if presence_bank:
            bank_row = bank_by_id.loc[txn_id]
            actual_amount = _safe_float(bank_row["credited_amount"])
            credit_date_val = bank_row["credit_date"]

        is_refund = False
        if presence_ledger:
            ledger_status = ledger_by_id.loc[txn_id]["status"]
            if ledger_status == "refunded":
                is_refund = True

        amount_mismatch = False
        if data_quality_issue:
            amount_mismatch = True  # can't verify -> treat conservatively as a mismatch
        elif expected_amount is not None and actual_amount is not None:
            variance = round(expected_amount - actual_amount, 2)
            if abs(variance) > AMOUNT_TOLERANCE and not is_refund:
                amount_mismatch = True

        date_mismatch = False
        if presence_settlement and presence_bank:
            settlement_date = _parse_date(settlement_by_id.loc[txn_id]["settlement_date"])
            credit_date = _parse_date(credit_date_val)
            if settlement_date and credit_date:
                date_gap_days = (credit_date - settlement_date).days
                if not (MIN_DATE_GAP <= date_gap_days <= MAX_DATE_GAP):
                    date_mismatch = True
            else:
                date_mismatch = True  # unparseable date is itself a problem, not "normal"

        missing_record = not (presence_ledger and presence_settlement and presence_bank)
        duplicate_entry = txn_id in all_duplicate_ids

        exception_codes = []
        if missing_record:
            exception_codes.append("missing_record")
        if duplicate_entry:
            exception_codes.append("duplicate_entry")
        if is_refund:
            exception_codes.append("refund_chargeback")
        if amount_mismatch:
            exception_codes.append("amount_mismatch")
        if date_mismatch:
            exception_codes.append("date_mismatch")

        primary_exception_code = None
        for code in PRECEDENCE:
            if code in exception_codes:
                primary_exception_code = code
                break

        reconciliation_status = "matched" if not exception_codes else "exception"

        if log_audit:
            if reconciliation_status == "matched":
                reason = f"Ledger/settlement/bank amounts agree within Rs.{AMOUNT_TOLERANCE} tolerance; date gap {date_gap_days} day(s), within 0-{MAX_DATE_GAP} day rule."
            else:
                reasons = []
                if missing_record:
                    reasons.append(f"absent from {'ledger' if not presence_ledger else ''}{'settlement' if not presence_settlement else ''}{'bank' if not presence_bank else ''}".strip())
                if duplicate_entry:
                    reasons.append("duplicate ledger_entry_id or payment_attempt_id detected")
                if is_refund:
                    reasons.append("ledger status is 'refunded'")
                if amount_mismatch:
                    reasons.append(f"variance {variance} exceeds Rs.{AMOUNT_TOLERANCE} tolerance" if not data_quality_issue else "required amount/fee/tax fields missing, cannot verify")
                if date_mismatch:
                    reasons.append(f"date gap {date_gap_days} outside 0-{MAX_DATE_GAP} day rule")
                reason = "; ".join(reasons) if reasons else "unspecified"

            log_decision(
                agent="reconciliation_agent", transaction_id=txn_id,
                decision=primary_exception_code or "matched", reasoning=reason,
                run_id=run_id, extra={"exception_codes": exception_codes}
            )

        results.append({
            "transaction_id": txn_id,
            "presence_ledger": presence_ledger,
            "presence_settlement": presence_settlement,
            "presence_bank": presence_bank,
            "ledger_amount": ledger_amount,
            "fee": fee,
            "tax": tax,
            "expected_amount": expected_amount,
            "actual_amount": actual_amount,
            "variance": variance,
            "date_gap_days": date_gap_days,
            "expected_settlement_date": expected_settlement_date_val,
            "credit_date": credit_date_val,
            "data_quality_issue": data_quality_issue,
            "exception_codes": exception_codes,
            "primary_exception_code": primary_exception_code,
            "reconciliation_status": reconciliation_status
        })

    return results


def summarize(results):
    total = len(results)
    matched = sum(1 for r in results if r["reconciliation_status"] == "matched")
    exceptions = total - matched
    match_rate = round((matched / total) * 100, 2) if total else 0

    by_type = {}
    for r in results:
        if r["primary_exception_code"]:
            by_type[r["primary_exception_code"]] = by_type.get(r["primary_exception_code"], 0) + 1

    return {
        "total_transactions": total,
        "matched": matched,
        "exceptions": exceptions,
        "match_rate_percent": match_rate,
        "exceptions_by_primary_type": by_type
    }


def build_flagged_exceptions_payload(results):
    flagged = [
        {
            "transaction_id": r["transaction_id"],
            "exception_codes": r["exception_codes"],
            "primary_exception_code": r["primary_exception_code"],
            "expected_amount": r["expected_amount"],
            "actual_amount": r["actual_amount"],
            "variance": r["variance"],
            "date_gap_days": r["date_gap_days"]
        }
        for r in results if r["reconciliation_status"] == "exception"
    ]
    matched_records = [
        {"transaction_id": r["transaction_id"], "amount": r["expected_amount"]}
        for r in results if r["reconciliation_status"] == "matched"
    ]
    return {"flagged_exceptions": flagged, "matched_records": matched_records}


if __name__ == "__main__":
    results = reconcile("data")
    summary = summarize(results)

    print("=== RECONCILIATION SUMMARY ===")
    for k, v in summary.items():
        print(f"{k}: {v}")

    answer_key = pd.read_csv("data/answer_key.csv")
    expected = dict(zip(answer_key["transaction_id"], answer_key["exception_type"]))

    correct = sum(1 for txn_id, t in expected.items()
                  for r in results if r["transaction_id"] == txn_id and t in r["exception_codes"])

    print(f"\n=== ACCURACY CHECK vs answer_key.csv ===")
    print(f"Total known exceptions: {len(expected)}")
    print(f"Correctly detected: {correct}")

    false_positives = [r["transaction_id"] for r in results
                        if r["reconciliation_status"] == "exception" and r["transaction_id"] not in expected]
    print(f"False positives (flagged but not in answer_key): {len(false_positives)}")
    if false_positives:
        print(f"  {false_positives}")

    data_quality_flags = [r["transaction_id"] for r in results if r["data_quality_issue"]]
    print(f"Data quality issues (missing required fields): {len(data_quality_flags)}")