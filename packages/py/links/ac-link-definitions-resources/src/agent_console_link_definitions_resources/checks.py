"""저장 전 정의 검사(1R.37·2R.4): 리소스 종류 검사 + 첨부 덮어쓰기 검사.

검사 로직은 패키지에 있다(``ac-resources.validate_resource``, ``ac-teams.attachment_issues``).
여기서는 정의 종류별로 어느 검사를 부를지 고르고, 이슈 path를 요청 문서 기준으로 맞춘다.
공통 설정의 비밀 규칙 정규식 검사는 ``mod-definitions``가 따로 낸다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from agent_console_contracts import Agent, Graph, Issue, Resource, WorkspaceSettings
from agent_console_registry import Registry
from agent_console_resources import Content, ResourceLookup, ResourceType, validate_resource
from agent_console_secret_rules import SecretRules
from agent_console_store import AGENT_KIND, GRAPH_KIND, RESOURCE_KIND, SETTINGS_KIND, StoreError
from agent_console_teams import (
    TeamPlan,
    agent_attachments,
    attachment_issues,
    graph_attachments,
    settings_attachments,
)

from .ports import DefinitionLookup

RESOURCE_CONFIG_POINTER = "/config"
"""리소스 문서에서 config의 위치(종류 검사 이슈 path의 기준)."""


def resource_document_path(path: str | None) -> str:
    """config 기준 JSON Pointer → 리소스 문서 기준(``/env/A`` → ``/config/env/A``)."""
    if not path:
        return RESOURCE_CONFIG_POINTER
    return RESOURCE_CONFIG_POINTER + (path if path.startswith("/") else "/" + path)


class LookupResources:
    """``definitions.lookup`` 위의 ``ResourceLookup``(``resources.lookup``이 없을 때)."""

    def __init__(self, lookup: DefinitionLookup, kind: str = RESOURCE_KIND.name) -> None:
        self._lookup = lookup
        self._kind = kind

    def get_resource(self, ref: str) -> Resource | None:
        try:
            return Resource.model_validate(self._lookup.get(self._kind, ref).document)
        except (StoreError, ValidationError):
            return None

    def read_content(self, resource: Resource) -> Content:
        return None  # 첨부 검사는 config만 본다


@dataclass(frozen=True)
class DefinitionChecker:
    """정의 종류별 저장 전 검사(``definitions.checks`` 하나).

    Attributes:
        types: 지금 리소스 종류 레지스트리.
        resources: 지금 리소스 조회(첨부 ``ref``).
        plan_of: 팀 구성 → ``TeamPlan``(리소스 연결 해석). 해석할 수 없으면 None(연결 검사 생략).
        secret_rules: 지금 비밀 의심 규칙(없으면 기본).
    """

    types: Callable[[], Registry[ResourceType]]
    resources: Callable[[], ResourceLookup]
    plan_of: Callable[[Graph], TeamPlan | None]
    secret_rules: Callable[[], SecretRules | None] = field(default=lambda: None)

    def issues(self, kind: str, document: Mapping[str, Any] | BaseModel) -> list[Issue]:
        """``kind`` 정의 문서의 검사 이슈(path = 문서 기준). 모델에 맞지 않는 문서는 빈 목록
        (모델 검증은 저장소가 따로 한다)."""
        try:
            if kind == RESOURCE_KIND.name:
                resource = _model(Resource, document)
                return [
                    i.model_copy(update={"path": resource_document_path(i.path)})
                    for i in validate_resource(resource, self.types())
                ]
            if kind == AGENT_KIND.name:
                placed = agent_attachments(_model(Agent, document))
            elif kind == GRAPH_KIND.name:
                graph = _model(Graph, document)
                placed = graph_attachments(graph, plan=self.plan_of(graph))
            elif kind == SETTINGS_KIND.name:
                placed = settings_attachments(_model(WorkspaceSettings, document))
            else:
                return []
        except ValidationError:
            return []
        return attachment_issues(
            placed,
            types=self.types(),
            resources=self.resources(),
            secret_rules=self.secret_rules(),
        )


def _model[M: BaseModel](cls: type[M], document: Mapping[str, Any] | BaseModel) -> M:
    if isinstance(document, cls):
        return document
    if isinstance(document, BaseModel):
        return cls.model_validate(document.model_dump(mode="json", exclude_unset=True))
    return cls.model_validate(document)


__all__ = ["DefinitionChecker", "LookupResources", "resource_document_path"]
