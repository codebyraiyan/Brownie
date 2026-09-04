# generate_exception_report.py
#
# What this file does:
# Reads reports/audit_trail.jsonl (every agent's logged decisions) and
# reports/e2e_run_output.json (the run summary), and produces ONE clean,
# human-readable Markdown report: reports/exception_report.md
#
# This is the literal artifact Razorpay's Track 4 asks for - "reporting
# its match rate and the exceptions it could not resolve." A judge should
# be able to open this file and immediately understand what happened,
# without reading raw JSON.
#
# HOW TO RUN THIS:
#   Run AFTER run_e2e.py (it needs the files that script produces).
#   python3 generate_exception_report.py

import json
import os
from datetime import datetime, timezone

# TASK #406 AUDIT FIX: anchor to project root, not cwd.
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
AUDIT_TRAIL_PATH = os.path.join(_PROJECT_ROOT, "reports", "audit_trail.jsonl")
E2E_OUTPUT_PATH = os.path.join(_PROJECT_ROOT, "reports", "e2e_run_output.json")
REPORT_OUTPUT_PATH = os.path.join(_PROJECT_ROOT, "reports", "exception_report.md")

# Statuses that mean "we could NOT resolve this - a human needs to look at it"
UNRESOLVED_STATUSES = {"pending_approval", "escalated", "escalated_for_review", "revised_proposal", "rejected"}
# "approved" is ambiguous on its own - see CLOSED_ROOT_CAUSES below.
# Root causes where "approved"/"auto_resolved" means the underlying problem
# is ACTUALLY closed - no further action needed.
CLOSED_ROOT_CAUSES = {"late_payout_or_posting", "duplicate_transaction", "refund_chargeback_not_accounted_for"}
# Root causes where "approved" only means "go ahead and chase this" -
# the real-world problem (e.g. missing money) is still open.
FOLLOWUP_ROOT_CAUSES = {"missing_record"}


def load_audit_trail():
    if not os.path.exists(AUDIT_TRAIL_PATH):
        raise FileNotFoundError(
            f"{AUDIT_TRAIL_PATH} not found. Run run_e2e.py first to generate it."
        )
    entries = []
    with open(AUDIT_TRAIL_PATH) as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                # TASK #406 AUDIT FIX: don't let one corrupted line crash
                # the whole report - skip it, but say exactly which line.
                print(f"[generate_exception_report] WARNING: skipping malformed "
                      f"line {line_num} in {AUDIT_TRAIL_PATH}: {e}")
    return entries


def load_e2e_summary():
    if not os.path.exists(E2E_OUTPUT_PATH):
        raise FileNotFoundError(
            f"{E2E_OUTPUT_PATH} not found. Run run_e2e.py first to generate it."
        )
    with open(E2E_OUTPUT_PATH) as f:
        return json.load(f)


def build_transaction_stories(audit_entries):
    """
    Groups every logged decision by transaction_id, so we can tell the
    FULL story of each exception: what Reconciliation found, what the
    Investigator decided, and what the Forecast Agent did with it.
    """
    stories = {}
    for entry in audit_entries:
        txn_id = entry["transaction_id"]
        if txn_id not in stories:
            stories[txn_id] = {}
        stories[txn_id][entry["agent"]] = entry
    return stories


