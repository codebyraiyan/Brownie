# Exception Investigator — Root Cause & Resolution Logic

Takes exceptions flagged by the Reconciliation Agent and determines *why* they occurred, resolving what it can and escalating the rest.

## Root Cause Categories
Each exception is classified into one of the following:
- **Fee/Tax Miscalculation** — expected deduction doesn't match actual
- **Duplicate Transaction** — same transaction recorded more than once in one source
- **Missing Record** — transaction never settled or never hit the bank
- **Refund/Chargeback Not Accounted For** — a reversal exists that wasn't reflected in one of the sources
- **Genuine Unresolved Anomaly** — no clear cause identified

---

---

# Appendix: Decision Logic & Approval-Gating (Task #204)

## 1. Root Cause Categories

| Category | Trigger |
|---|---|
| Fee/Tax Miscalculation | Expected fee/tax deduction doesn't match actual |
| Duplicate Transaction | Same `ledger_entry_id` appears twice |
| Missing Record | Transaction absent from bank or settlement |
| Refund/Chargeback Not Accounted For | A reversal exists but wasn't reflected in one source |
| Late Payout or Posting | Date gap > 2 days, but otherwise a clean match — likely a delayed payout, not a data error |
| Genuine Unresolved Anomaly | No clear cause found after checking all above |

Separating "Late Payout or Posting" from "Genuine Unresolved Anomaly" keeps the anomaly bucket honest — a delayed payout is a known, low-risk pattern, not a mystery, and shouldn't be reported as one.

## 2. Approval-Gating Rule

**Auto-Resolved (no human needed):**
- Late Payout or Posting — logged, no correction needed, expected to settle on its own
- Fee/Tax Miscalculation — recalculable with certainty from known fee rules

**Requires Human Approval before any correction is posted:**
- Duplicate Transaction — could reflect a refund process already underway
- Missing Record — could mean money is stuck, not just a data gap
- Refund/Chargeback Not Accounted For — touches real money movement, must be verified
- Genuine Unresolved Anomaly — always escalated by definition, no auto-fix proposed

Auto-correcting financial records without solid evidence is unsafe. Any category touching real money movement or requiring an assumption about intent is gated behind human approval.

## 3. Proposed Resolution Format
Rather than silently acting, the agent produces a proposed resolution with reasoning and marks it `pending_approval`:

```json
{
  "transaction_id": "TXN10234",
  "root_cause": "duplicate_transaction",
  "proposed_action": "Remove duplicate ledger entry LDG20234",
  "investigation_status": "pending_approval",
  "evidence": "ledger_entry_id LDG20234 appears twice"
}
```

A human reviews and approves or rejects before any correction is actually posted.

## 4. Final Status Values
Every exception ends in one of:
`auto_resolved` | `pending_approval` | `approved` | `rejected` | `escalated`

`escalated` applies to Genuine Unresolved Anomaly cases with no proposed fix at all.

---

# Correction (Task #208): Rejection Path & Rule Conflict

## Important: resolve a contradiction first
Your original "Resolution Rule" section (written in Task #106, before approval-gating existed) says Duplicate Transaction and Refund/Chargeback are auto-resolved. The Task #204 appendix correctly overrides this — both require human approval. **Delete or strike through the original Task #106 "Resolution Rule" section** so only the Task #204 appendix rules apply. The appendix is authoritative.

## Rejection Path (previously undefined)
```
pending_approval → approved | rejected
rejected → escalated_for_review | revised_proposal
```

When a human rejects a proposed resolution:
- The proposed correction is **discarded** — nothing is posted to any record.
- The transaction's `investigation_status` becomes `rejected`.
- It is routed to one of two places, decided by the reviewer:
  - `escalated_for_review` — needs deeper manual investigation, no automated fix will be re-attempted
  - `revised_proposal` — the agent generates a new proposed resolution with different reasoning, returns to `pending_approval`
- It appears in the final exception report with the reviewer's rationale, and receives `cash_treatment: at_risk` or `excluded` (see `cash-forecast-agent.md` Correction) — never silently dropped from the report.

## Final Status Values (updated)
`auto_resolved` | `pending_approval` | `approved` | `rejected` | `escalated_for_review` | `revised_proposal`

---

# AI-Judgment Addition (Task #505)

Every other decision in Brownie is deterministic rule logic - matching, tolerance checks, duplicate detection - which is the correct choice whenever there's a clear, checkable answer. But "genuine_unresolved_anomaly" cases are exactly the opposite: by definition, no rule explains them.

For these specific cases (and ONLY these - not every exception), the Exception Investigator calls Claude (via `agents/ai_investigator.py`) to generate a real, specific investigative hypothesis from the transaction's actual numbers, rather than a generic "requires manual investigation" placeholder.

This is deliberately narrow in scope: deterministic logic still owns every case with a clear answer. AI is used only where genuine judgment is needed and rules run out - which is the point, not an afterthought.

Requires `ANTHROPIC_API_KEY` to be set; degrades gracefully to a plain fallback message if not configured, so the rest of the pipeline is unaffected either way.