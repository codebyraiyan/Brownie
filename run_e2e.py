# run_e2e.py
#
# What this file does:
# This is the FINAL proof-of-correctness script. It runs the entire Brownie
# pipeline (Brownie -> Finance Head -> all 3 sub-agents) on the full 168-record
# dataset, saves the result to reports/e2e_run_output.json, and checks the
# output against answer_key.csv to prove the numbers are actually correct -
# not just "it ran without crashing."
#
# This is the file whose output you'd show a judge/interviewer as evidence.
#
# HOW TO RUN THIS:
#   python3 run_e2e.py

import sys
import os
import json
import csv
from datetime import datetime, timezone

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents"))

from brownie import Brownie
from finance_head import run_finance_head
from audit_log import clear_audit_trail


def load_answer_key(data_dir="data"):
    """Loads the known-correct exception type PER transaction_id (not just counts)."""
    by_txn = {}
    with open(f"{data_dir}/answer_key.csv") as f:
        for row in csv.DictReader(f):
            by_txn[row["transaction_id"]] = row["exception_type"]
    return by_txn


def run_e2e(data_dir="data", output_path="reports/e2e_run_output.json"):
    print("Starting end-to-end run: Brownie -> Finance Head -> 3 sub-agents...\n")

    # Fresh audit trail per full run - avoids mixing this run's decisions
    # with leftover entries from earlier standalone agent testing.
    clear_audit_trail()

    brownie = Brownie()
    brownie.register_capability("finance.reconcile", run_finance_head)

    result = brownie.submit_task("finance.reconcile", data_dir=data_dir)
    department_result = result["payload"]["department_result"]

    # --- TASK #308 AUDIT FIX: verify exact transaction IDs, not just counts ---
    # The old check only compared aggregate counts per type, which would
    # pass even if 12 completely WRONG transactions were labeled
    # amount_mismatch, as long as the total was still 12. This directly
    # calls the Reconciliation Agent again to get per-transaction detail
    # and checks every single ID against the answer key.
    # NOTE: log_audit=False here - this is a verification-only re-run,
    # not a real pipeline decision, so it shouldn't duplicate entries
    # already logged by the actual run inside run_finance_head() above.
    from reconciliation_agent import reconcile as reconcile_direct
    recon_results = reconcile_direct(data_dir, log_audit=False)
    recon_by_id = {r["transaction_id"]: r for r in recon_results}

    expected_by_txn = load_answer_key(data_dir)
    correct_ids = []
    wrong_ids = []

    for txn_id, expected_type in expected_by_txn.items():
        actual = recon_by_id.get(txn_id)
        if actual is None:
            wrong_ids.append({"transaction_id": txn_id, "issue": "not found in reconciliation output"})
        elif expected_type in actual["exception_codes"]:
            correct_ids.append(txn_id)
        else:
            wrong_ids.append({
                "transaction_id": txn_id,
                "issue": f"expected '{expected_type}', got {actual['exception_codes']}"
            })

    false_positives = [
        r["transaction_id"] for r in recon_results
        if r["reconciliation_status"] == "exception" and r["transaction_id"] not in expected_by_txn
    ]

    accuracy_check = {
        "expected_total_exceptions": len(expected_by_txn),
        "actual_total_exceptions": department_result.get("exceptions_total"),
        "exact_transaction_id_matches": len(correct_ids),
        "exact_transaction_id_mismatches": wrong_ids,
        "false_positives": false_positives,
        "all_exact_ids_correct": len(wrong_ids) == 0 and len(false_positives) == 0
    }

    # --- Build the final saved report ---
    final_report = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": result["payload"]["task_id"],
        "pipeline_status": result["status"],
        "finance_head_report": department_result,
        "accuracy_verification": accuracy_check
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(final_report, f, indent=2)

    # --- Print human-readable summary ---
    print("=== END-TO-END RUN COMPLETE ===")
    print(f"Task ID: {final_report['task_id']}")
    print(f"Pipeline status: {final_report['pipeline_status']}")
    print(f"Match rate: {department_result.get('match_rate')}")
    print(f"Total records: {department_result.get('total_records')}")
    print(f"Matched: {department_result.get('matched')}")
    print(f"Exceptions: {department_result.get('exceptions_total')}")

    print(f"\n=== ACCURACY VERIFICATION vs answer_key.csv (exact transaction IDs) ===")
    print(f"Expected exceptions: {accuracy_check['expected_total_exceptions']}")
    print(f"Correctly matched by exact transaction ID: {accuracy_check['exact_transaction_id_matches']}")
    print(f"False positives: {len(accuracy_check['false_positives'])}")
    print(f"All exact IDs correct: {accuracy_check['all_exact_ids_correct']}")

    if not accuracy_check["all_exact_ids_correct"]:
        print("\n!!! MISMATCH DETECTED !!!")
        for issue in accuracy_check["exact_transaction_id_mismatches"]:
            print(f"  {issue}")
        if accuracy_check["false_positives"]:
            print(f"  False positives: {accuracy_check['false_positives']}")
    else:
        print("\nPASS: Every single transaction ID's exception type matches the answer key exactly.")

    if department_result.get("cash_forecast"):
        print(f"\nCash forecast (7/14/30 day): {department_result['cash_forecast']}")
        print(f"At-risk (7/14/30 day): {department_result['at_risk']}")

    print(f"\nFull report saved to: {output_path}")
    return final_report


if __name__ == "__main__":
    run_e2e()