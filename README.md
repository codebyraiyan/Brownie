# Brownie

An agentic AI system built to run business operations autonomously. Brownie is the head agent that orchestrates specialized department heads, each managing their own sub-agents.

**Current scope:** Finance vertical only.

Brownie &rarr; Finance Head &rarr; 3 sub-agents:
- **Reconciliation Agent** &mdash; matches records across Ledger, Settlement, and Bank data using a full outer join, flags mismatches
- **Exception Investigator** &mdash; diagnoses root cause of flagged mismatches, auto-resolves where safe, gates the rest behind human approval (built on LangGraph)
- **Cash Forecast Agent** &mdash; projects future cash position (not just inflows) from reconciled data across 7/14/30-day horizons

Other departments (Operations, Sales, Marketing, Product, Engineering) are future scope and not part of this build.

**Status:** Core pipeline complete and verified.

---

## Verified Results

Run on a 168-record synthetic dataset (160 base + 8 refund cases), 56 deliberately injected exceptions (30% rate) across 5 categories:

| Metric | Result |
|---|---|
| Exact transaction-ID-level exception accuracy | **56/56 (100%)** |
| False positives | **0** |
| Match rate | 66.67% |
| Audit trail entries per clean run | 392 (one reasoned decision per agent per transaction) |
| Edge case tests passing | 16/16 |
| Scale tested | Up to 1,000 records (20x Razorpay's stated 50-record minimum), 100% accuracy maintained |

Every phase of this project (data, architecture, code) was independently audited by an external AI (ChatGPT for architecture docs, Codex for code) before proceeding, with all critical/moderate findings fixed and re-verified.

---

## Quick Start

```bash
# 1. Install dependencies
pip3 install -r requirements.txt --break-system-packages

# 2. Generate the synthetic dataset (160 records by default)
python3 inject_mismatches.py

# 3. Run the full pipeline: Brownie -> Finance Head -> all 3 agents
# NOTE: this runs non-interactively by default (auto-approve mode) - it
# will NOT hang waiting for terminal input. Every run starts with a fresh
# audit trail (cleared automatically), so results are never mixed with a
# previous run's data.
python3 run_e2e.py

# 4. Generate the human-readable exception report
python3 generate_exception_report.py

# 5. (Optional) Run the edge-case regression suite
python3 test_edge_cases.py

# 6. (Optional) Test at a larger scale, e.g. 500 records
python3 inject_mismatches.py 500
python3 run_e2e.py
# Reset back to the default afterward:
python3 inject_mismatches.py
```

**Outputs to look at:**
- `reports/e2e_run_output.json` &mdash; full structured run report
- `reports/exception_report.md` &mdash; human-readable exception summary (start here)
- `reports/audit_trail.jsonl` &mdash; every agent decision, with reasoning, per transaction

---

## Architecture

See `docs/architecture-diagram.jpg` for the full visual, and `docs/agent-protocol.md` for the exact message format every agent uses to talk to the others.

```
Brownie (capability registry: finance.reconcile)
  -> Finance Head (sequential pipeline, per-stage failure handling)
       -> Reconciliation Agent   (full outer join, duplicate/refund/amount/date checks)
       -> Exception Investigator (root-cause classification, human-in-loop approval)
       -> Cash Forecast Agent    (date-aware cash position, no double-counting)
```

Detailed logic for each agent lives in `docs/`:
- `reconciliation-agent.md`
- `exception-investigator.md`
- `cash-forecast-agent.md`
- `finance-head.md`
- `brownie-orchestrator.md`
- `agent-protocol.md`
- `schema.md`

---

## Roadmap: AI-Judgment Integration (Built, Ready to Activate)

Every decision in the current pipeline is deterministic rule logic - correct for anything with a clear, checkable answer (matching, tolerance checks, duplicate detection). The one case that's genuinely open-ended is `genuine_unresolved_anomaly`: an amount discrepancy with no rule-based explanation.

For exactly this case, `agents/ai_investigator.py` is a complete, working integration with Google's Gemini API: it generates a specific, evidence-based investigative hypothesis from the transaction's actual numbers, instead of a generic "requires manual investigation" placeholder.

**Why Gemini:** Google's Gemini API has a genuinely free developer tier (via Google AI Studio, no credit card required) - the right choice for a student project's budget, without resorting to unofficial third-party API resellers.

**Current state:** fully built and wired into the Exception Investigator. It degrades gracefully to a clear fallback message if no API key is configured, with zero setup required; the rest of the pipeline is completely unaffected either way.

**To activate:**
```bash
pip3 install google-genai --break-system-packages
export GEMINI_API_KEY=your_key_here   # free at https://aistudio.google.com/apikey
```
No code changes needed - it activates automatically once a key is present.

This is a deliberate scope choice, not an oversight: the design keeps AI narrowly scoped to the one case where rules genuinely run out, rather than using it as a blanket buzzword layer over what is otherwise correctly deterministic logic.

---

## Known Limitations

These are disclosed, intentional scope decisions for this build &mdash; not oversights. A production deployment would need to address these before handling real financial data:

- **Float precision for money.** Amounts are handled as Python floats with rounding, not `Decimal`. Fine for this dataset's scale and tolerance (Rs.1.00), but a production system should use `Decimal` or integer minor units to avoid binary rounding artifacts.
- **No full CSV schema validation layer.** Missing/malformed columns can raise an exception at the Reconciliation Agent level; this is caught gracefully one level up by Finance Head's failure handling (verified), but there's no upfront schema/header validation pass.
- **In-memory task tracking.** Brownie's task state (`_tasks` dict) lives in process memory only &mdash; it does not survive a restart and is not safe for concurrent submissions. Acceptable for a single-session demo; a real deployment needs persistent storage (e.g. SQLite) and proper locking.
- **LangGraph checkpointing is in-memory.** Approval workflows use `InMemorySaver`; a pending approval does not survive a process restart. A durable checkpointer would be needed for a long-running service.
- **Only the primary exception code is investigated.** A transaction can have multiple exception codes (e.g. both `missing_record` and `duplicate_entry`), but only the highest-precedence one drives the Exception Investigator's decision today. The others are recorded but not separately resolved.
- **No versioned fee-rule table.** The fee/tax model is fixed at 2% + 18% GST, matching the synthetic data generator. A real system would need a versioned, auditable fee-rule table per payment method and time period, which is why `amount_mismatch` cases are always escalated for human review rather than auto-explained.
- **Settlement has no stable row-level ID.** Unlike ledger (`ledger_entry_id`) and bank (`payment_attempt_id`), the settlement schema has no equivalent identifier, so settlement-side duplicates are detected via `transaction_id` repetition only.
- **The 30% exception rate is a stress-test rate**, chosen for thorough branch coverage during development &mdash; not a claim about real-world reconciliation error rates, which are typically much lower.
- **Human approval is a CLI prompt**, standing in for what would be a real reviewer dashboard in production.
- **Internal agent-to-agent calls pass plain Python dicts**, not the full message envelope defined in `agent-protocol.md`. The envelope is used at the Brownie/Finance Head boundary; wrapping every internal handoff was judged unnecessary complexity for this scope.
- **Audit log writes are not file-locked.** `audit_log.py` appends to a single file with standard (non-atomic) writes. Safe for this project's single-process design; a multi-process deployment would need file locking or a proper logging backend.
- **ID ranges assume a reasonable dataset scale.** Transaction/ledger/bank ID numbering could theoretically overlap in formatting at extremely large scales (10,000+ records) - verified safe at the tested scale (up to 1,000 records), not designed for unbounded scale.

---

## Project Structure

```
Brownie/
  agents/              # All agent code
  data/                # Synthetic dataset (generated, not hand-written)
  docs/                # Architecture and logic documentation
  reports/             # Run outputs, audit trail, exception reports
  inject_mismatches.py # Synthetic data generator
  run_e2e.py           # Full pipeline runner
  generate_exception_report.py
  test_edge_cases.py
  requirements.txt
```
