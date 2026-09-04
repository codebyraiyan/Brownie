# Agent Communication Protocol (v2 — corrected per Phase 2 audit, Task #208)

This version replaces the original agent-protocol.md entirely. It fixes: an incomplete envelope, a Forecast payload missing required fields, and undefined error/versioning fields.

## 1. The Universal Envelope

```json
{
  "message_id": "MSG00123",
  "task_id": "TASK001",
  "run_id": "RUN0007",
  "correlation_id": "TASK001-RUN0007",
  "schema_version": "1.0",
  "from_agent": "reconciliation_agent",
  "to_agent": "exception_investigator",
  "timestamp": "2026-08-28T10:15:00",
  "status": "success",
  "payload": {}
}
```

- `task_id` — the overall Brownie task this message belongs to.
- `run_id` — a specific execution of the pipeline (lets you distinguish reruns of the same task).
- `correlation_id` — ties every message in one pipeline run together for tracing/logging.
- `schema_version` — lets payload shape evolve later without breaking older consumers.
- `status` is `"success"` or `"error"`.
- On error, `payload` becomes: `{ "error_code": "RECON_TIMEOUT", "error_message": "..." }`.

This envelope is required on every message, with no exceptions — including Finance Head → Brownie.

## 2. Payload — Reconciliation Agent → Exception Investigator

```json
"payload": {
  "flagged_exceptions": [
    {
      "transaction_id": "TXN10234",
      "exception_codes": ["missing_record", "duplicate_entry"],
      "primary_exception_code": "missing_record",
      "expected_amount": 977.00,
      "actual_amount": null,
      "variance": null,
      "date_gap_days": null
    }
  ],
  "matched_records": [
    { "transaction_id": "TXN10001", "amount": 500.00, "settlement_date": "2026-08-20" }
  ]
}
```

Two changes from v1: (1) `exception_codes` is now a list (a transaction can have more than one problem) with a separate `primary_exception_code` for queue ordering; (2) `matched_records` now carries amount/date, not just IDs, since downstream agents need this data.

## 3. Payload — Exception Investigator → Cash Forecast Agent

The original version only sent `transaction_id` + `investigation_status`, which Cash Forecast Agent cannot compute a forecast from. Corrected version sends a complete `cash_items[]` list — this is now the ONLY path data reaches Cash Forecast Agent (matched records are folded in here too, not sent separately):

```json
"payload": {
  "cash_items": [
    {
      "transaction_id": "TXN10001",
      "cash_treatment": "bank_confirmed",
      "amount": 500.00,
      "expected_settlement_date": "2026-08-20",
      "bank_confirmed_at": "2026-08-20",
      "investigation_status": null
    },
    {
      "transaction_id": "TXN10234",
      "cash_treatment": "expected_inflow",
      "amount": 977.00,
      "expected_settlement_date": "2026-08-30",
      "bank_confirmed_at": null,
      "investigation_status": "auto_resolved"
    },
    {
      "transaction_id": "TXN10099",
      "cash_treatment": "at_risk",
      "amount": 300.00,
      "expected_settlement_date": "2026-09-02",
      "bank_confirmed_at": null,
      "investigation_status": "pending_approval"
    }
  ]
}
```

`cash_treatment` is the single field Cash Forecast Agent uses to decide inclusion — see `cash-forecast-agent.md` Correction section for the 4 valid values.

## 4. Payload — Cash Forecast Agent → Finance Head

```json
"payload": {
  "opening_balance": 250000.00,
  "forecast": { "7_day": 45000.00, "14_day": 92000.00, "30_day": 210000.00 },
  "at_risk": { "7_day": 3000.00, "14_day": 8500.00, "30_day": 12000.00 }
}
```

## 5. Payload — Finance Head → Brownie
Uses the same envelope, wrapping the final merged report (per `finance-head.md`) as `payload`. Always include `reconciliation_run_status` (`success` / `failed`) at the top of the payload so Brownie knows if the report is trustworthy before reading further.