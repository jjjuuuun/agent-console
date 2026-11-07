"""정의 경로가 쓰는 동작(저장 전 검사·원문 목록·팀 구성 목록 요약). FastAPI를 모른다."""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ValidationError

from agent_console_contracts import (
    Graph,
    GraphSessionSummary,
    GraphSummary,
    GraphValidationSummary,
    Issue,
)
from agent_console_store import (
    GRAPH_KIND,
    DefinitionCorrupt,
    DefinitionStore,
    InvalidIdentifier,
    NotFound,
    StoredDefinition,
    list_graph_summaries,
)

from .errors import reject_errors
from .ports import (
    DefinitionCheck,
    GraphEntryLabels,
    GraphSessionSummarySource,
    GraphValidationSource,
    SpaceGraphValidationSource,
)

_log = logging.getLogger("agent_console_mod_definitions")


class DefinitionService:
    """정의 경로의 동작 묶음.

    Args:
        store: 정의 저장소.
        checks: 지금 저장 전 검사 목록(부를 때마다 — 늦게 켜진 제공자도 보인다).
        validation: 팀 구성 목록 검증 요약 제공자(없으면 None → 요약 null).
        entry_labels: 팀 구성 입구 이름 제공자(없으면 None → 이름 null).
        session_summary: 팀 구성 세션 집계 제공자(없으면 None → 집계 null).
        space: 이 서비스가 쓰는 공간 이름(None = 라이브러리). 공간이면 검증 요약은 제공자의 선택
            메서드 ``space_summaries``로만 계산한다(없으면 null).
    """

    def __init__(
        self,
        store: DefinitionStore,
        *,
        checks: Callable[[], Sequence[DefinitionCheck]] = lambda: (),
        validation: Callable[[], GraphValidationSource | None] = lambda: None,
        entry_labels: Callable[[], GraphEntryLabels | None] = lambda: None,
        session_summary: Callable[[], GraphSessionSummarySource | None] = lambda: None,
        space: str | None = None,
    ) -> None:
        self.store = store
        self.space = space
        self._checks = checks
        self._validation = validation
        self._entry_labels = entry_labels
        self._session_summary = session_summary

    def issues(self, kind: str, document: Mapping[str, Any] | BaseModel) -> list[Issue]:
        """저장 전 검사 이슈 전부(검사가 없으면 빈 목록)."""
        doc: Mapping[str, Any] = (
            document.model_dump(mode="json", exclude_unset=True)
            if isinstance(document, BaseModel)
            else document
        )
        return [i for check in self._checks() for i in check.issues(kind, doc)]

    def check(self, kind: str, document: Mapping[str, Any] | BaseModel, what: str) -> None:
        """검사에 error가 있으면 ``DefinitionRejectedError``(422)."""
        reject_errors(self.issues(kind, document), what)

    def documents(self, kind: str, model: type[BaseModel]) -> list[dict[str, Any]]:
        """한 종류의 저장 원문 사본 전부(id 순). 읽을 수 없거나 ``model``에 맞지 않으면 뺀다."""
        out: list[dict[str, Any]] = []
        for item_id in self.store.list_ids(kind):
            stored = self._readable(kind, item_id, model)
            if stored is not None:
                out.append(copy.deepcopy(stored.document))
        return out

    def _readable(self, kind: str, item_id: str, model: type[BaseModel]) -> StoredDefinition | None:
        try:
            stored = self.store.get(kind, item_id)
            stored.model(model)
        except (NotFound, DefinitionCorrupt, ValidationError, InvalidIdentifier):
            return None
        return stored

    def graph_summaries(self, *, validate: bool = True) -> list[GraphSummary]:
        """팀 구성 목록: 저장소 요약 + 입구 이름 + 세션 집계 + 검증 요약(각각 제공자가 있을 때)."""
        summaries = list_graph_summaries(self.store)
        validations: Mapping[str, GraphValidationSummary | None] = {}
        source = self._validation() if validate else None
        if source is not None:
            ids = [s.id for s in summaries]
            try:
                if self.space is None:
                    validations = source.summaries(ids)
                elif isinstance(source, SpaceGraphValidationSource):
                    validations = source.space_summaries(self.space, ids, lookup=self.store)
            except Exception:
                _log.exception("팀 구성 검증 요약 실패")
        labeler = self._entry_labels()
        sessions = self._session_summary()
        out: list[GraphSummary] = []
        for summary in summaries:
            labels: list[str] | None = None
            session: GraphSessionSummary | None = None
            if labeler is not None or sessions is not None:
                stored = self._readable(GRAPH_KIND.name, summary.id, Graph)
                graph = stored.model(Graph) if stored is not None else None
                if graph is not None and labeler is not None:
                    try:
                        labels = labeler.entry_labels(graph)
                    except Exception:
                        labels = None
                if graph is not None and sessions is not None:
                    try:
                        session = sessions.session_summary(graph)
                    except Exception:
                        session = None
            out.append(
                summary.model_copy(
                    update={
                        "entry_labels": labels,
                        "validation": validations.get(summary.id),
                        "session_summary": session,
                    }
                )
            )
        return out


__all__ = ["DefinitionService"]