def generate_report():
    audit_entries = load_audit_trail()
    summary = load_e2e_summary()

    # TASK #406 AUDIT FIX: filter to only THIS run's entries, defense in
    # depth on top of run_e2e.py already clearing the trail at start. This
    # protects against stale data if someone ran standalone agent tests,
    # or an older e2e run's log, without clearing in between.
    target_run_id = summary.get("finance_head_report", {}).get("run_id")
    if target_run_id:
        before_count = len(audit_entries)
        audit_entries = [e for e in audit_entries if e.get("run_id") == target_run_id]
        skipped = before_count - len(audit_entries)
        if skipped > 0:
            print(f"[generate_exception_report] Filtered out {skipped} audit entries "
                  f"from other runs (kept only run_id={target_run_id}).")

    stories = build_transaction_stories(audit_entries)

    # Only look at transactions the Reconciliation Agent actually flagged
    # as an exception (decision != "matched")
    exception_txn_ids = [
        txn_id for txn_id, agents in stories.items()
        if "reconciliation_agent" in agents and agents["reconciliation_agent"]["decision"] != "matched"
    ]

    unresolved = []
    needs_followup = []
    resolved = []

    for txn_id in exception_txn_ids:
        story = stories[txn_id]
        recon = story.get("reconciliation_agent", {})
        investigation = story.get("exception_investigator")

        if investigation is None:
            unresolved.append({
                "transaction_id": txn_id,
                "reconciliation_finding": recon.get("decision"),
                "status": "not_investigated",
                "investigator_reasoning": "Exception Investigator did not process this transaction."
            })
            continue

        status = investigation["decision"]
        reasoning_text = investigation.get("reasoning", "")
        # TASK #406 AUDIT FIX: read root_cause from the structured 'extra'
        # field instead of parsing free-text reasoning. String parsing broke
        # silently if the reasoning wording ever changed - this can't.
        root_cause_guess = investigation.get("extra", {}).get("root_cause")

        row = {
            "transaction_id": txn_id,
            "reconciliation_finding": recon.get("decision"),
            "status": status,
            "root_cause": root_cause_guess or "N/A",
            "investigator_reasoning": reasoning_text
        }

        if status in UNRESOLVED_STATUSES:
            unresolved.append(row)
        elif status in ("auto_resolved", "approved"):
            if root_cause_guess in FOLLOWUP_ROOT_CAUSES:
                needs_followup.append(row)
            elif root_cause_guess in CLOSED_ROOT_CAUSES:
                resolved.append(row)
            else:
                # Unknown root cause paired with a resolved-sounding status -
                # don't assume it's actually closed.
                needs_followup.append(row)
        else:
            row["investigator_reasoning"] += " (unrecognized status - flagged conservatively)"
            unresolved.append(row)

    # --- Build the Markdown report ---
    lines = []
    lines.append("# Brownie - Reconciliation Exception Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Run Task ID: {summary.get('task_id', 'N/A')}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    dept = summary.get("finance_head_report", {})
    lines.append(f"- **Match rate:** {dept.get('match_rate', 'N/A')}")
    lines.append(f"- **Total records:** {dept.get('total_records', 'N/A')}")
    lines.append(f"- **Matched cleanly:** {dept.get('matched', 'N/A')}")
    lines.append(f"- **Total exceptions:** {dept.get('exceptions_total', 'N/A')}")
    lines.append(f"- **Fully resolved (no further action needed):** {len(resolved)}")
    lines.append(f"- **Approved for follow-up (action still required):** {len(needs_followup)}")
    lines.append(f"- **Unresolved (require manual investigation):** {len(unresolved)}")
    lines.append("")
    lines.append("> **Note on approvals:** transactions marked 'approved' in this run were approved "
                  "in automated testing mode, not by a real human reviewer. In a live deployment, "
                  "these would require actual sign-off before any correction is posted.")
    lines.append("")

    if dept.get("cash_forecast"):
        lines.append("## Cash Forecast")
        lines.append("")
        lines.append(f"- **Opening balance:** Rs.{dept.get('opening_balance', 'N/A')}")
        lines.append(f"- **7-day forecast:** Rs.{dept['cash_forecast'].get('7_day')}")
        lines.append(f"- **14-day forecast:** Rs.{dept['cash_forecast'].get('14_day')}")
        lines.append(f"- **30-day forecast:** Rs.{dept['cash_forecast'].get('30_day')}")
        lines.append(f"- **At-risk (7/14/30 day):** Rs.{dept['at_risk'].get('7_day')} / "
                      f"Rs.{dept['at_risk'].get('14_day')} / Rs.{dept['at_risk'].get('30_day')}")
        lines.append("")

    lines.append("## Unresolved Exceptions (Could Not Be Resolved Automatically)")
    lines.append("")
    lines.append("These require a human to review before they can be closed out.")
    lines.append("")
    if unresolved:
        lines.append("| Transaction ID | Finding | Status | Reasoning |")
        lines.append("|---|---|---|---|")
        for r in sorted(unresolved, key=lambda x: x["transaction_id"] or ""):
            lines.append(f"| {r['transaction_id']} | {r['reconciliation_finding']} | {r['status']} | {r['investigator_reasoning']} |")
    else:
        lines.append("*None - every flagged exception was automatically resolved or approved.*")
    lines.append("")

    lines.append("## Approved for Follow-Up (Action Still Required)")
    lines.append("")
    lines.append("These were reviewed and approved to proceed, but the underlying issue "
                  "(e.g. tracking down missing funds) is not yet closed - only the investigation step is.")
    lines.append("")
    if needs_followup:
        lines.append("| Transaction ID | Finding | Root Cause | Reasoning |")
        lines.append("|---|---|---|---|")
        for r in sorted(needs_followup, key=lambda x: x["transaction_id"] or ""):
            lines.append(f"| {r['transaction_id']} | {r['reconciliation_finding']} | {r['root_cause']} | {r['investigator_reasoning']} |")
    else:
        lines.append("*None.*")
    lines.append("")

    lines.append("## Fully Resolved (No Further Action Needed)")
    lines.append("")
    if resolved:
        lines.append("| Transaction ID | Finding | Root Cause | Reasoning |")
        lines.append("|---|---|---|---|")
        for r in sorted(resolved, key=lambda x: x["transaction_id"] or ""):
            lines.append(f"| {r['transaction_id']} | {r['reconciliation_finding']} | {r['root_cause']} | {r['investigator_reasoning']} |")
    else:
        lines.append("*None.*")
    lines.append("")

    os.makedirs(os.path.dirname(REPORT_OUTPUT_PATH), exist_ok=True)
    with open(REPORT_OUTPUT_PATH, "w") as f:
        f.write("\n".join(lines))

    print(f"Report generated: {REPORT_OUTPUT_PATH}")
    print(f"  Unresolved exceptions: {len(unresolved)}")
    print(f"  Approved for follow-up: {len(needs_followup)}")
    print(f"  Fully resolved: {len(resolved)}")

    return unresolved, needs_followup, resolved


if __name__ == "__main__":
    generate_report()