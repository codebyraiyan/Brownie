# finance_head.py
#
# What this file does:
# This is the "manager" for the 3 Finance sub-agents. It runs them in the
# correct order (Reconciliation -> Investigation -> Forecast), passes data
# between them, and - importantly - handles what happens if any ONE of
# them fails, per docs/finance-head.md (including the Task #208 correction
# for a full Reconciliation Agent crash).
#
# HOW TO RUN THIS DIRECTLY (for testing):
#   python3 agents/finance_head.py
# This runs the whole pipeline and prints the final report that would be
# sent back to Brownie.

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from reconciliation_agent import reconcile, summarize, build_flagged_exceptions_payload
from exception_investigator import investigate_all, build_cash_items_payload
from cash_forecast_agent import compute_forecast, load_account_snapshot
from envelope import create_envelope, create_error_envelope, new_task_id, new_run_id


def run_finance_head(data_dir="data", task_id=None, run_id=None,
                      simulate_failure=None, auto_approve=True):
    """
    Runs the full Finance Head pipeline.

    simulate_failure: for TESTING ONLY - pass "reconciliation", "investigator",
                       or "forecast" to deliberately simulate that stage
                       crashing, so we can verify failure handling actually
                       works (not just the happy path). Leave as None for
                       normal operation.
    """
    if task_id is None:
        task_id = new_task_id()
    if run_id is None:
        run_id = new_run_id()

    # --- STAGE 1: Reconciliation Agent ---
    try:
        if simulate_failure == "reconciliation":
            raise RuntimeError("Simulated crash: could not read bank.csv")

        recon_results = reconcile(data_dir, run_id=run_id)
        recon_summary = summarize(recon_results)

    except Exception as e:
        # Task #208 correction: if Reconciliation Agent fails completely,
        # there is NO valid input for the other 2 agents. Block them
        # entirely and return a snapshot_only report - never pretend to
        # forecast on top of a failed reconciliation.
        #
        # TASK #308 AUDIT FIX: guard the snapshot load independently - if
        # BOTH reconciliation input AND account_snapshot.csv are broken,
        # this "graceful" error path must not itself crash.
        report = {
            "reconciliation_run_status": "failed",
            "blocked_by": "reconciliation_agent",
            "run_id": run_id,
            "error_code": "RECONCILIATION_FAILED",
            "error_message": "Reconciliation could not be completed. See server logs for details."
        }
        print(f"[Finance Head] Reconciliation Agent failed: {e}")  # detailed log, not exposed to caller

        try:
            as_of, opening_balance = load_account_snapshot(data_dir)
            report["snapshot_only"] = {"as_of": as_of.isoformat(), "opening_balance": opening_balance}
        except Exception as snapshot_error:
            print(f"[Finance Head] Account snapshot also unavailable: {snapshot_error}")
            report["snapshot_only"] = None
            report["error_message"] += " Account snapshot also unavailable."

        return create_envelope(
            from_agent="finance_head", to_agent="brownie",
            payload=report, task_id=task_id, run_id=run_id, status="error"
        )

    # --- STAGE 2: Exception Investigator ---
    incomplete_data = False
    investigation_results = []
    try:
        if simulate_failure == "investigator":
            raise RuntimeError("Simulated crash: Exception Investigator timed out")

        flagged_payload = build_flagged_exceptions_payload(recon_results)
        investigation_results = investigate_all(
            flagged_payload["flagged_exceptions"],
            auto_approve_for_testing=auto_approve,
            run_id=run_id
        )

    except Exception as e:
        # Partial failure - matched records are still valid, forward them
        # onward, but flag the report as incomplete per finance-head.md
        incomplete_data = True
        print(f"[Finance Head] WARNING: Exception Investigator failed ({e}). "
              f"Proceeding with matched records only, marking incomplete_data=true.")

    # --- STAGE 3: Cash Forecast Agent ---
    forecast_status = "success"
    forecast_result = None
    try:
        if simulate_failure == "forecast":
            raise RuntimeError("Simulated crash: could not read account_snapshot.csv")

        cash_payload = build_cash_items_payload(investigation_results, recon_results)
        as_of, opening_balance = load_account_snapshot(data_dir)
        forecast_result = compute_forecast(cash_payload["cash_items"], as_of, opening_balance, run_id=run_id)

    except Exception as e:
        forecast_status = "failed"
        print(f"[Finance Head] WARNING: Cash Forecast Agent failed ({e}). "
              f"Reporting reconciliation/investigation results without a forecast.")

    # --- Assemble final report ---
    report = {
        "reconciliation_run_status": "success",
        "run_id": run_id,
        "match_rate": f"{recon_summary['match_rate_percent']}%",
        "total_records": recon_summary["total_transactions"],
        "matched": recon_summary["matched"],
        "exceptions_total": recon_summary["exceptions"],
        "exceptions_by_type": recon_summary["exceptions_by_primary_type"],
        "incomplete_data": incomplete_data,
        "forecast_status": forecast_status
    }

    if forecast_result:
        report["cash_forecast"] = forecast_result["forecast"]
        report["at_risk"] = forecast_result["at_risk"]
        report["opening_balance"] = forecast_result["opening_balance"]
        # TASK #308 AUDIT FIX: these were computed by Cash Forecast Agent
        # but silently dropped here - a reviewer would see zero unscheduled
        # risk even when real unresolved exposure existed with no date.
        report["unscheduled_at_risk"] = forecast_result["unscheduled_at_risk"]
        report["unscheduled_expected_inflow"] = forecast_result["unscheduled_expected_inflow"]

    return create_envelope(
        from_agent="finance_head", to_agent="brownie",
        payload=report, task_id=task_id, run_id=run_id, status="success"
    )


# --- Self-test: normal run + all 3 failure scenarios ---
if __name__ == "__main__":
    print("=== NORMAL RUN ===")
    result = run_finance_head("data")
    print(f"Status: {result['status']}")
    for k, v in result["payload"].items():
        print(f"  {k}: {v}")

    for failure_point in ["reconciliation", "investigator", "forecast"]:
        print(f"\n=== SIMULATED FAILURE: {failure_point} ===")
        result = run_finance_head("data", simulate_failure=failure_point)
        print(f"Status: {result['status']}")
        for k, v in result["payload"].items():
            print(f"  {k}: {v}")