"""엔진 시험: 이 공급자로 해석한 비밀 값은 실행 기록(Run·NodeRun·이벤트)에
평문으로 남지 않는다.

엔진의 시험 노드(`agent_console_runtime.testing`)가 비밀 참조를 해석해 이벤트·결과·오류에
그대로 넣고, 엔진이 저장 전에 가린다. 공급자 순서는 엔진이 받은 해석기의 순서다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_console_example_secret_provider import FileSecretProvider
from agent_console_runtime import REDACTED, EnvSecretProvider, SecretResolver
from agent_console_runtime.testing import BUILDERS, Harness, make_harness

VALUE = "file-value-zz52"


def _stored(h: Harness, run_id: str) -> str:
    rec = h.recorder
    parts = [rec.run_docs[run_id].model_dump_json()]
    parts += [n.model_dump_json() for n in rec.runs.list_node_runs(run_id)]
    parts += [e.model_dump_json() for e in rec.events.list(run_id)]
    return "\n".join(parts)


@pytest.mark.parametrize("leak", ["error", "out"])
async def test_value_from_file_is_redacted_in_records(tmp_path: Path, leak: str) -> None:
    path = tmp_path / "secrets.env"
    path.write_text(f"EXAMPLE_TOKEN={VALUE}\n", encoding="utf-8")
    secrets = SecretResolver([EnvSecretProvider({}), FileSecretProvider(path)])
    h = make_harness()
    b = BUILDERS
    graph = b.graph(
        [b.node("a", secret="secret://example_token", leak=leak), b.node("next")],
        [b.edge("a", "next")],
        entries=["a"],
    )
    run = await h.make(secrets=secrets).run(graph)
    stored = _stored(h, run.id) + run.model_dump_json()
    assert VALUE not in stored
    assert REDACTED in stored
    events = [e for e in h.recorder.events.list(run.id) if e.type == "test.secret"]
    assert events
    assert events[0].payload["value"] == REDACTED


def test_environment_wins_over_the_file(tmp_path: Path) -> None:
    path = tmp_path / "secrets.env"
    path.write_text("EXAMPLE_TOKEN=from-file-1\n", encoding="utf-8")
    resolver = SecretResolver(
        [EnvSecretProvider({"EXAMPLE_TOKEN": "from-env-1"}), FileSecretProvider(path)]
    )
    assert resolver.resolve("secret://EXAMPLE_TOKEN") == "from-env-1"
