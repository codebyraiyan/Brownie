# test_edge_cases.py
#
# What this file does:
# Deliberately builds BROKEN, weird, or malformed data and checks that
# Brownie's Reconciliation Agent handles it gracefully - flags a proper
# exception or data-quality issue - instead of crashing or, worse, silently
# marking bad data as "matched".
#
# This directly answers the Phase 3 audit's core criticism: our first
# 56/56 accuracy result only proved the HAPPY PATH works. This file proves
# the UGLY paths work too.
#
# HOW TO RUN THIS:
#   python3 test_edge_cases.py
# Every test either passes or prints exactly what went wrong.

import sys
import os
import shutil
import tempfile
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents"))
from reconciliation_agent import reconcile

# TASK #406 AUDIT FIX: use tempfile instead of hardcoded /tmp, which
# doesn't exist as a root path on Windows.
TEST_DIR = os.path.join(tempfile.gettempdir(), "brownie_edge_case_tests")
passed = 0
failed = 0


def make_fixture(name, ledger_rows, settlement_rows, bank_rows):
    """Writes a small 3-file dataset to a temp folder for one test case."""
    folder = f"{TEST_DIR}/{name}"
    os.makedirs(folder, exist_ok=True)

    ledger_cols = ["transaction_id", "ledger_entry_id", "order_id", "amount", "date", "status"]
    settlement_cols = ["transaction_id", "settlement_amount", "fee", "tax", "settlement_date", "expected_settlement_date", "status"]
    bank_cols = ["transaction_id", "payment_attempt_id", "credited_amount", "credit_date", "bank_ref"]

    pd.DataFrame(ledger_rows, columns=ledger_cols).to_csv(f"{folder}/ledger.csv", index=False)
    pd.DataFrame(settlement_rows, columns=settlement_cols).to_csv(f"{folder}/settlement.csv", index=False)
    pd.DataFrame(bank_rows, columns=bank_cols).to_csv(f"{folder}/bank.csv", index=False)

    return folder


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} -- {detail}")


def get(results, txn_id):
    return next((r for r in results if r["transaction_id"] == txn_id), None)


print("=== EDGE CASE TEST SUITE ===\n")

# --- TC1: Duplicate ledger_entry_id across DIFFERENT transaction_ids ---
print("TC1: Same ledger_entry_id reused across two different transaction_ids")
folder = make_fixture("tc1",
    ledger_rows=[
        ["TXN_A", "LDG_SHARED", "ORD_A", 500.00, "2026-07-01", "paid"],
        ["TXN_B", "LDG_SHARED", "ORD_B", 700.00, "2026-07-02", "paid"],
    ],
    settlement_rows=[
        ["TXN_A", 489.00, 10.00, 1.00, "2026-07-02", "2026-07-03", "settled"],
        ["TXN_B", 685.00, 14.00, 1.00, "2026-07-03", "2026-07-04", "settled"],
    ],
    bank_rows=[
        ["TXN_A", "ATT_A", 489.00, "2026-07-02", "REF_A"],
        ["TXN_B", "ATT_B", 685.00, "2026-07-03", "REF_B"],
    ])
results = reconcile(folder, log_audit=False)
r_a = get(results, "TXN_A")
r_b = get(results, "TXN_B")
check("TXN_A flagged duplicate", "duplicate_entry" in r_a["exception_codes"])
check("TXN_B flagged duplicate", "duplicate_entry" in r_b["exception_codes"])
# TASK #406 AUDIT FIX: also verify NO spurious extra codes snuck in, and
# that reconciliation_status is actually "exception" - membership alone
# wouldn't catch a bug that also wrongly flags amount_mismatch etc.
check("TXN_A has ONLY duplicate_entry (no spurious extra codes)", r_a["exception_codes"] == ["duplicate_entry"],
      f"got {r_a['exception_codes']}")
check("TXN_A reconciliation_status is 'exception'", r_a["reconciliation_status"] == "exception")

