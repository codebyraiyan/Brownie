# ai_investigator.py
#
# What this file does:
# For exceptions that NO rule can explain (genuine_unresolved_anomaly -
# not a duplicate, not a refund, not a simple fee error, not a late
# payout), this asks Google's Gemini to generate a real investigative
# hypothesis in plain English, based on the transaction's actual numbers.
#
# WHY GEMINI: Google's Gemini API has a genuinely free developer tier
# (via Google AI Studio) - no credit card required, no paid trial that
# expires. That makes it the right choice for a student project where a
# paid API isn't an option, without resorting to unofficial/unverified
# third-party resellers.
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
# SETUP REQUIRED (free, no credit card needed):
#   1. Go to https://aistudio.google.com/apikey and create a free API key
#   2. pip3 install google-genai python-dotenv --break-system-packages
#   3. Either:
#      a) Create a .env file in your project root containing:
#         GEMINI_API_KEY=your_key_here
#      b) OR run: export GEMINI_API_KEY=your_key_here
#
# IMPORTANT: if you use a .env file, make sure ".env" is listed in your
# .gitignore - NEVER commit an API key to a public GitHub repo.
#
# HOW TO RUN THIS DIRECTLY (for testing):
#   python3 agents/ai_investigator.py

import os
import warnings

try:
    from dotenv import load_dotenv
    load_dotenv()  # reads .env file in the project root, if present
except ImportError:
    pass  # dotenv is optional - export GEMINI_API_KEY manually if not using .env

try:
    from google import genai
    from google.genai import types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False

# The SDK prints a recommendation about a different calling pattern that
# doesn't apply to our use (we don't use function calling / tools at all) -
# this suppresses that specific noise without hiding real errors.
warnings.filterwarnings("ignore", message=".*automatic function calling.*")


def generate_ai_hypothesis(exception: dict) -> str:
    """
    Takes a flagged exception that no rule could explain, and asks Gemini
    for a practical, specific investigative hypothesis - not a generic
    "look into it" response.
    """
    if not _GENAI_AVAILABLE:
        return ("AI hypothesis unavailable: 'google-genai' package not installed. "
                "Run: pip3 install google-genai --break-system-packages")

    if not os.environ.get("GEMINI_API_KEY"):
        return ("AI hypothesis unavailable: GEMINI_API_KEY not set. "
                "Get a free key at https://aistudio.google.com/apikey, then run: "
                "export GEMINI_API_KEY=your_key_here")

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
        client = genai.Client()  # reads GEMINI_API_KEY from environment automatically
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                http_options=types.HttpOptions(timeout=15000)  # 15 second timeout, in milliseconds
            )
        )
        return response.text.strip()
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

    print("Testing AI hypothesis generation (Gemini)...")
    print(f"google-genai package available: {_GENAI_AVAILABLE}")
    print(f"API key set: {bool(os.environ.get('GEMINI_API_KEY'))}")
    print()
    result = generate_ai_hypothesis(sample_exception)
    print("Result:")
    print(result)