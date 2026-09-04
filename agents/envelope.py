# envelope.py
#
# What this file does:
# Every message that passes between Brownie, Finance Head, and the 3 sub-agents
# uses the SAME wrapper structure - the "envelope" - defined in agent-protocol.md.
# Instead of every agent writing its own message-building code (and risking typos
# or missing fields), they all import and use these two functions.
#
# You won't need to edit this file much - other agent files will import from it.

import uuid
from datetime import datetime, timezone

SCHEMA_VERSION = "1.0"


def _new_id(prefix):
    """Generates a short unique ID like 'MSG-a1b2c3d4'."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def create_envelope(from_agent, to_agent, payload, task_id, run_id,
                     status="success", correlation_id=None):
    """
    Builds a properly-formatted message envelope.

    from_agent / to_agent: which agents are talking, e.g. "reconciliation_agent"
    payload: the actual data being sent (a dict) - shape depends on which
             agents are talking, see agent-protocol.md for the exact shapes
    task_id: the overall Brownie task this belongs to (passed in, not generated
             here, since it stays the same across the whole pipeline run)
    run_id: identifies this specific execution of the pipeline
    status: "success" or "error"
    correlation_id: ties all messages in one pipeline run together.
                     If not given, defaults to "{task_id}-{run_id}"
    """
    if correlation_id is None:
        correlation_id = f"{task_id}-{run_id}"

    return {
        "message_id": _new_id("MSG"),
        "task_id": task_id,
        "run_id": run_id,
        "correlation_id": correlation_id,
        "schema_version": SCHEMA_VERSION,
        "from_agent": from_agent,
        "to_agent": to_agent,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "payload": payload
    }


def create_error_envelope(from_agent, to_agent, error_code, error_message,
                           task_id, run_id, correlation_id=None):
    """Same as create_envelope, but for reporting a failure instead of data."""
    return create_envelope(
        from_agent=from_agent,
        to_agent=to_agent,
        payload={"error_code": error_code, "error_message": error_message},
        task_id=task_id,
        run_id=run_id,
        status="error",
        correlation_id=correlation_id
    )


def new_task_id():
    """Call this once when Brownie receives a new request."""
    return _new_id("TASK")


def new_run_id():
    """Call this once each time Finance Head starts a pipeline execution."""
    return _new_id("RUN")


def is_error(envelope):
    """Quick check any agent can use before touching payload."""
    return envelope.get("status") == "error"


# --- Quick self-test when this file is run directly ---
if __name__ == "__main__":
    task_id = new_task_id()
    run_id = new_run_id()

    msg = create_envelope(
        from_agent="reconciliation_agent",
        to_agent="exception_investigator",
        payload={"flagged_exceptions": [], "matched_records": []},
        task_id=task_id,
        run_id=run_id
    )
    print("Sample success envelope:")
    print(msg)

    err = create_error_envelope(
        from_agent="reconciliation_agent",
        to_agent="finance_head",
        error_code="RECON_CRASH",
        error_message="Could not read bank.csv",
        task_id=task_id,
        run_id=run_id
    )
    print("\nSample error envelope:")
    print(err)
    print("\nis_error check:", is_error(err))