# --- TC2: Repeated settlement transaction_id (the exact crash scenario from the audit) ---
print("\nTC2: Repeated transaction_id in settlement.csv (previously crashed)")
folder = make_fixture("tc2",
    ledger_rows=[["TXN_C", "LDG_C", "ORD_C", 1000.00, "2026-07-01", "paid"]],
    settlement_rows=[
        ["TXN_C", 977.00, 20.00, 3.00, "2026-07-02", "2026-07-03", "settled"],
        ["TXN_C", 977.00, 20.00, 3.00, "2026-07-02", "2026-07-03", "settled"],  # duplicate row
    ],
    bank_rows=[["TXN_C", "ATT_C", 977.00, "2026-07-02", "REF_C"]])
try:
    results = reconcile(folder, log_audit=False)
    check("No crash on duplicate settlement row", True)
    check("TXN_C flagged duplicate", "duplicate_entry" in get(results, "TXN_C")["exception_codes"])
except Exception as e:
    check("No crash on duplicate settlement row", False, f"crashed with: {e}")

# --- TC3: Repeated payment_attempt_id in bank across different transaction_ids ---
print("\nTC3: Same payment_attempt_id reused across two different transaction_ids")
folder = make_fixture("tc3",
    ledger_rows=[
        ["TXN_D", "LDG_D", "ORD_D", 300.00, "2026-07-01", "paid"],
        ["TXN_E", "LDG_E", "ORD_E", 400.00, "2026-07-01", "paid"],
    ],
    settlement_rows=[
        ["TXN_D", 293.00, 6.00, 1.00, "2026-07-02", "2026-07-03", "settled"],
        ["TXN_E", 391.00, 8.00, 1.00, "2026-07-02", "2026-07-03", "settled"],
    ],
    bank_rows=[
        ["TXN_D", "ATT_SHARED", 293.00, "2026-07-02", "REF_D"],
        ["TXN_E", "ATT_SHARED", 391.00, "2026-07-02", "REF_E"],
    ])
results = reconcile(folder, log_audit=False)
check("TXN_D flagged duplicate (shared payment_attempt_id)", "duplicate_entry" in get(results, "TXN_D")["exception_codes"])
check("TXN_E flagged duplicate (shared payment_attempt_id)", "duplicate_entry" in get(results, "TXN_E")["exception_codes"])

# --- TC4: Null/missing amount, fee, tax ---
print("\nTC4: Null ledger amount and null fee/tax")
folder = make_fixture("tc4",
    ledger_rows=[["TXN_F", "LDG_F", "ORD_F", "", "2026-07-01", "paid"]],
    settlement_rows=[["TXN_F", 500.00, "", "", "2026-07-02", "2026-07-03", "settled"]],
    bank_rows=[["TXN_F", "ATT_F", 500.00, "2026-07-02", "REF_F"]])
results = reconcile(folder, log_audit=False)
r = get(results, "TXN_F")
check("Null amount/fee/tax flagged as data_quality_issue", r["data_quality_issue"] is True)
check("Null amount/fee/tax NOT silently matched", r["reconciliation_status"] == "exception",
      f"got status={r['reconciliation_status']}")

# --- TC5: Malformed / unparseable dates ---
print("\nTC5: Malformed date string (not a real date)")
folder = make_fixture("tc5",
    ledger_rows=[["TXN_G", "LDG_G", "ORD_G", 500.00, "2026-07-01", "paid"]],
    settlement_rows=[["TXN_G", 489.00, 10.00, 1.00, "not-a-date", "2026-07-03", "settled"]],
    bank_rows=[["TXN_G", "ATT_G", 489.00, "2026-07-02", "REF_G"]])
results = reconcile(folder, log_audit=False)
r = get(results, "TXN_G")
check("Malformed date treated as date_mismatch, not silently 'normal'",
      "date_mismatch" in r["exception_codes"], f"got exception_codes={r['exception_codes']}")

