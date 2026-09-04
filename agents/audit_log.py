# audit_log.py
#
# What this file does:
# A shared utility every agent calls to record WHY it made a decision -
# not just WHAT the decision was. This turns Brownie from a black box into
# something explainable: for any transaction, you can look up exactly which
# agent touched it, what it decided, and why.
#
# Log entries are appended to reports/audit_trail.jsonl - one JSON object
# per line (a common format for logs, easy to read line-by-line or load
# into a dataframe later).
#
# HOW TO RUN THIS DIRECTLY (for testing):
#   python3 agents/audit_log.py
# Writes a few sample entries and reads them back to prove it works.

import json
import os
from datetime import datetime, timezone

# TASK #406 AUDIT FIX: anchor to the project root (one level up from
# agents/), not the current working directory. Previously, running any
# agent from inside agents/ (rather than the project root) would silently
# create a SEPARATE agents/reports/ folder instead of writing to the
# canonical reports/ folder - splitting the audit trail across locations.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_LOG_PATH = os.path.join(_PROJECT_ROOT, "reports", "audit_trail.jsonl")


def log_decision(agent, transaction_id, decision, reasoning, run_id=None,
                  extra=None, log_path=DEFAULT_LOG_PATH):
    """
    Records one decision made by one agent about one transaction.

    agent: which agent made this call, e.g. "reconciliation_agent"
    transaction_id: which transaction this is about (or "N/A" for
                     non-transaction-specific events)
    decision: the short outcome, e.g. "matched", "duplicate_entry",
              "auto_resolved", "bank_confirmed"
    reasoning: a human-readable sentence explaining WHY - this is the part
               that makes the system explainable, not just correct
    extra: optional dict of any additional structured detail worth keeping
    """
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "run_id": run_id,
        "transaction_id": transaction_id,
        "decision": decision,
        "reasoning": reasoning,
        "extra": extra or {}
    }

    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def read_audit_trail(log_path=DEFAULT_LOG_PATH):
    """Loads every logged entry, in order. Returns an empty list if no log exists yet."""
    if not os.path.exists(log_path):
        return []
    entries = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def get_trail_for_transaction(transaction_id, log_path=DEFAULT_LOG_PATH):
    """Every logged decision about ONE specific transaction, across all agents, in order."""
    return [e for e in read_audit_trail(log_path) if e["transaction_id"] == transaction_id]


def clear_audit_trail(log_path=DEFAULT_LOG_PATH):
    """Wipes the log - useful before a fresh e2e run so old entries don't mix in."""
    if os.path.exists(log_path):
        os.remove(log_path)


# --- Self-test ---
if __name__ == "__main__":
    test_log_path = "reports/audit_trail_test.jsonl"
    clear_audit_trail(test_log_path)

    log_decision(
        agent="reconciliation_agent", transaction_id="TXN10001",
        decision="matched", reasoning="Ledger, settlement, and bank amounts agree within tolerance; date gap 1 day.",
        run_id="RUN-TEST", log_path=test_log_path
    )
    log_decision(
        agent="exception_investigator", transaction_id="TXN10012",
        decision="approved", reasoning="Duplicate ledger_entry_id LDG20012 found twice; human approved removal.",
        run_id="RUN-TEST", extra={"root_cause": "duplicate_transaction"}, log_path=test_log_path
    )
    log_decision(
        agent="cash_forecast_agent", transaction_id="TXN10012",
        decision="excluded", reasoning="Approved duplicate removal has no cash impact.",
        run_id="RUN-TEST", log_path=test_log_path
    )

    print("Full trail:")
    for entry in read_audit_trail(test_log_path):
        print(entry)

    print("\nTrail for TXN10012 only:")
    for entry in get_trail_for_transaction("TXN10012", test_log_path):
        print(entry)

    clear_audit_trail(test_log_path)
    print("\nSelf-test passed, test log cleaned up.")