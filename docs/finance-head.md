# Finance Head — Coordination Logic

Finance Head sits between Brownie and the 3 Finance sub-agents. It runs them in the correct order, passes data between them, handles failures, and merges their output into one final report.

## 1. Execution Order (sequential)

```
Reconciliation Agent → Exception Investigator → Cash Forecast Agent
```

- **Reconciliation Agent** runs first — takes raw ledger/settlement/bank data, produces matches + flagged exceptions.
- **Exception Investigator** runs second — takes the flagged exceptions, diagnoses root cause, resolves or escalates.
- **Cash Forecast Agent** runs last — needs clean, resolved data to project cash position accurately.

Each step depends on the previous one's output, so they cannot run in parallel.

## 2. Data Handoff Between Agents
Finance Head passes structured output from one agent as input to the next (exact message format defined in `agent-protocol.md`, Task #206):

```json
{
  "from": "reconciliation_agent",
  "matched_records": ["..."],
  "flagged_exceptions": ["..."]
}
```

## 3. Failure Handling Mid-Pipeline
If a step fails (e.g. Exception Investigator times out or errors):
- Finance Head marks that step `failed`
- It still passes the successfully matched records forward to Cash Forecast Agent
- The final report is labeled with an `incomplete_data: true` flag, so the forecast is never presented as fully reliable when a step failed

This is preferred over halting the whole pipeline, since a partial, clearly-labeled result is more useful than nothing.

## 4. Final Report Assembly
Finance Head merges all 3 agents' outputs into one report before returning it to Brownie:

```json
{
  "match_rate": "82%",
  "total_records": 160,
  "matched": 112,
  "exceptions_total": 48,
  "exceptions_resolved": 30,
  "exceptions_escalated": 18,
  "cash_forecast": {
    "7_day": 45000,
    "14_day": 92000,
    "30_day": 210000
  },
  "at_risk_amount": 12000,
  "incomplete_data": false
}
```

This report format directly satisfies the core requirement: match rate + honest unresolved exceptions, plus the cash forecast as a differentiator.

---

# Correction (Task #208): Failure Handling for a Full Reconciliation Agent Crash

The original failure-handling section only covered the Exception Investigator failing partway through — it did not address the Reconciliation Agent itself crashing, which is more severe: with no matches and no exceptions, there is no valid input for either downstream agent at all.

## Corrected Failure Handling by Stage

**If Reconciliation Agent fails completely:**
- Block Exception Investigator and Cash Forecast Agent entirely — do not attempt to run them on no data.
- Return a `snapshot_only` report to Brownie: opening balance only, no forecast, `reconciliation_run_status: "failed"`.
- Never present a snapshot-only number as if it were a reconciliation-based forecast.

**If Exception Investigator fails partway (original case, still valid):**
- Matched records from Reconciliation Agent are still valid and forwarded to Cash Forecast Agent.
- Final report includes `incomplete_data: true`.

**If Cash Forecast Agent fails:**
- Reconciliation + investigation results are still valid and reported.
- Final report omits `forecast`/`at_risk` fields entirely rather than guessing, and includes `forecast_status: "failed"`.

## Additional Required Metadata
Every failure report includes: `blocked_by` (which stage failed), `run_id`, and `last_successful_run_id` (if any prior run succeeded), so Brownie/the user can tell whether this is a one-off issue or a persistent problem.