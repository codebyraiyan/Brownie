# Brownie — Orchestration Logic (Head Agent)

Brownie is the head agent. It does not do reconciliation, investigation, or forecasting itself — it receives requests, routes them to the right Department Head, tracks progress, and assembles the final result.

## 1. Task Intake
A request enters Brownie in this shape:

```json
{ "task_type": "finance_reconciliation", "period": "2026-07-01 to 2026-08-30" }
```

## 2. Routing
Brownie holds a lookup table mapping task types to Department Heads:

```json
{
  "finance": "FinanceHead",
  "operations": null,
  "sales": null,
  "marketing": null,
  "product": null,
  "engineering": null
}
```

Only `"finance"` is active in this build. Brownie matches `task_type` to the correct department and hands off the full request. Adding a new department later means filling in the table — no change to Brownie's core logic.

## 3. State Tracking
For every task, Brownie tracks:

| Field | Example |
|---|---|
| task_id | TASK001 |
| status | pending / in_progress / completed / failed |
| assigned_to | finance |
| started_at | timestamp |
| completed_at | timestamp |

This lets Brownie know what's currently running, even mid-task.

## 4. Result Assembly
When a Department Head finishes, Brownie wraps its report with metadata before returning it:

```json
{
  "task_id": "TASK001",
  "status": "completed",
  "department": "finance",
  "result": { "...Finance Head's report..." }
}
```

## 5. Error Handling
If a Department Head fails (bad data, agent crash), Brownie catches the error, sets `status: "failed"`, and returns a clear error message and reason — rather than letting the whole system crash silently.

---

# Correction (Task #208): Capability Registry (not a fixed routing table)

The original routing table (`{"finance": "FinanceHead", "operations": null, ...}`) was not truly extensible — it also didn't match the `task_type` naming used elsewhere (`finance_reconciliation`), and had no versioning or capability metadata.

## Corrected Approach: Capability Registry

Instead of one department key, Brownie registers specific **capabilities**:

```json
{
  "finance.reconcile": {
    "handler": "FinanceHead",
    "schema_version": "1.0",
    "status": "active"
  }
}
```

A task specifies the exact capability it needs:
```json
{ "capability": "finance.reconcile", "period": "2026-07-01 to 2026-08-30" }
```

Brownie looks up `finance.reconcile` directly in the registry — no ambiguous string matching between `"finance"` and `"finance_reconciliation"`.

**Why this is genuinely extensible:** adding Operations later means registering `"operations.procurement"` or similar as a new capability — no changes to Brownie's lookup logic, no null placeholders sitting unused, and each capability can carry its own schema version independently.