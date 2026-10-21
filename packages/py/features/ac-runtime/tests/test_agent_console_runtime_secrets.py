"""회귀: 해석된 비밀 값이 저장소(Run·NodeRun·이벤트)에 평문으로 남지 않는다."""

from __future__ import annotations

import pytest

from agent_console_runtime import REDACTED, EnvSecretProvider, SecretResolver
from agent_console_runtime.testing import BUILDERS, Builders, Harness, make_harness

SECRET = "sk-very-secret-value"


@pytest.fixture
def h() -> Harness:
    return make_harness()


@pytest.fixture
def b() -> Builders:
    return BUILDERS


def _dump_all(h: Harness, run_id: str) -> str:
    rec = h.recorder
    parts = [rec.run_docs[run_id].model_dump_json()]
    parts += [n.model_dump_json() for n in rec.runs.list_node_runs(run_id)]
    parts += [e.model_dump_json() for e in rec.events.list(run_id)]
    return "\n".join(parts)


@pytest.mark.parametrize("leak", ["error", "out"])
async def test_resolved_secret_never_stored(h: Harness, b: Builders, leak: str) -> None:
    secrets = SecretResolver([EnvSecretProvider({"API_KEY": SECRET})])
    g = b.graph(
        [b.node("a", secret="secret://api_key", leak=leak), b.node("next")],
        [b.edge("a", "next")],
        entries=["a"],
    )
    run = await h.make(secrets=secrets).run(g)
    stored = _dump_all(h, run.id) + run.model_dump_json()
    assert SECRET not in stored
    assert REDACTED in stored
    if leak == "error":
        saved = h.recorder.run_docs[run.id]
        assert saved.status == "failed"
        assert saved.error is not None
        assert REDACTED in saved.error.message
        node = next(n for n in h.recorder.runs.list_node_runs(run.id) if n.node_id == "a")
        assert node.error is not None
        assert node.error.details == {"k": REDACTED}
    if leak == "out":
        node = next(n for n in h.recorder.runs.list_node_runs(run.id) if n.node_id == "a")
        assert node.outputs == {"out": f"val {REDACTED}"}
        # 하류 노드로는 엔진 메모리 안에서 원래 값이 전달된다(저장본만 가린다).
        assert ("next", {"in": f"val {SECRET}"}) in h.probe.calls


def test_short_secrets_are_not_redacted_but_warned(caplog: pytest.LogCaptureFixture) -> None:
    resolver = SecretResolver([EnvSecretProvider({"SHORT": "ab", "LONG": "abcd"})])
    with caplog.at_level("WARNING", logger="agent_console_runtime._secrets"):
        assert resolver.resolve("secret://short") == "ab"
        resolver.resolve("secret://short")  # 경고는 이름당 한 번
    assert resolver.redact("a table about cabbage") == "a table about cabbage"
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "short" in warnings[0].getMessage()
    assert "'ab'" not in warnings[0].getMessage()
    resolver.resolve("secret://long")
    assert resolver.redact("x abcd y") == f"x {REDACTED} y"
    custom = SecretResolver([EnvSecretProvider({"S": "ab"})], min_redact_chars=2)
    custom.resolve("s")
    assert custom.redact("cab") == f"c{REDACTED}"
