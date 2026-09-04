# cash_forecast_agent.py
#
# What this file does:
# Takes the cash_items[] from the Exception Investigator and computes an
# actual cash POSITION (not just a list of incoming amounts), per
# docs/cash-forecast-agent.md - including the Task #208 correction that
# fixed a double-counting bug.
#
# THE KEY RULE: opening_balance already includes every "bank_confirmed"
# amount. We NEVER add bank_confirmed amounts again - only "expected_inflow"
# (money not yet arrived, but a safe bet) gets added to the forecast.
# "at_risk" money is reported separately, never mixed into the confident
# forecast number.
#
# HOW TO RUN THIS DIRECTLY (for testing):
#   python3 agents/cash_forecast_agent.py

import sys
import os
from datetime import date, datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from reconciliation_agent import reconcile, build_flagged_exceptions_payload
from audit_log import log_decision
# NOTE: exception_investigator (and LangGraph) is imported lazily inside
# __main__ below, not here - this keeps compute_forecast() testable on its
# own even in environments without LangGraph installed.

import csv

HORIZONS = [7, 14, 30]


def _parse_date(date_str):
    if date_str is None:
        return None
    try:
        return datetime.strptime(str(date_str), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def load_account_snapshot(data_dir="data"):
    with open(f"{data_dir}/account_snapshot.csv") as f:
        row = next(csv.DictReader(f))
    as_of = datetime.fromisoformat(row["as_of_timestamp"]).date()
    opening_balance = float(row["opening_bank_balance"])
    return as_of, opening_balance


def determine_final_cash_treatment(item: dict, as_of: date) -> str:
    """
    TASK #308 AUDIT FIX: this is the ACTUAL final decision on cash_treatment,
    now correctly based on the real credit_date vs as_of - not just a label
    assigned without knowing the forecast date. This fixes both:
      - a matched/resolved transaction credited AFTER as_of being wrongly
        labeled bank_confirmed (and disappearing from the forecast)
      - a transaction already credited BEFORE as_of being wrongly labeled
        expected_inflow (and double-counted on top of opening_balance)
    """
    provisional = item["provisional_cash_status"]

    if provisional == "excluded":
        return "excluded"
    if provisional == "at_risk":
        return "at_risk"

    # provisional == "likely_confirmed_or_expected" - the real decision
    # depends on whether the bank credit already happened on or before as_of.
    credit_date = _parse_date(item.get("credit_date"))
    if credit_date is not None:
        return "bank_confirmed" if credit_date <= as_of else "expected_inflow"

    # No real credit_date at all (e.g. missing_record cases never reached
    # the bank) - can't claim it's confirmed OR a safe expected inflow.
    return "at_risk"


def compute_forecast(cash_items: list, as_of: date, opening_balance: float, run_id=None, log_audit=True) -> dict:
    """
    Implements the corrected formula from cash-forecast-agent.md (Task #208),
    now with the Task #308 date-aware cash_treatment fix applied first.

    forecast[horizon] = opening_balance
                       + sum(amount where cash_treatment == "expected_inflow"
                             and 0 <= days_out <= horizon)

    at_risk[horizon]  = sum(amount where cash_treatment == "at_risk"
                             and expected_settlement_date falls within horizon)
                       + overdue expected_inflow amounts (see below)

    "bank_confirmed" is NEVER added again - it's already inside opening_balance.
    "excluded" never appears in either total. Items with unparseable or
    missing dates are tracked separately, never silently dropped.
    """
    forecast = {f"{h}_day": opening_balance for h in HORIZONS}
    at_risk = {f"{h}_day": 0.0 for h in HORIZONS}

    unscheduled_at_risk = 0.0
    unscheduled_expected_inflow = 0.0

    for item in cash_items:
        treatment = determine_final_cash_treatment(item, as_of)

        if log_audit:
            credit_date_str = item.get("credit_date")
            if treatment == "bank_confirmed":
                reason = f"Bank credit on {credit_date_str} is on/before as_of {as_of.isoformat()} - already reflected in opening balance."
            elif treatment == "expected_inflow":
                reason = f"Bank credit expected {credit_date_str or item.get('expected_settlement_date')}, after as_of {as_of.isoformat()} - counted as future inflow."
            elif treatment == "excluded":
                reason = "Non-cash correction (e.g. approved duplicate removal) - no cash impact."
            else:
                reason = "No confirmed bank credit date available - treated conservatively as at-risk."

            log_decision(
                agent="cash_forecast_agent", transaction_id=item["transaction_id"],
                decision=treatment, reasoning=reason, run_id=run_id
            )

        amount = item.get("amount")

        if amount is None or treatment in ("bank_confirmed", "excluded"):
            continue

        settlement_date = _parse_date(item.get("expected_settlement_date")) or _parse_date(item.get("credit_date"))

        if settlement_date is None:
            # TASK #308 AUDIT FIX: never silently drop this - report it
            if treatment == "at_risk":
                unscheduled_at_risk += amount
            elif treatment == "expected_inflow":
                unscheduled_expected_inflow += amount
            continue

        days_out = (settlement_date - as_of).days

        if treatment == "expected_inflow" and days_out < 0:
            # TASK #308 AUDIT FIX: money that was EXPECTED to have already
            # arrived by now, but hasn't been bank-confirmed, is overdue -
            # that's a risk signal, not a confident forecast contribution.
            for h in HORIZONS:
                at_risk[f"{h}_day"] = round(at_risk[f"{h}_day"] + amount, 2)
            continue

        for h in HORIZONS:
            if 0 <= days_out <= h or (treatment == "at_risk" and days_out <= h):
                key = f"{h}_day"
                if treatment == "expected_inflow":
                    forecast[key] = round(forecast[key] + amount, 2)
                elif treatment == "at_risk":
                    at_risk[key] = round(at_risk[key] + amount, 2)

    return {
        "as_of": as_of.isoformat(),
        "opening_balance": round(opening_balance, 2),
        "forecast": forecast,
        "at_risk": at_risk,
        "unscheduled_at_risk": round(unscheduled_at_risk, 2),
        "unscheduled_expected_inflow": round(unscheduled_expected_inflow, 2)
    }


# --- Self-test: run the full pipeline end to end ---
if __name__ == "__main__":
    from exception_investigator import investigate_all, build_cash_items_payload

    print("Running full pipeline: Reconciliation -> Investigation -> Forecast...\n")

    recon_results = reconcile("data")
    payload = build_flagged_exceptions_payload(recon_results)
    flagged = payload["flagged_exceptions"]

    investigation_results = investigate_all(flagged, auto_approve_for_testing=True)
    cash_payload = build_cash_items_payload(investigation_results, recon_results)

    as_of, opening_balance = load_account_snapshot("data")
    result = compute_forecast(cash_payload["cash_items"], as_of, opening_balance)

    print("=== CASH FORECAST ===")
    for k, v in result.items():
        print(f"{k}: {v}")

    # Sanity check: forecast should never be LESS than opening_balance
    # (expected_inflow amounts should only ever add, never subtract)
    for h in HORIZONS:
        key = f"{h}_day"
        assert result["forecast"][key] >= result["opening_balance"], \
            f"BUG: {key} forecast is below opening balance!"
    print("\nSanity check passed: forecast never drops below opening balance.")