# --- TC6: Negative date gap (bank credited BEFORE settlement - logically impossible) ---
print("\nTC6: Bank credit date BEFORE settlement date (negative gap)")
folder = make_fixture("tc6",
    ledger_rows=[["TXN_H", "LDG_H", "ORD_H", 500.00, "2026-07-01", "paid"]],
    settlement_rows=[["TXN_H", 489.00, 10.00, 1.00, "2026-07-05", "2026-07-06", "settled"]],
    bank_rows=[["TXN_H", "ATT_H", 489.00, "2026-07-02", "REF_H"]])  # credited BEFORE settlement
results = reconcile(folder, log_audit=False)
r = get(results, "TXN_H")
check("Negative date gap flagged as date_mismatch", "date_mismatch" in r["exception_codes"],
      f"date_gap_days={r['date_gap_days']}, codes={r['exception_codes']}")

# --- TC7: Empty CSVs (each individually) ---
print("\nTC7: All 3 CSVs completely empty (headers only)")
folder = make_fixture("tc7", ledger_rows=[], settlement_rows=[], bank_rows=[])
try:
    results = reconcile(folder, log_audit=False)
    check("Empty dataset returns empty results, no crash", results == [], f"got {len(results)} results")
except Exception as e:
    check("Empty dataset returns empty results, no crash", False, f"crashed with: {e}")

# --- TC8: One CSV empty, others have data (orphan detection) ---
print("\nTC8: Bank has a transaction that appears in NO other file (total orphan)")
folder = make_fixture("tc8", ledger_rows=[], settlement_rows=[],
    bank_rows=[["TXN_ORPHAN", "ATT_ORPHAN", 100.00, "2026-07-02", "REF_ORPHAN"]])
results = reconcile(folder, log_audit=False)
r = get(results, "TXN_ORPHAN")
check("Bank-only orphan transaction is caught (not silently ignored)", r is not None)
check("Orphan flagged as missing_record", r is not None and "missing_record" in r["exception_codes"])

# --- TC9: Exact tolerance boundary ---
print("\nTC9: Variance exactly at the Rs 1.00 tolerance boundary")
folder = make_fixture("tc9_exact",
    ledger_rows=[["TXN_I", "LDG_I", "ORD_I", 1000.00, "2026-07-01", "paid"]],
    settlement_rows=[["TXN_I", 977.00, 20.00, 3.00, "2026-07-02", "2026-07-03", "settled"]],
    bank_rows=[["TXN_I", "ATT_I", 976.00, "2026-07-02", "REF_I"]])  # exactly Rs 1.00 off
results = reconcile(folder, log_audit=False)
r = get(results, "TXN_I")
check("Exactly Rs 1.00 variance is WITHIN tolerance (not flagged)",
      "amount_mismatch" not in r["exception_codes"], f"variance={r['variance']}, codes={r['exception_codes']}")

folder = make_fixture("tc9_over",
    ledger_rows=[["TXN_J", "LDG_J", "ORD_J", 1000.00, "2026-07-01", "paid"]],
    settlement_rows=[["TXN_J", 977.00, 20.00, 3.00, "2026-07-02", "2026-07-03", "settled"]],
    bank_rows=[["TXN_J", "ATT_J", 975.98, "2026-07-02", "REF_J"]])  # Rs 1.02 off - just over tolerance
results = reconcile(folder, log_audit=False)
r = get(results, "TXN_J")
check("Rs 1.02 variance (just over tolerance) IS flagged",
      "amount_mismatch" in r["exception_codes"], f"variance={r['variance']}, codes={r['exception_codes']}")

# --- TC10: The audit's exact ledger-fee-tax bypass reproduction ---
print("\nTC10: Settlement and bank agree with each other, but ledger-fee-tax math disagrees")
folder = make_fixture("tc10",
    ledger_rows=[["TXN_K", "LDG_K", "ORD_K", 1000.00, "2026-07-01", "paid"]],
    settlement_rows=[["TXN_K", 990.00, 20.00, 3.00, "2026-07-02", "2026-07-03", "settled"]],  # should be 977, claims 990
    bank_rows=[["TXN_K", "ATT_K", 990.00, "2026-07-02", "REF_K"]])  # agrees with the WRONG settlement figure
