# exception_investigator.py
#
# What this file does:
# Takes the flagged_exceptions list from the Reconciliation Agent and
# decides, for each one, WHY it happened (root cause) and whether it's
# safe to auto-fix or needs a human to approve first - per
# docs/exception-investigator.md (including Task #204 and #208 corrections).
#
# HOW HUMAN APPROVAL WORKS HERE:
# We use LangGraph's "interrupt" feature - it's like a checkpoint that
# PAUSES the program and waits for you to type "approve" or "reject" in
# the terminal, then continues exactly where it left off. This is a real,
# working pause - not a simulation - which is why it needs a "checkpointer"
# (a place to remember where it paused).
#
# HOW TO RUN THIS DIRECTLY (for testing):
#   python3 agents/exception_investigator.py
# It will process the flagged exceptions from the Reconciliation Agent and
# ask you to approve/reject a few in your terminal.

import uuid
from typing import TypedDict, Optional, List
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import InMemorySaver

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from reconciliation_agent import reconcile, build_flagged_exceptions_payload
from audit_log import log_decision


# --- Root cause categories and their gating rule (per exception-investigator.md) ---
# "auto"            -> safe to resolve without a human
# "approval"        -> needs human approval before any correction is posted
# "escalate_direct" -> no proposed fix exists at all, straight to escalation

CATEGORY_RULES = {
    "missing_record": {"root_cause": "missing_record", "gate": "approval"},
    "duplicate_entry": {"root_cause": "duplicate_transaction", "gate": "approval"},
    "refund_chargeback": {"root_cause": "refund_chargeback_not_accounted_for", "gate": "approval"},
    "date_mismatch": {"root_cause": "late_payout_or_posting", "gate": "auto"},
    # amount_mismatch is special-cased below: we try to explain it via fee
    # recalculation first; only if that fails does it become a genuine anomaly.
}


class InvestigationState(TypedDict):
    exception: dict
    root_cause: str
    gate: str
    proposed_action: str
    investigation_status: str
    provisional_cash_status: str


def classify_exception(exception: dict) -> dict:
    """
    Looks at the Reconciliation Agent's primary_exception_code and decides
    the root cause + whether it's auto-resolved, approval-gated, or
    escalated directly.

    TASK #308 AUDIT FIX: amount_mismatch no longer gets auto-classified as
    "fee_tax_miscalculation" via an arbitrary variance threshold. The
    investigator does not have a versioned fee-rule table to verify this
    with certainty (a known, disclosed limitation - see cash-forecast-agent.md),
    so guessing based on a percentage was unsupported and unsafe. Every
    amount_mismatch is now honestly escalated as a genuine anomaly unless a
    real fee-rule table is built in a future phase.
    """
    code = exception["primary_exception_code"]

    if code == "amount_mismatch":
        return {"root_cause": "genuine_unresolved_anomaly", "gate": "escalate_direct"}

    if code in CATEGORY_RULES:
        return CATEGORY_RULES[code]

    return {"root_cause": "genuine_unresolved_anomaly", "gate": "escalate_direct"}


def build_proposed_action(exception: dict, root_cause: str) -> str:
    """Human-readable description of what the agent WOULD do, for approval review."""
    txn_id = exception["transaction_id"]
    actions = {
        "missing_record": f"Flag {txn_id} for manual chase - confirm whether funds are in transit or lost",
        "duplicate_transaction": f"Remove duplicate ledger entry for {txn_id}",
        "refund_chargeback_not_accounted_for": f"Record {txn_id} as refunded, adjust expected cash to actual bank amount",
        "late_payout_or_posting": f"No action needed for {txn_id} - payout delay, expected to settle",
        "fee_tax_miscalculation": f"Auto-correct expected amount for {txn_id} based on recalculated fee/tax",
        "genuine_unresolved_anomaly": f"No automated explanation found for {txn_id} - requires manual investigation",
    }
    return actions.get(root_cause, f"Review {txn_id} manually")


