# brownie.py
#
# What this file does:
# This is Brownie - the head agent. It does NOT do reconciliation, forecasting,
# or investigation itself. It just:
#   1. Receives a task request
#   2. Looks up which registered "capability" can handle it
#   3. Tracks the task's state while it runs
#   4. Wraps and returns whatever that capability's handler produces
#
# Per the Task #208 audit fix, we use a CAPABILITY REGISTRY (e.g.
# "finance.reconcile") instead of a fixed department lookup table - this is
# what makes adding Operations/Sales/etc. later a registration, not a
# rewrite.
#
# HOW TO RUN THIS DIRECTLY (for testing):
#   python3 agents/brownie.py

import sys
import os
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from envelope import create_envelope, create_error_envelope, new_task_id, new_run_id


class Brownie:
    def __init__(self):
        # The capability registry. Each entry says WHO handles a capability
        # and what schema version it speaks. Adding a new department later
        # means adding a new entry here - nothing else about Brownie changes.
        self._registry = {}
        # Tracks every task Brownie has ever been asked to run, by task_id.
        self._tasks = {}

    def register_capability(self, capability_name, handler_fn, schema_version="1.0"):
        """
        Registers a function that can handle a specific capability.
        Example: brownie.register_capability("finance.reconcile", run_finance_head)
        """
        self._registry[capability_name] = {
            "handler": handler_fn,
            "schema_version": schema_version,
            "status": "active"
        }

    def submit_task(self, capability, **kwargs):
        """
        The main entry point. Give it a capability name (e.g.
        "finance.reconcile") and any arguments the handler needs.
        Returns an envelope wrapping the handler's result.
        """
        task_id = new_task_id()
        run_id = new_run_id()

        self._tasks[task_id] = {
            "status": "pending",
            "capability": capability,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None
        }

        # --- Capability lookup ---
        if capability not in self._registry:
            self._tasks[task_id]["status"] = "failed"
            self._tasks[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            return create_error_envelope(
                from_agent="brownie", to_agent="user",
                error_code="UNKNOWN_CAPABILITY",
                error_message=f"No handler registered for capability '{capability}'. "
                              f"Available: {list(self._registry.keys())}",
                task_id=task_id, run_id=run_id
            )

        entry = self._registry[capability]
        if entry["status"] != "active":
            self._tasks[task_id]["status"] = "failed"
            self._tasks[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            return create_error_envelope(
                from_agent="brownie", to_agent="user",
                error_code="CAPABILITY_INACTIVE",
                error_message=f"Capability '{capability}' is registered but not active.",
                task_id=task_id, run_id=run_id
            )

        # --- Run the handler ---
        self._tasks[task_id]["status"] = "in_progress"

        try:
            handler_result = entry["handler"](task_id=task_id, run_id=run_id, **kwargs)
        except Exception as e:
            # A safety net - Finance Head is designed to catch its own
            # failures internally, but if something truly unexpected
            # happens, Brownie itself must not crash.
            # TASK #308 AUDIT FIX: don't expose raw exception text (could
            # leak file paths/internals) - log it, return a stable message.
            print(f"[Brownie] Handler for '{capability}' crashed unexpectedly: {e}")
            self._tasks[task_id]["status"] = "failed"
            self._tasks[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            return create_error_envelope(
                from_agent="brownie", to_agent="user",
                error_code="HANDLER_CRASHED",
                error_message="The requested task could not be completed due to an internal error.",
                task_id=task_id, run_id=run_id
            )

        # handler_result is already an envelope (Finance Head returns one) -
        # Brownie assembles its own final response around it.
        self._tasks[task_id]["status"] = "completed" if handler_result["status"] == "success" else "failed"
        self._tasks[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()

        return create_envelope(
            from_agent="brownie", to_agent="user",
            payload={
                "task_id": task_id,
                "status": self._tasks[task_id]["status"],
                "department_result": handler_result["payload"]
            },
            task_id=task_id, run_id=run_id,
            status=handler_result["status"]
        )

    def get_task_status(self, task_id):
        """Lets you check on a task's state at any time."""
        return self._tasks.get(task_id, {"error": "task_id not found"})


# --- Self-test ---
if __name__ == "__main__":
    brownie = Brownie()

    # --- Test 1: unknown capability (before anything is registered) ---
    print("=== TEST 1: Unknown capability ===")
    result = brownie.submit_task("finance.reconcile", data_dir="data")
    print(f"Status: {result['status']}, error: {result['payload'].get('error_message')}\n")

    # --- Test 2: register a simple dummy handler and confirm routing works ---
    print("=== TEST 2: Dummy handler routing (no LangGraph needed) ===")

    def dummy_handler(task_id, run_id, **kwargs):
        return create_envelope(
            from_agent="finance_head", to_agent="brownie",
            payload={"message": "dummy handler ran fine", "kwargs_received": kwargs},
            task_id=task_id, run_id=run_id
        )

    brownie.register_capability("finance.reconcile", dummy_handler)
    result = brownie.submit_task("finance.reconcile", data_dir="data")
    print(f"Status: {result['status']}")
    print(f"Payload: {result['payload']}")
    print(f"Task status lookup: {brownie.get_task_status(result['payload']['task_id'])}\n")

    # --- Test 3: handler that crashes unexpectedly ---
    print("=== TEST 3: Handler crashes unexpectedly ===")

    def crashing_handler(task_id, run_id, **kwargs):
        raise RuntimeError("Something totally unexpected broke")

    brownie.register_capability("finance.broken_test", crashing_handler)
    result = brownie.submit_task("finance.broken_test")
    print(f"Status: {result['status']}, error: {result['payload'].get('error_message')}")

    print("\n=== TEST 4: Real Finance Head (requires LangGraph) ===")
    try:
        from finance_head import run_finance_head
        brownie.register_capability("finance.reconcile", run_finance_head)
        result = brownie.submit_task("finance.reconcile", data_dir="data")
        print(f"Status: {result['status']}")
        print(f"Payload: {result['payload']}")
    except ImportError as e:
        print(f"Skipped - LangGraph not available in this environment ({e})")
        print("Run this test on your machine to verify the real end-to-end flow.")