"""OpenAPI 문서 후처리: 스키마 컴포넌트를 계약 JSON Schema(1.3 생성물)와 같게 맞춘다.

FastAPI는 같은 Pydantic 모델로 컴포넌트를 만들지만 필드 제목(`"Node Id"`) 등이 계약 생성기
(`agent_console_contracts.build_schema`)와 다르다. 이름이 같은 컴포넌트는 계약 `$defs` 항목으로
바꾸고(`$ref`만 `#/components/schemas/`로), 그 항목이 참조하는 정의도 함께 넣는다.
타입 생성은 계약 JSON Schema 한 곳에서 한다(§5.7). OpenAPI는 문서·탐색용이다.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from agent_console_contracts import CONTRACTS_VERSION, build_schema

CONTRACT_REF_PREFIX = "#/$defs/"
OPENAPI_REF_PREFIX = "#/components/schemas/"
FASTAPI_VALIDATION_SCHEMAS = ("HTTPValidationError", "ValidationError")
"""FastAPI 기본 422 형식. 이 서버는 계약 `ErrorResponse`로 보내므로 문서에서 지운다."""
TOKEN_SCHEME = "ConsoleToken"
UNSAFE_OPERATIONS = frozenset({"post", "put", "patch", "delete"})


def rebase_refs(node: Any, source: str, target: str) -> Any:
    """`$ref` 접두어를 바꾼 사본(JSON 값 재귀)."""
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and value.startswith(source):
                out[key] = target + value[len(source) :]
            else:
                out[key] = rebase_refs(value, source, target)
        return out
    if isinstance(node, list):
        return [rebase_refs(v, source, target) for v in node]
    return node


def _refs(node: Any, prefix: str) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and value.startswith(prefix):
                found.add(value[len(prefix) :])
            else:
                found |= _refs(value, prefix)
    elif isinstance(node, list):
        for value in node:
            found |= _refs(value, prefix)
    return found


def align_components(schemas: dict[str, Any], contract_defs: Mapping[str, Any]) -> None:
    """이름이 계약에 있는 컴포넌트를 계약 정의로 바꾸고, 참조된 계약 정의를 빠짐없이 넣는다."""
    for name in list(schemas):
        if name in contract_defs:
            schemas[name] = rebase_refs(
                copy.deepcopy(contract_defs[name]), CONTRACT_REF_PREFIX, OPENAPI_REF_PREFIX
            )
    pending = set().union(*(_refs(s, OPENAPI_REF_PREFIX) for s in schemas.values()))
    while missing := {n for n in pending if n not in schemas and n in contract_defs}:
        for name in missing:
            schemas[name] = rebase_refs(
                copy.deepcopy(contract_defs[name]), CONTRACT_REF_PREFIX, OPENAPI_REF_PREFIX
            )
        pending = set().union(*(_refs(schemas[n], OPENAPI_REF_PREFIX) for n in missing))


def build_openapi(app: FastAPI) -> dict[str, Any]:
    """앱의 OpenAPI 문서(캐시). 422도 `ErrorResponse`, 변경 요청에 토큰 보안 스킴 표기."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        separate_input_output_schemas=False,
    )
    error_ref = {"$ref": OPENAPI_REF_PREFIX + "ErrorResponse"}
    for path_item in schema.get("paths", {}).values():
        for method, operation in path_item.items():
            if not isinstance(operation, dict):
                continue
            response = operation.get("responses", {}).get("422")
            if response is not None:
                response["content"] = {"application/json": {"schema": error_ref}}
                response["description"] = "validation_failed"
            if method in UNSAFE_OPERATIONS:
                operation["security"] = [{TOKEN_SCHEME: []}]
    components = schema.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    for name in FASTAPI_VALIDATION_SCHEMAS:
        schemas.pop(name, None)
    align_components(schemas, build_schema()["$defs"])
    components["schemas"] = {name: schemas[name] for name in sorted(schemas)}
    components["securitySchemes"] = {
        TOKEN_SCHEME: {"type": "apiKey", "in": "header", "name": "X-Console-Token"}
    }
    schema["x-contracts-version"] = CONTRACTS_VERSION
    app.openapi_schema = schema
    return schema