def get_provisional_cash_status(root_cause: str, investigation_status: str) -> str:
    """
    TASK #308 AUDIT FIX: this used to make the FINAL cash_treatment decision
    (bank_confirmed/expected_inflow/at_risk/excluded), but that was wrong -
    it labeled things "bank_confirmed" or "expected_inflow" without ever
    checking the actual credit_date against the forecast's as_of date. That
    caused real double-counting and under-counting bugs.

    Now this only returns a PROVISIONAL status. The Cash Forecast Agent
    makes the final cash_treatment call using the real credit_date vs as_of
    (see cash_forecast_agent.py's determine_final_cash_treatment()).
    """
    if investigation_status == "auto_resolved":
        return "likely_confirmed_or_expected"   # resolved by root cause, date decides bank_confirmed vs expected_inflow
    if investigation_status == "approved":
        if root_cause == "refund_chargeback_not_accounted_for":
            return "likely_confirmed_or_expected"
        if root_cause == "duplicate_transaction":
            return "excluded"   # bookkeeping fix, no cash impact regardless of date
        return "at_risk"        # e.g. missing_record approved as genuinely missing - no bank record exists at all
    return "at_risk"


# --- LangGraph nodes ---

def classify_node(state: InvestigationState) -> InvestigationState:
    result = classify_exception(state["exception"])
    root_cause = result["root_cause"]
    gate = result["gate"]
    proposed_action = build_proposed_action(state["exception"], root_cause)
    return {**state, "root_cause": root_cause, "gate": gate, "proposed_action": proposed_action}


def auto_resolve_node(state: InvestigationState) -> InvestigationState:
    status = "auto_resolved"
    return {**state, "investigation_status": status,
            "provisional_cash_status": get_provisional_cash_status(state["root_cause"], status)}


def escalate_direct_node(state: InvestigationState) -> InvestigationState:
    status = "escalated"
    return {**state, "investigation_status": status,
            "provisional_cash_status": get_provisional_cash_status(state["root_cause"], status)}


def human_approval_node(state: InvestigationState) -> InvestigationState:
    # This PAUSES execution here until a human responds via Command(resume=...)
    decision = interrupt({
        "transaction_id": state["exception"]["transaction_id"],
        "root_cause": state["root_cause"],
        "proposed_action": state["proposed_action"],
        "question": "Type 'approve' or 'reject':"
    })

    if str(decision).strip().lower() == "approve":
        status = "approved"
    else:
        # Rejection path per Task #208 correction - default to
        # escalated_for_review (safer default than silently retrying)
        status = "escalated_for_review"

    return {**state, "investigation_status": status,
            "provisional_cash_status": get_provisional_cash_status(state["root_cause"], status)}


def route_after_classify(state: InvestigationState) -> str:
    return {"auto": "auto_resolve", "approval": "human_approval",
            "escalate_direct": "escalate_direct"}[state["gate"]]


def build_graph():
    graph = StateGraph(InvestigationState)
    graph.add_node("classify", classify_node)
    graph.add_node("auto_resolve", auto_resolve_node)
    graph.add_node("escalate_direct", escalate_direct_node)
    graph.add_node("human_approval", human_approval_node)

    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", route_after_classify,
                                 {"auto_resolve": "auto_resolve",
                                  "human_approval": "human_approval",
                                  "escalate_direct": "escalate_direct"})
    graph.add_edge("auto_resolve", END)
    graph.add_edge("escalate_direct", END)
    graph.add_edge("human_approval", END)

    return graph.compile(checkpointer=InMemorySaver())


