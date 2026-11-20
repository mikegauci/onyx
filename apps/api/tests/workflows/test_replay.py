"""Workflow code must replay recorded histories, or running workflows break on deploy.

No database or Temporal server: the Replayer re-runs the workflow code against the events.
A change that fails here needs ``workflow.patched`` (versioning), not a new recording.
"""

import asyncio
from pathlib import Path

from temporalio.client import WorkflowHistory
from temporalio.worker import Replayer

from app.workflows.workflows import WORKFLOWS

HISTORIES = Path(__file__).parent / "histories"


def test_recorded_histories_replay_against_the_current_code() -> None:
    files = sorted(HISTORIES.glob("*.json"))
    assert files, "no recorded histories"

    async def main() -> None:
        replayer = Replayer(workflows=WORKFLOWS)
        for path in files:
            history = WorkflowHistory.from_json(path.stem, path.read_text())
            await replayer.replay_workflow(history)

    asyncio.run(main())
