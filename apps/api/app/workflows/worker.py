"""The Temporal worker process: ``python -m app.workflows.worker``.

Runs the workflow and activity worker and the outbox relay until SIGTERM/SIGINT, then drains.
``--check`` connects to Temporal and the database and exits 0, for deploy health checks.

It uses the same image and ``ONYX_API_*`` settings as the API, with the database login that
may enter ``onyx_worker``. No Temporal Cloud namespace or Render worker exists yet; both need
the owner's approval (see ``docs/platform/workflows.md``).
"""

import argparse
import asyncio
import logging
import signal
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from temporalio.client import Client
from temporalio.worker import Worker

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.observability import init_sentry
from app.workflows.activities import Activities, ApprovalActivities
from app.workflows.relay import OutboxRelay
from app.workflows.workflows import WORKFLOWS

logger = logging.getLogger("onyx.workflows.worker")


async def connect(settings: Settings) -> Client:
    return await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)


async def check(settings: Settings) -> None:
    await connect(settings)
    engine = create_async_engine(settings.require_database_url())
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


async def run(settings: Settings) -> None:
    engine = create_async_engine(settings.require_database_url(), pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    client = await connect(settings)
    activities = Activities(sessions)
    relay = OutboxRelay(
        sessions,
        client,
        task_queue=settings.temporal_task_queue,
        batch_size=settings.outbox_batch_size,
        lease_seconds=settings.outbox_lease_seconds,
        max_attempts=settings.outbox_max_attempts,
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=WORKFLOWS,
        activities=[*activities.all(), *ApprovalActivities(sessions).all()],
    )
    logger.info(
        "worker starting",
        extra={
            "fields": {
                "namespace": settings.temporal_namespace,
                "task_queue": settings.temporal_task_queue,
            }
        },
    )
    try:
        async with worker:
            await relay.run_forever(settings.outbox_poll_seconds, stop)
    finally:
        await engine.dispose()
        logger.info("worker stopped")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.workflows.worker")
    parser.add_argument("--check", action="store_true", help="check connections and exit")
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    init_sentry(settings, "worker")
    try:
        asyncio.run(check(settings) if args.check else run(settings))
    except Exception:
        logger.exception("worker failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