def investigate_all(flagged_exceptions: List[dict], auto_approve_for_testing=None, run_id=None, log_audit=True):
    """
    Runs every flagged exception through the graph.

    auto_approve_for_testing: if set to True/False, skips the real terminal
    prompt and auto-answers every approval gate the same way - useful for
    automated testing without needing to sit and type responses.
    If None (default), it will actually pause and ask you in the terminal.
    """
    graph = build_graph()
    results = []

    for exception in flagged_exceptions:
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        state = graph.invoke({"exception": exception}, config)

        if "__interrupt__" in state:
            interrupt_info = state["__interrupt__"][0].value

            if auto_approve_for_testing is not None:
                answer = "approve" if auto_approve_for_testing else "reject"
            else:
                print(f"\n--- APPROVAL NEEDED ---")
                print(f"Transaction: {interrupt_info['transaction_id']}")
                print(f"Root cause: {interrupt_info['root_cause']}")
                print(f"Proposed action: {interrupt_info['proposed_action']}")
                # TASK #308 AUDIT FIX: keep asking until we get an exact,
                # unambiguous answer - a typo like "aprove" used to be
                # silently treated as a real rejection, which is unsafe
                # for something that decides a financial record's fate.
                while True:
                    raw_answer = input(f"{interrupt_info['question']} ").strip().lower()
                    if raw_answer in ("approve", "reject"):
                        answer = raw_answer
                        break
                    print(f"  '{raw_answer}' not recognized - please type exactly 'approve' or 'reject'.")

            state = graph.invoke(Command(resume=answer), config)

        if log_audit:
            log_decision(
                agent="exception_investigator", transaction_id=state["exception"]["transaction_id"],
                decision=state["investigation_status"],
                reasoning=f"Root cause: {state['root_cause']}. {state['proposed_action']}",
                run_id=run_id,
                # TASK #406 AUDIT FIX: root_cause now stored as structured
                # data, not just embedded in free text - the report
                # generator should never need to parse reasoning strings.
                extra={"gate": state["gate"], "root_cause": state["root_cause"]}
            )

        results.append({
            "transaction_id": state["exception"]["transaction_id"],
            "root_cause": state["root_cause"],
            "proposed_action": state["proposed_action"],
            "investigation_status": state["investigation_status"],
            "provisional_cash_status": state["provisional_cash_status"]
        })

    return results


def build_cash_items_payload(investigation_results: List[dict], recon_results: List[dict]) -> dict:
    """
    Shapes the final payload to hand off to Cash Forecast Agent, per
    agent-protocol.md v2. Pulls real amounts/dates from the Reconciliation
    Agent's output.

    TASK #308 AUDIT FIX: now includes credit_date (not just
    expected_settlement_date) so the Cash Forecast Agent can correctly
    decide bank_confirmed vs expected_inflow based on the real as_of date,
    instead of trusting a label decided without that context.
    """
    recon_by_id = {r["transaction_id"]: r for r in recon_results}
    cash_items = []

    # Matched (clean) transactions - a real bank record exists, but whether
    # it counts as "already confirmed" depends on its date vs as_of, decided
    # by the Forecast Agent, not here.
    for r in recon_results:
        if r["reconciliation_status"] == "matched":
            cash_items.append({
                "transaction_id": r["transaction_id"],
                "provisional_cash_status": "likely_confirmed_or_expected",
                "amount": r["actual_amount"],
                "credit_date": r["credit_date"],
                "expected_settlement_date": r["expected_settlement_date"],
                "investigation_status": None
            })

    for r in investigation_results:
        recon = recon_by_id.get(r["transaction_id"], {})
        amount = recon.get("actual_amount") if recon.get("actual_amount") is not None else recon.get("expected_amount")
        cash_items.append({
            "transaction_id": r["transaction_id"],
            "provisional_cash_status": r["provisional_cash_status"],
            "amount": amount,
            "credit_date": recon.get("credit_date"),
            "expected_settlement_date": recon.get("expected_settlement_date"),
            "investigation_status": r["investigation_status"]
        })


    return {"cash_items": cash_items}


# --- Self-test ---
if __name__ == "__main__":
    print("Running Reconciliation Agent first to get flagged exceptions...")
    recon_results = reconcile("data")
    payload = build_flagged_exceptions_payload(recon_results)
    flagged = payload["flagged_exceptions"]

    print(f"\n{len(flagged)} exceptions to investigate.\n")
    print("For quick testing, auto-approving all gated exceptions (no manual typing needed).")
    print("To try REAL interactive approval, run with auto_approve_for_testing=None.\n")

    results = investigate_all(flagged, auto_approve_for_testing=True)

    print("\n=== INVESTIGATION RESULTS SUMMARY ===")
    status_counts = {}
    for r in results:
        status_counts[r["investigation_status"]] = status_counts.get(r["investigation_status"], 0) + 1
    for status, count in status_counts.items():
        print(f"{status}: {count}")

    print("\nSample results:")
    for r in results[:5]:
        print(r)

    cash_payload = build_cash_items_payload(results, recon_results)
    print(f"\n{len(cash_payload['cash_items'])} total cash_items built for Cash Forecast Agent.")
    print("Sample cash_items:")
    for item in cash_payload["cash_items"][:3]:
        print(item)