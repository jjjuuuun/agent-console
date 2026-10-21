"""호스트 기본 서비스 기여(modkit 호스트 확장 지점, 3R.16): 레지스트리 묶음과 실행 플러그인 로더.

- ``create_registries``(entry point ``agent_console.host_registries``): 실행 엔진의 레지스트리 묶음
  ``Registries``(노드·엣지·백엔드·비밀 공급자 + 이름 붙은 확장). 호스트가 한 번 만들어 모든 모듈에
  ``registries``로 준다.
- ``load_plugins``(entry point ``agent_console.host_plugin_loaders``): 노드·엣지·백엔드·위임 방식·
  상호작용 종류 그룹(보고 그룹 ``runtime``), 비밀 공급자 그룹, 조건 연산자 그룹(X22, 보고 그룹
  ``condition_operators``, 이름 붙은 확장 레지스트리 ``condition_operators``)을 묶음에 로드한다.
- ``bind_condition_operators``: 등록된 노드·엣지 종류 중 연산자를 쓰는 것(``OperatorConsumer``)에
  묶음의 연산자 레지스트리를 준다. 모듈이 플러그인을 다 읽은 뒤(``build``) 부른다.
- ``bind_redactor``: 등록된 노드·엣지 종류 중 판정 근거를 만드는 것(``RedactorConsumer``)에 엔진
  가림 함수를 준다(자르기 전에 가림, design §5.2R.7). 모듈이 비밀 해석기를 만든 뒤 부른다.

이 모듈이 설정으로 꺼져 있어도 설치되어 있으면 호스트가 부른다(레지스트리는 호스트 기본 서비스다).
"""

from __future__ import annotations

from typing import Any

from agent_console_conditions import (
    CONDITION_OPERATORS_EXTENSION,
    ConditionOperator,
    OperatorConsumer,
    Redactor,
    RedactorConsumer,
    as_condition_operator,
    load_condition_operators,
    operator_map,
)
from agent_console_modkit import PluginLoadContext
from agent_console_registry import LoadReport, Registry, load_entry_points
from agent_console_runtime import (
    SECRET_PROVIDERS_GROUP,
    Registries,
    as_secret_provider,
    load_registries,
)

RUNTIME_REPORT_GROUP = "runtime"
"""실행 확장 지점(노드·엣지·백엔드·위임 방식·상호작용 종류) 보고 그룹 이름."""

CONDITION_OPERATORS_REPORT_GROUP = CONDITION_OPERATORS_EXTENSION
"""조건 연산자(X22) 보고 그룹 이름."""


def condition_operators(registries: Any) -> Registry[ConditionOperator]:
    """묶음의 조건 연산자 레지스트리(이름 붙은 확장, 없으면 만든다)."""
    registry: Registry[ConditionOperator] = registries.extension(
        CONDITION_OPERATORS_EXTENSION, validator=as_condition_operator
    )
    return registry


def load_condition_operator_group(
    registries: Any, *, enabled: set[str] | None = None
) -> list[LoadReport]:
    """조건 연산자 entry point(``agent_console.condition_operators``)를 묶음에 로드한다."""
    return load_condition_operators(condition_operators(registries), enabled=enabled)


def bind_condition_operators(registries: Registries) -> int:
    """연산자를 쓰는 노드·엣지 종류에 묶음의 연산자 레지스트리를 준다(종류 이름은 모른다).

    Returns:
        연결한 확장 수.
    """
    registry = condition_operators(registries)

    def current() -> dict[str, ConditionOperator]:
        return operator_map(registry)

    bound = 0
    for group in (registries.node_types, registries.edge_types):
        for entry in group.list(all_versions=True):
            if isinstance(entry.item, OperatorConsumer):
                entry.item.use_operators(current)
                bound += 1
    return bound


def bind_redactor(registries: Registries, redact: Redactor | None) -> int:
    """판정 근거를 만드는 노드·엣지 종류에 가림 함수를 준다(종류 이름은 모른다).

    Returns:
        연결한 확장 수.
    """
    bound = 0
    for group in (registries.node_types, registries.edge_types):
        for entry in group.list(all_versions=True):
            if isinstance(entry.item, RedactorConsumer):
                entry.item.use_redactor(redact)
                bound += 1
    return bound


def create_registries() -> Registries:
    """빈 실행 레지스트리 묶음."""
    return Registries()


def load_plugins(ctx: PluginLoadContext) -> list[tuple[str, LoadReport]]:
    """실행 확장 지점과 비밀 공급자 entry point를 묶음에 로드한다.

    묶음이 ``Registries``가 아니면(다른 공장이 골라짐) 실패 보고 하나만 돌려준다.
    """
    registries = ctx.registries
    if not isinstance(registries, Registries):
        return [
            (
                RUNTIME_REPORT_GROUP,
                LoadReport(
                    source="host registries",
                    status="failed",
                    error="TypeError: 레지스트리 묶음이 실행 엔진 Registries가 아닙니다",
                ),
            )
        ]
    enabled = set(ctx.enabled) if ctx.enabled is not None else None
    reports = [(RUNTIME_REPORT_GROUP, r) for r in load_registries(registries, enabled=enabled)]
    reports += [
        (SECRET_PROVIDERS_GROUP, r)
        for r in load_entry_points(
            SECRET_PROVIDERS_GROUP,
            registries.secret_providers,
            enabled=enabled,
            validate=as_secret_provider,
        )
    ]
    reports += [
        (CONDITION_OPERATORS_REPORT_GROUP, r)
        for r in load_condition_operator_group(registries, enabled=enabled)
    ]
    return reports


__all__ = [
    "CONDITION_OPERATORS_EXTENSION",
    "CONDITION_OPERATORS_REPORT_GROUP",
    "RUNTIME_REPORT_GROUP",
    "bind_condition_operators",
    "bind_redactor",
    "condition_operators",
    "create_registries",
    "load_condition_operator_group",
    "load_plugins",
]
