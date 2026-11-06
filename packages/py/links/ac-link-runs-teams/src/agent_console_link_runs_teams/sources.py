"""Run 하나의 정의 조회 출처(5.7R.33y) → 노드 서비스용 조회 함수 묶음.

``mod-runs``가 실행 범위(``runs.scopes``의 ``run_definitions``)로 Run의 정의 출처를 정하면 그 출처를
실행 환경 ``RunEnvironment.definitions``와 노드 서비스 ``RUN_DEFINITIONS``로 넘긴다. 이 모듈은 그
출처 하나로 에이전트·팀 구성(고정 버전 포함)·리소스(본문·여러 파일 포함) 조회를 만든다. 출처에
없으면 "없음"이다(다른 출처로 넘어가 찾지 않는다).

출처는 ``agent_console_store`` 정의 저장소의 읽기 메서드(``get``·``get_version``·``read_content``·
``list_files``·``read_file``)를 가진 객체면 된다.

>>> from agent_console_store import DEFAULT_KINDS, InMemoryDefinitionStore
>>> store = InMemoryDefinitionStore(DEFAULT_KINDS)
>>> _ = store.create("agent", {"id": "a", "name": "A", "system_prompt": "hi"})
>>> found = lookups_from(store)
>>> found.find_agent("a").name, found.find_agent("ghost")
('A', None)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from agent_console_contracts import Agent, Graph, Resource
from agent_console_nodes_core import FunctionResources
from agent_console_resources import ResourceLookup
from agent_console_store import AGENT_KIND, GRAPH_KIND, RESOURCE_KIND, StoreError

from .ports import DefinitionSource

__all__ = ["RunLookups", "lookups_from"]

_log = logging.getLogger("agent_console_link_runs_teams")

_MISSING = (StoreError, ValidationError, LookupError, OSError)


@dataclass(frozen=True)
class RunLookups:
    """정의 출처 하나의 조회 함수(노드 서비스 ``AGENT_LOOKUP``·``TEAM_LOOKUP``·``RESOURCE_LOOKUP``).

    Attributes:
        find_agent: 에이전트 id → 정의(없거나 읽을 수 없으면 None).
        find_team: (팀 구성 id, 고정 버전 | None) → 팀 구성(없으면 None).
        resources: 리소스 조회(정의·본문·여러 파일).
    """

    find_agent: Callable[[str], Agent | None]
    find_team: Callable[[str, str | None], Graph | None]
    resources: ResourceLookup


def lookups_from(
    source: DefinitionSource,
    *,
    agent_kind: str = AGENT_KIND.name,
    graph_kind: str = GRAPH_KIND.name,
    resource_kind: str = RESOURCE_KIND.name,
) -> RunLookups:
    """출처 하나에 묶인 조회 함수들. 종류 이름은 인자(기본 = ``agent_console_store`` 기본 종류).

    Args:
        source: Run의 정의 조회 출처.
        agent_kind: 에이전트 정의 종류 이름.
        graph_kind: 팀 구성 정의 종류 이름.
        resource_kind: 리소스 정의 종류 이름.
    """

    def find_agent(agent_id: str) -> Agent | None:
        try:
            return Agent.model_validate(source.get(agent_kind, agent_id).document)
        except _MISSING:
            return None

    def find_team(graph_id: str, version: str | None = None) -> Graph | None:
        try:
            if version is None:
                document: Any = source.get(graph_kind, graph_id).document
            else:
                document = source.get_version(graph_kind, graph_id, version).content
            return Graph.model_validate(document or {})
        except _MISSING:
            _log.debug("팀 구성 읽기 실패: %s@%s", graph_id, version, exc_info=True)
            return None

    def find_resource(ref: str) -> Resource | None:
        try:
            return Resource.model_validate(source.get(resource_kind, ref).document)
        except _MISSING:
            return None

    def read_content(resource: Resource) -> str | bytes | None:
        reader = getattr(source, "read_content", None)
        if reader is None:
            return None
        found: str | bytes | None = reader(resource_kind, resource.id)
        return found

    def read_files(resource: Resource) -> dict[str, bytes] | None:
        lister = getattr(source, "list_files", None)
        reader = getattr(source, "read_file", None)
        if lister is None or reader is None:
            return None
        return {
            f.path: reader(resource_kind, resource.id, f.path)
            for f in lister(resource_kind, resource.id)
        }

    return RunLookups(
        find_agent=find_agent,
        find_team=find_team,
        resources=FunctionResources(find_resource, read_content, read_files),
    )
