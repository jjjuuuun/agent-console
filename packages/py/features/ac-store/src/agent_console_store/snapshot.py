"""RunSnapshot 조립 도우미."""

from agent_console_contracts import RunSnapshot

from .errors import NotFound
from .interfaces import EventRepository, RunRepository


def get_run_snapshot(runs: RunRepository, events: EventRepository, run_id: str) -> RunSnapshot:
    """`GET /runs/{id}` 응답: Run + NodeRun 목록 + 마지막 seq. Run이 없으면 `NotFound`."""
    run = runs.get(run_id)
    if run is None:
        raise NotFound(f"run/{run_id}")
    return RunSnapshot(
        run=run, node_runs=runs.list_node_runs(run_id), last_seq=events.last_seq(run_id)
    )
