"""Temporal worker — runs workflows and activities.

Start alongside the FastAPI server:

    python -m workers.worker

Connects to Temporal, auto-creates the namespace (idempotent, survives
scale-from-zero), registers the workflow + activities, then polls the task
queue. Run multiple processes for horizontal scaling.
"""
from __future__ import annotations

import asyncio
import signal
import sys
from datetime import timedelta

from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode
from temporalio.worker import Worker

from observability.tracing import init_tracing
from shared.config import get_settings
from shared.logger import get_logger, setup_logging
from workflows.activities import (
    persist_session_to_db,
    run_agent_turn,
    send_status_notification,
)
from workflows.example_workflow import ExampleWorkflow

log = get_logger(__name__)


async def _ensure_namespace(host: str, namespace: str, *, tls: bool = False) -> None:
    """Register the namespace if missing. Never blocks worker startup."""
    try:
        from temporalio.api.workflowservice.v1 import RegisterNamespaceRequest

        admin = await Client.connect(host, namespace="default", tls=tls)
        await admin.service_client.workflow_service.register_namespace(
            RegisterNamespaceRequest(
                namespace=namespace,
                workflow_execution_retention_period=timedelta(days=30),
            )
        )
        log.info("namespace_created", namespace=namespace)
    except RPCError as exc:
        if exc.status == RPCStatusCode.ALREADY_EXISTS:
            log.info("namespace_already_exists", namespace=namespace)
        else:
            log.warning("namespace_create_failed", namespace=namespace, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        log.warning("namespace_create_failed", namespace=namespace, error=str(exc))


async def run_worker() -> None:
    settings = get_settings()
    log.info(
        "worker_connecting",
        temporal_host=settings.temporal_host,
        namespace=settings.temporal_namespace,
        task_queue=settings.temporal_task_queue_agents,
    )

    # ACA serves gRPC over TLS on port 443. Local dev uses plain gRPC on 7233.
    use_tls = settings.temporal_host.endswith(":443")
    await _ensure_namespace(settings.temporal_host, settings.temporal_namespace, tls=use_tls)

    client = await Client.connect(
        settings.temporal_host, namespace=settings.temporal_namespace, tls=use_tls
    )

    async with Worker(
        client,
        task_queue=settings.temporal_task_queue_agents,
        workflows=[ExampleWorkflow],
        activities=[
            run_agent_turn,
            persist_session_to_db,
            send_status_notification,
        ],
        max_concurrent_activities=10,
        max_concurrent_workflow_tasks=50,
    ):
        log.info("worker_started", task_queue=settings.temporal_task_queue_agents)

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        def _stop(*_: object) -> None:
            log.info("worker_shutdown_signal_received")
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _stop)

        await stop_event.wait()
        log.info("worker_stopped")


def main() -> None:
    setup_logging()
    init_tracing(service_name="__APP_NAME__-worker")
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
