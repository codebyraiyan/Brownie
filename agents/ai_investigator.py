# ai_investigator.py
#
# What this file does:
# For exceptions that NO rule can explain (genuine_unresolved_anomaly -
# not a duplicate, not a refund, not a simple fee error, not a late
# payout), this asks Claude to generate a real investigative hypothesis
# in plain English, based on the transaction's actual numbers.
#
# WHY THIS MATTERS: everywhere else in Brownie, decisions are deterministic
# rules (matching, tolerance checks, duplicate detection) - which is the
# RIGHT choice for anything with a clear, checkable answer. But "why did
# this specific number come out wrong, with no known cause" is exactly
# the kind of open-ended reasoning a human analyst does by pattern-matching
# experience - which is what an LLM is actually good for, and rules aren't.
#
# GRACEFUL FALLBACK: if no API key is set, or the API call fails for any
# reason, this returns a clear fallback message instead of crashing the
# pipeline. The rest of Brownie works perfectly with or without this.
#
# SETUP REQUIRED:
#   pip3 install anthropic --break-system-packages
#   export ANTHROPIC_API_KEY=your_key_here
#
# HOW TO RUN THIS DIRECTLY (for testing):
#   python3 agents/ai_investigator.py

import os

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


def generate_ai_hypothesis(exception: dict) -> str:
    """
    Takes a flagged exception that no rule could explain, and asks Claude
    for a practical, specific investigative hypothesis - not a generic
    "look into it" response.
    """
    if not _ANTHROPIC_AVAILABLE:
        return ("AI hypothesis unavailable: 'anthropic' package not installed. "
                "Run: pip3 install anthropic --break-system-packages")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return ("AI hypothesis unavailable: ANTHROPIC_API_KEY not set. "
                "Run: export ANTHROPIC_API_KEY=your_key_here")

    txn_id = exception.get("transaction_id", "unknown")
    expected = exception.get("expected_amount")
    actual = exception.get("actual_amount")
    variance = exception.get("variance")
    date_gap = exception.get("date_gap_days")

    prompt = f"""You are a financial reconciliation analyst investigating an unexplained payment discrepancy.

Transaction ID: {txn_id}
Expected settlement amount (ledger amount minus fee minus tax): Rs.{expected}
Actual bank credited amount: Rs.{actual}
Variance: Rs.{variance}
Date gap between settlement and bank credit: {date_gap} days

This discrepancy could NOT be explained by any known rule: it is not a duplicate entry, not a refund/chargeback, not a simple rounding or fee-calculation error, and not a late payout.

In 2-3 sentences, suggest the most likely real-world explanation(s) a human investigator should check first, and what specific evidence would confirm or rule out each one. Be concrete and practical - reference the actual numbers above, not generic advice."""

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        # Never let an API failure crash the pipeline - degrade gracefully.
        return f"AI hypothesis unavailable (API error: {e}). Manual investigation required."


# --- Self-test ---
if __name__ == "__main__":
    sample_exception = {
        "transaction_id": "TXN10013",
        "expected_amount": 977.00,
        "actual_amount": 913.45,
        "variance": 63.55,
        "date_gap_days": 1
    }

    print("Testing AI hypothesis generation...")
    print(f"Anthropic package available: {_ANTHROPIC_AVAILABLE}")
    print(f"API key set: {bool(os.environ.get('ANTHROPIC_API_KEY'))}")
    print()
    result = generate_ai_hypothesis(sample_exception)
    print("Result:")
    print(result)