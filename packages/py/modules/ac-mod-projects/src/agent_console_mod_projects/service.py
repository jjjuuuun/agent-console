"""프로젝트 경로가 쓰는 동작: 범위 검사·옮기기 계획과 적용·삭제 계획과 삭제(FastAPI를 모른다).

규칙 계산은 순수 패키지 ``ac-projects``가 하고, 여기서는 저장소를 읽고 쓴다. 다른 기능은 함수로
받는다(없으면 그 부분만 꺼진다, design §UX-P.5):

- 정의 읽기가 없으면: 범위 검사·계획에 ``project.definitions_unavailable`` 정보 하나.
- 참조 추출이 없으면: 참조 규칙 대신 ``project.references_unavailable`` 정보(ac-projects).
- 정의 쓰기가 없으면: 옮기기 적용과 "정의가 있는 프로젝트" 삭제가 ``unavailable()`` 오류.
"""

from __future__ import annotations

import copy
import string
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final, Literal

from agent_console_contracts import (
    DefinitionKey,
    DefinitionMove,
    DeletePlan,
    Issue,
    KnownIssueCodes,
    MovePlan,
    MovePlanRequest,
)
from agent_console_projects import (
    CODE_REFERENCES_UNAVAILABLE,
    DEFAULT_MESSAGES,
    References,
    ScopedDefinition,
    UnknownDefinitionError,
    delete_plan,
    move_plan,
    scope_issues,
)
from agent_console_store import SCOPE_FIELD, NotFound

from .definitions import DefinitionSnapshot
from .ports import DefinitionWriter
from .repository import ProjectRepository

CODE_DEFINITIONS_UNAVAILABLE: Final = KnownIssueCodes.PROJECT_DEFINITIONS_UNAVAILABLE
"""정의 읽기 포트가 없어 범위 검사·계획을 하지 못했다(info). 예: 정의 모듈이 꺼짐."""

MODULE_MESSAGES: Mapping[str, str] = {
    CODE_DEFINITIONS_UNAVAILABLE: (
        "정의 기능이 꺼져 있어 프로젝트 범위 검사를 하지 못했습니다. "
        "프로젝트 만들기·고치기는 됩니다."
    ),
}
"""이 모듈이 더하는 기본 문구(설정 ``messages``로 바꾼다)."""

type DeleteMode = Literal["move_to_shared", "delete_definitions"]


def _template(messages: Mapping[str, str], code: str) -> str:
    return string.Template(messages.get(code) or MODULE_MESSAGES.get(code, code)).safe_substitute()


def _involves(issue: Issue, key: tuple[str, str]) -> bool:
    details = issue.details or {}
    if (details.get("kind"), details.get("id")) == key:
        return True
    source = details.get("source")
    return isinstance(source, Mapping) and (source.get("kind"), source.get("id")) == key


class DefinitionsUnavailableError(Exception):
    """정의 쓰기 포트가 없어 할 수 없는 동작(호스트가 409로 바꾸게 모듈이 감싼다)."""


