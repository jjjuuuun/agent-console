"""계약 0.13.2(6R.19 서버 후속·6R.20k, 더하기만): `runs` 1.8.0·`definitions` 1.7.0.

- `Run.has_children`(선택, null = 서버가 채우지 않음): 목록 페이지 `GET /runs/page`가 행마다
  직접 자식 Run 유무를 채운다. 0.13.1 Run·페이지가 그대로 읽힌다.
"""

from agent_console_contracts import (
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    GraphSessionSummary,
    GraphSummary,
    Run,
    RunPage,
)
from agent_console_contracts.schema import build_schema


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_contracts_version_is_at_least_0_13_2() -> None:
    """0.13.2에서 정한 버전 이상이다(정확한 지금 값은 0.14.4 테스트가 고정한다)."""
    assert _ver(CONTRACTS_VERSION) >= (0, 13, 2)
    assert build_schema()["x-constants"]["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    v0132 = {
        "common": "1.9.0",
        "resources": "1.1.0",
        "logs": "1.2.0",
        "definitions": "1.7.0",
        "runs": "1.8.0",
        "usage": "1.1.0",
        "projects": "3.2.0",
        "chat": "1.3.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.1.0",
        "sdd": "1.1.0",
        "modules": "1.4.0",
    }
    assert set(CONTRACT_VERSIONS) >= set(v0132)
    for sub, version in v0132.items():
        assert _ver(CONTRACT_VERSIONS[sub]) >= _ver(version), sub


def _run(**extra: object) -> dict[str, object]:
    return {
        "id": "r1",
        "graph_id": "g",
        "graph_version": "v",
        "status": "completed",
        "input": {},
        "origin": "api",
        "created_at": 1.0,
        **extra,
    }


def test_has_children_is_optional_and_null_by_default() -> None:
    old = Run.model_validate(_run())
    assert old.has_children is None
    assert "has_children" not in old.model_dump(mode="json", exclude_unset=True)
    assert Run.model_validate(_run(has_children=True)).has_children is True
    page = RunPage.model_validate({"items": [_run(has_children=False)], "source": "project"})
    assert page.items[0].has_children is False


def test_has_children_in_schema_is_not_required() -> None:
    run = build_schema()["$defs"]["Run"]
    assert "has_children" in run["properties"]
    assert "has_children" not in run.get("required", [])


def test_graph_session_summary_is_optional_and_counts_open_values() -> None:
    base = {"id": "g", "name": "G", "version_hash": "h", "node_count": 0, "edge_count": 0}
    old = GraphSummary.model_validate(base)
    assert old.session_summary is None
    assert "session_summary" not in old.model_dump(mode="json", exclude_unset=True)
    summary = GraphSummary.model_validate(
        {**base, "session_summary": {"nodes": 3, "delegated": {"아무-값": 2}}}
    )
    assert summary.session_summary == GraphSessionSummary(nodes=3, delegated={"아무-값": 2})
    schema = build_schema()["$defs"]
    assert "session_summary" not in schema["GraphSummary"].get("required", [])
    assert schema["GraphSessionSummary"]["required"] == ["nodes"]