results = reconcile(folder, log_audit=False)
r = get(results, "TXN_K")
check("Ledger-fee-tax inconsistency caught even though settlement/bank agree with each other",
      "amount_mismatch" in r["exception_codes"], f"expected_amount={r['expected_amount']}, codes={r['exception_codes']}")


# --- TC11: Negative amounts (audit flagged: could tolerance check use raw diff, not abs?) ---
print("\nTC11: Negative ledger amount (e.g. a refund recorded as a negative sale)")
folder = make_fixture("tc11",
    ledger_rows=[["TXN_L", "LDG_L", "ORD_L", -500.00, "2026-07-01", "paid"]],
    settlement_rows=[["TXN_L", -490.00, -9.00, -1.00, "2026-07-02", "2026-07-03", "settled"]],
    bank_rows=[["TXN_L", "ATT_L", -400.00, "2026-07-02", "REF_L"]])  # Rs 90 off - should still be caught
results = reconcile(folder, log_audit=False)
r = get(results, "TXN_L")
check("Negative amounts still correctly flagged when variance is large (abs() used, not raw diff)",
      "amount_mismatch" in r["exception_codes"], f"variance={r['variance']}, codes={r['exception_codes']}")

# --- TC12: Completely missing CSV file (not just empty) ---
print("\nTC12: bank.csv file does not exist on disk at all")
folder = f"{TEST_DIR}/tc12"
os.makedirs(folder, exist_ok=True)
pd.DataFrame([["TXN_M", "LDG_M", "ORD_M", 500.00, "2026-07-01", "paid"]],
             columns=["transaction_id", "ledger_entry_id", "order_id", "amount", "date", "status"]).to_csv(f"{folder}/ledger.csv", index=False)
pd.DataFrame([["TXN_M", 489.00, 10.00, 1.00, "2026-07-02", "2026-07-03", "settled"]],
             columns=["transaction_id", "settlement_amount", "fee", "tax", "settlement_date", "expected_settlement_date", "status"]).to_csv(f"{folder}/settlement.csv", index=False)
# bank.csv deliberately NOT created
try:
    results = reconcile(folder, log_audit=False)
    check("Missing CSV file raises a clear, catchable error (not a silent wrong result)", False,
          "expected an exception but reconcile() returned normally")
except FileNotFoundError:
    check("Missing CSV file raises a clear, catchable error (FileNotFoundError)", True)
except Exception as e:
    check("Missing CSV file raises SOME catchable error", True, f"(raised {type(e).__name__}, not FileNotFoundError - acceptable, still catchable by Finance Head's error handling)")

# --- TC13: Floating point precision noise right at the tolerance boundary ---
print("\nTC13: Floating point representation noise near the Rs 1.00 tolerance boundary")
folder = make_fixture("tc13",
    ledger_rows=[["TXN_N", "LDG_N", "ORD_N", 1000.00, "2026-07-01", "paid"]],
    settlement_rows=[["TXN_N", 977.00, 20.00, 3.00, "2026-07-02", "2026-07-03", "settled"]],
    bank_rows=[["TXN_N", "ATT_N", 975.99, "2026-07-02", "REF_N"]])  # 1.01 off - classic float noise territory
results = reconcile(folder, log_audit=False)
r = get(results, "TXN_N")
check("Rs 1.01 variance (float precision boundary) correctly flagged despite rounding noise",
      "amount_mismatch" in r["exception_codes"], f"variance={r['variance']}, codes={r['exception_codes']}")


print(f"\n=== RESULTS: {passed} passed, {failed} failed ===")
shutil.rmtree(TEST_DIR, ignore_errors=True)

if failed > 0:
    sys.exit(1)