"""OpenAPI 문서: §5.2 경로 전부, 스키마 컴포넌트가 계약 JSON Schema 생성물과 같은지(드리프트)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_console_contracts import render_schema
from agent_console_server import create_app
from agent_console_server.testing import make_settings, server

OPENAPI_REF_PREFIX = "#/components/schemas/"

PHASE1_OPERATIONS = {
    ("/api/v1/bootstrap", "get"): "BootstrapResponse",
    ("/api/v1/node-types", "get"): "NodeTypeDescriptor[]",
    ("/api/v1/node-types/{type_id}/ports", "post"): "PortSpec",
    ("/api/v1/edge-types", "get"): "EdgeTypeDescriptor[]",
    ("/api/v1/backends", "get"): "BackendDescriptor[]",
    ("/api/v1/backends/{backend_id}/models", "get"): "ModelInfo[]",
    ("/api/v1/agents", "get"): "Agent[]",
    ("/api/v1/agents", "post"): "Agent",
    ("/api/v1/agents/{agent_id}", "get"): "Agent",
    ("/api/v1/agents/{agent_id}", "put"): "Agent",
    ("/api/v1/agents/{agent_id}", "delete"): None,
    ("/api/v1/graphs", "get"): "GraphSummary[]",
    ("/api/v1/graphs", "post"): "VersionedGraph",
    ("/api/v1/graphs/{graph_id}", "get"): "VersionedGraph",
    ("/api/v1/graphs/{graph_id}", "put"): "VersionedGraph",
    ("/api/v1/graphs/{graph_id}", "delete"): None,
    ("/api/v1/graphs/{graph_id}/validate", "post"): "Issue[]",
    ("/api/v1/graphs/{graph_id}/versions", "get"): "DefinitionVersion[]",
    ("/api/v1/graphs/{graph_id}/versions/{version_hash}", "get"): "DefinitionVersion",
    ("/api/v1/runs", "post"): "Run",
    ("/api/v1/runs", "get"): "Run[]",
    ("/api/v1/runs/{run_id}", "get"): "RunSnapshot",
    ("/api/v1/runs/{run_id}/cancel", "post"): "Run",
    ("/api/v1/settings", "get"): "WorkspaceSettings",
    ("/api/v1/settings", "put"): "WorkspaceSettings",
}


def _openapi(tmp_path: Path) -> dict[str, Any]:
    schema: dict[str, Any] = create_app(make_settings(tmp_path), environ={}).openapi()
    return schema


def _success_schema(operation: dict[str, Any]) -> str | None:
    for status, response in operation["responses"].items():
        if status.startswith("2"):
            content = response.get("content")
            if not content:
                return None
            body = content["application/json"]["schema"]
            if body.get("type") == "array":
                return str(body["items"]["$ref"]).removeprefix(OPENAPI_REF_PREFIX) + "[]"
            return str(body["$ref"]).removeprefix(OPENAPI_REF_PREFIX)
    raise AssertionError(f"성공 응답이 없다: {operation}")


def test_agent_console_server_openapi_covers_phase1(tmp_path: Path) -> None:
    paths = _openapi(tmp_path)["paths"]
    for (path, method), expected in PHASE1_OPERATIONS.items():
        operation = paths[path][method]
        assert _success_schema(operation) == expected, (path, method)
        errors = {s for s in operation["responses"] if not s.startswith("2")}
        for status in errors:
            body = operation["responses"][status]["content"]["application/json"]["schema"]
            assert body == {"$ref": OPENAPI_REF_PREFIX + "ErrorResponse"}, (path, method, status)
        if method in ("post", "put", "delete"):
            assert operation["security"] == [{"ConsoleToken": []}]
    put_graph = paths["/api/v1/graphs/{graph_id}"]["put"]["responses"]
    assert {"412", "428", "422"} <= set(put_graph)


def test_agent_console_server_openapi_matches_contract_schema(tmp_path: Path) -> None:
    """모든 컴포넌트 = 계약 JSON Schema(`render_schema`)의 `$defs` 항목(`$ref` 접두어만 다름).

    커밋된 TS 생성물과의 일치는 `poe contracts-check`·tests/integration이 검사한다.
    """
    defs = json.loads(render_schema())["$defs"]
    components = _openapi(tmp_path)["components"]["schemas"]
    assert "HTTPValidationError" not in components
    outside = sorted(set(components) - set(defs))
    assert outside == [], f"계약 밖 모델이 API에 쓰였다: {outside}"
    for name, component in components.items():
        rebased = json.loads(json.dumps(component).replace(OPENAPI_REF_PREFIX, "#/$defs/"))
        assert rebased == defs[name], name


def test_agent_console_server_openapi_served(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        served = client.get("/api/v1/openapi.json").json()
    assert served["x-contracts-version"]
    assert "/api/v1/graphs" in served["paths"]


BACKEND_READINESS_OPERATIONS = {
    ("/api/v1/backends/status", "get"): "BackendReadiness[]",
    ("/api/v1/backends/{backend_id}/status", "get"): "BackendReadiness",
    ("/api/v1/backends/{backend_id}/probe", "post"): "BackendProbeResult",
}
"""백엔드 준비 상태·연결 테스트(5.2R.67, ux-overhaul §15.8)."""


def test_agent_console_server_openapi_backend_readiness(tmp_path: Path) -> None:
    paths = _openapi(tmp_path)["paths"]
    for (path, method), expected in BACKEND_READINESS_OPERATIONS.items():
        operation = paths[path][method]
        assert _success_schema(operation) == expected, (path, method)
        assert operation.get("description"), (path, method)
    probe = paths["/api/v1/backends/{backend_id}/probe"]["post"]
    assert "409" in probe["responses"]
    assert "backend.probe_unsupported" in probe["description"]
    assert probe["security"] == [{"ConsoleToken": []}]
