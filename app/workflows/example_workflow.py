"""Example Temporal workflow — durable orchestration of an agent session.

A workflow is deterministic: it may only touch the outside world through
activities. This one runs a single agent turn, then persists the result. Extend
it with signals (to feed user messages mid-run), queries (to read live state),
and timers (for periodic reviews / reminders).
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from workflows.activities import (
        persist_session_to_db,
        run_agent_turn,
        send_status_notification,
    )

_DEFAULT_RETRY = RetryPolicy(maximum_attempts=3)


@workflow.defn
class ExampleWorkflow:
    def __init__(self) -> None:
        self._state: dict[str, Any] = {}

    @workflow.run
    async def run(self, initial_state: dict[str, Any]) -> dict[str, Any]:
        self._state = initial_state
        session_id = self._state.get("session_id", "unknown")

        self._state = await workflow.execute_activity(
            run_agent_turn,
            self._state,
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=_DEFAULT_RETRY,
        )

        await workflow.execute_activity(
            persist_session_to_db,
            args=[session_id, self._state],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=_DEFAULT_RETRY,
        )
        await workflow.execute_activity(
            send_status_notification,
            args=[session_id, self._state.get("step_status", "completed")],
            start_to_close_timeout=timedelta(seconds=30),
        )
        return self._state

    @workflow.query
    def current_state(self) -> dict[str, Any]:
        return self._state
