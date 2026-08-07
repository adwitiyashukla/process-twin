"""Temporal worker entrypoint."""

from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from process_twin.config import get_settings
from process_twin.durability.activities import append_audit, execute_atom, load_workflow_spec
from process_twin.durability.workflows import CaseWorkflow


async def main() -> None:
    settings = get_settings()
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[CaseWorkflow],
        activities=[execute_atom, append_audit, load_workflow_spec],
    )
    print(f"worker listening on {settings.temporal_task_queue!r} @ {settings.temporal_address}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