class ProjectService:
    """프로젝트 동작 묶음.

    Args:
        projects: 프로젝트 저장소.
        snapshot: 정의 목록(범위 판단 입력).
        writer: 지금 정의 쓰기 포트(없으면 None).
        references: 지금 참조 추출(없으면 None).
        unavailable: 정의 쓰기가 필요한데 없을 때 던질 예외를 만든다.
        messages: 문구 바꾸기(이슈 코드 → 문구).
    """

    def __init__(
        self,
        projects: ProjectRepository,
        *,
        snapshot: DefinitionSnapshot,
        writer: Callable[[], DefinitionWriter | None] = lambda: None,
        references: Callable[[], References | None] = lambda: None,
        unavailable: Callable[[], Exception] = DefinitionsUnavailableError,
        messages: Mapping[str, str] | None = None,
    ) -> None:
        self.projects = projects
        self.snapshot = snapshot
        self._writer = writer
        self._references = references
        self._unavailable = unavailable
        self._messages = dict(messages or {})

    # ------------------------------------------------------------ 공통

    def _defs_unavailable(self) -> Issue:
        return Issue(
            severity="info",
            code=CODE_DEFINITIONS_UNAVAILABLE,
            message=_template(self._messages, CODE_DEFINITIONS_UNAVAILABLE),
        )

    def _message_table(self) -> Mapping[str, str]:
        return {**DEFAULT_MESSAGES, **MODULE_MESSAGES, **self._messages}

    def _require_writer(self) -> DefinitionWriter:
        writer = self._writer()
        if writer is None:
            raise self._unavailable()
        return writer

    def _require_target(self, to: str | None) -> None:
        if to is not None:
            self.projects.require(to)

    # ------------------------------------------------------------ 범위 검사

    def scope_issues(self) -> list[Issue]:
        """워크스페이스 전체의 범위 이슈(경고·정보)."""
        defs = self.snapshot.get()
        if defs is None:
            return [self._defs_unavailable()]
        return scope_issues(
            defs,
            self.projects.ids(),
            references=self._references(),
            messages=self._message_table(),
        )

    def check(self, kind: str, document: Mapping[str, Any]) -> list[Issue]:
        """저장하려는 정의 문서 하나의 범위 이슈(``definitions.checks``).

        그 정의가 참조하는 쪽·참조되는 쪽 이슈만 낸다. 정의 읽기가 없거나 문서에 ``id``가 없으면
        빈 목록이다(저장을 막지 않는다 — 경고·정보만). 참조 추출이 없으면 범위가 있는 문서에만
        ``project.references_unavailable`` 정보를 단다.
        """
        try:
            current = ScopedDefinition.from_document(kind, document)
        except ValueError:
            return []
        defs = self.snapshot.get()
        if defs is None:
            return []
        merged = [d for d in defs if d.key != current.key] + [current]
        references = self._references()
        found = scope_issues(
            merged,
            self.projects.ids(),
            references=references,
            messages=self._message_table(),
        )
        out: list[Issue] = []
        for issue in found:
            if issue.code == CODE_REFERENCES_UNAVAILABLE:
                if current.project is not None:
                    out.append(issue)
            elif _involves(issue, current.key):
                out.append(issue)
        return out

    # ------------------------------------------------------------ 옮기기

    def move_plan(self, request: MovePlanRequest) -> MovePlan:
        """옮기기 계획(저장하지 않음). ``to`` 프로젝트가 없거나 정의가 없으면 ``NotFound``."""
        self._require_target(request.to)
        defs = self.snapshot.get()
        target = DefinitionKey(kind=request.kind, id=request.id)
        if defs is None:
            return MovePlan(target=target, to=request.to, warnings=[self._defs_unavailable()])
        try:
            return move_plan(
                (request.kind, request.id),
                request.to,
                defs,
                references=self._references(),
                projects=self.projects.ids(),
                messages=self._message_table(),
            )
        except UnknownDefinitionError as exc:
            raise NotFound(str(exc)) from exc

    def apply_moves(self, plan: MovePlan) -> MovePlan:
        """계획의 ``moves``를 적용한다(정의마다 ``project`` 필드 하나를 고쳐 저장).

        이미 그 범위인 정의는 건너뛴다. 정의마다 따로 저장하므로 중간에 실패하면 앞의 것은
        저장된 채 남는다(같은 계획을 다시 보내면 남은 것만 적용된다).

        Returns:
            실제로 바꾼 이동(``from`` = 바꾸기 전 범위)과 적용 뒤 범위 이슈.

        Raises:
            NotFound: 옮길 프로젝트·정의가 없다.
            VersionConflict: 읽은 뒤 다른 저장이 끼었다.
        """
        writer = self._require_writer()
        for target in {m.to for m in plan.moves}:
            self._require_target(target)
        applied: list[DefinitionMove] = []
        try:
            for move in plan.moves:
                done = self._apply_one(writer, move.kind, move.id, move.to, required=move.required)
                if done is not None:
                    applied.append(done)
        finally:
            self.snapshot.invalidate()
        moved = {(m.kind, m.id) for m in applied}
        warnings = [
            i
            for i in self.scope_issues()
            if any(_involves(i, key) for key in moved) or i.code == CODE_DEFINITIONS_UNAVAILABLE
        ]
        return MovePlan(target=plan.target, to=plan.to, moves=applied, warnings=warnings)

    def _apply_one(
        self, writer: DefinitionWriter, kind: str, def_id: str, to: str | None, *, required: bool
    ) -> DefinitionMove | None:
        stored = writer.get(kind, def_id)
        document = copy.deepcopy(stored.document)
        before = document.get(SCOPE_FIELD) or None
        if before == to:
            return None
        if to is None:
            document.pop(SCOPE_FIELD, None)
        else:
            document[SCOPE_FIELD] = to
        writer.save(
            kind,
            document,
            expected_version=stored.version_hash,
            message=f"project: {before or '(shared)'} -> {to or '(shared)'}",
        )
        name = document.get("name")
        return DefinitionMove.model_validate(
            {
                "kind": kind,
                "id": def_id,
                "name": name if isinstance(name, str) else "",
                "from": before,
                "to": to,
                "required": required,
            }
        )

    # ------------------------------------------------------------ 삭제

    def delete_plan(self, project_id: str) -> DeletePlan:
        """삭제하면 바뀌는 것(저장하지 않음). 프로젝트가 없으면 ``NotFound``."""
        self.projects.require(project_id)
        defs = self.snapshot.get()
        if defs is None:
            return DeletePlan(project_id=project_id, warnings=[self._defs_unavailable()])
        return delete_plan(project_id, defs)

    def delete(
        self,
        project_id: str,
        *,
        mode: DeleteMode = "move_to_shared",
        expected_version: str | None = None,
    ) -> DeletePlan:
        """프로젝트 삭제. 그 프로젝트 전용 정의는 ``mode``대로 공용으로 옮기거나 함께 지운다.

        실행·대화의 ``project_id``는 건드리지 않는다(화면에 "삭제된 프로젝트"). 정의 읽기가
        없으면 정의는 그대로 두고(없는 프로젝트를 가리키므로 공용으로 보인다) 프로젝트만 지운다.

        Returns:
            처리한 정의 목록(``definitions``)과 정보 이슈.

        Raises:
            NotFound: 프로젝트가 없다.
            VersionConflict: ``expected_version``이 지금 버전과 다르다(정의는 건드리지 않음).
        """
        stored = self.projects.get(project_id)
        if expected_version is not None and expected_version != stored.version_hash:
            self.projects.delete(project_id, expected_version=expected_version)  # 412를 낸다
        plan = self.delete_plan(project_id)
        if plan.definitions:
            writer = self._require_writer()
            try:
                for item in plan.definitions:
                    if mode == "delete_definitions":
                        writer.delete(item.kind, item.id)
                    else:
                        self._apply_one(writer, item.kind, item.id, None, required=True)
            finally:
                self.snapshot.invalidate()
        self.projects.delete(project_id, expected_version=stored.version_hash)
        return plan.model_copy(update={"default_mode": mode})


def issues_payload(issues: Sequence[Issue]) -> list[dict[str, Any]]:
    """이슈 목록 → JSON(``None`` 필드 제외)."""
    return [i.model_dump(mode="json", exclude_none=True) for i in issues]


__all__ = [
    "CODE_DEFINITIONS_UNAVAILABLE",
    "MODULE_MESSAGES",
    "DefinitionsUnavailableError",
    "DeleteMode",
    "ProjectService",
    "issues_payload",
]
