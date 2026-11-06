"""가짜 파일 접근·검증 출처·작업 연동과 메모리 저장소 조립(테스트용, 실제 연동이 아니다)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts.constants import ErrorCodes
from agent_console_contracts.definitions import Issue
from agent_console_contracts.sdd import (
    KnownTaskLinkKinds,
    ParsedTask,
    TaskAction,
    TaskActionResult,
    TaskLink,
    VerificationResult,
)
from agent_console_sdd._files import SpecFileEntry, check_project_path
from agent_console_sdd._integrations import SpecContext, VerificationContext
from agent_console_sdd._repository import SpecRepository
from agent_console_sdd._templates import definition_kinds
from agent_console_store import InMemoryDefinitionStore

__all__ = [
    "TEST_SPEC_KIND",
    "TEST_TEMPLATE_KIND",
    "FakeTaskIntegration",
    "FakeVerificationSource",
    "MemorySpecFiles",
    "memory_repository",
]

TEST_SPEC_KIND = "test-spec"
"""테스트 저장소의 스펙 종류 이름(실제 이름은 `mod-sdd` 데이터)."""
TEST_TEMPLATE_KIND = "test-spec-template"
"""테스트 저장소의 문서 틀 종류 이름."""


class MemorySpecFiles:
    """메모리 `SpecFiles`. `links`에 든 경로(폴더·파일)는 링크로 본다."""

    def __init__(
        self, files: Mapping[str, bytes | str] | None = None, *, links: Iterable[str] = ()
    ) -> None:
        self.files: dict[str, bytes] = {
            k: v.encode("utf-8") if isinstance(v, str) else bytes(v)
            for k, v in (files or {}).items()
        }
        self.links = set(links)
        self.writes: list[str] = []

    def _dirs(self) -> set[str]:
        out = {""}
        for path in [*self.files, *self.links]:
            parts = path.split("/")
            for i in range(1, len(parts)):
                out.add("/".join(parts[:i]))
        return out

    def read(self, path: str) -> bytes | None:
        norm = check_project_path(path)
        return self.files.get(norm)

    def write(self, path: str, data: bytes) -> None:
        norm = check_project_path(path)
        if norm in self._dirs():
            raise IsADirectoryError(path)
        self.files[norm] = bytes(data)
        self.writes.append(norm)

    def exists(self, path: str) -> bool:
        norm = check_project_path(path, allow_root=True)
        return norm in self.files or norm in self._dirs()

    def is_link(self, path: str) -> bool:
        return check_project_path(path, allow_root=True) in self.links

    def list(self, path: str) -> list[SpecFileEntry]:
        norm = check_project_path(path, allow_root=True)
        if norm in self.files:
            raise NotADirectoryError(path)
        dirs = self._dirs()
        if norm not in dirs:
            raise FileNotFoundError(path)
        prefix = f"{norm}/" if norm else ""
        seen: dict[str, SpecFileEntry] = {}
        for p in [*self.files, *self.links, *dirs]:
            if not p or not p.startswith(prefix) or p == norm:
                continue
            name = p[len(prefix) :].split("/", 1)[0]
            full = prefix + name
            if name in seen:
                continue
            seen[name] = SpecFileEntry(
                name=name,
                is_dir=full in dirs and full not in self.files,
                is_link=full in self.links,
                size=len(self.files.get(full, b"")),
            )
        return list(seen.values())


@dataclass
class FakeVerificationSource:
    """미리 준 결과를 돌려주는 검증 출처(X42 가짜). `calls`에 받은 맥락을 남긴다."""

    results: list[VerificationResult] = field(default_factory=list)
    source_id: str = "fake"
    calls: list[VerificationContext] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.source_id

    async def collect(self, ctx: VerificationContext) -> list[VerificationResult]:
        self.calls.append(ctx)
        return list(self.results)


@dataclass
class FakeTaskIntegration:
    """실행 프로필마다 동작 하나를 내고 부르면 기록만 하는 작업 연동(X43 가짜).

    `invoke`는 `run_id = "<연동 id>-<순번>"`으로 `started`를 돌려주고 `links`에 연결을 더한다.
    """

    integration_id: str = "fake"
    links_data: list[TaskLink] = field(default_factory=list)
    invoked: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.integration_id

    async def actions(self, ctx: SpecContext, task: ParsedTask) -> list[TaskAction]:
        return [
            TaskAction(integration=self.id, id=p.id, label=p.title, purpose=p.purpose)
            for p in ctx.spec.rules.run_profiles or ()
        ]

    async def invoke(
        self, ctx: SpecContext, task: ParsedTask, action: str, args: Mapping[str, Any]
    ) -> TaskActionResult:
        known = {p.id for p in ctx.spec.rules.run_profiles or ()}
        if action not in known:
            return TaskActionResult(
                task_key=task.key,
                status="failed",
                issue=Issue(
                    severity="error",
                    code=ErrorCodes.SDD_ACTION_UNAVAILABLE,
                    message="이 작업에서 쓸 수 없는 동작입니다.",
                ),
            )
        self.invoked.append((task.key, action, dict(args)))
        run_id = f"{self.id}-{len(self.invoked)}"
        self.links_data.append(
            TaskLink(
                integration=self.id,
                kind=KnownTaskLinkKinds.RUN,
                ref=run_id,
                task_key=task.key,
                profile=action,
            )
        )
        return TaskActionResult(task_key=task.key, status="started", run_id=run_id)

    async def links(self, ctx: SpecContext, tasks: Sequence[ParsedTask]) -> list[TaskLink]:
        keys = {t.key for t in tasks}
        return [link for link in self.links_data if link.task_key in keys]


def memory_repository(**kwargs: Any) -> SpecRepository:
    """메모리 정의 저장소 위의 `SpecRepository`(종류 이름 `TEST_SPEC_KIND`·`TEST_TEMPLATE_KIND`).

    `kwargs`는 `SpecRepository`에 그대로 넘긴다(`operators`·`settings`·`clock` 등).
    """
    spec_kind, template_kind = definition_kinds(
        spec_kind=TEST_SPEC_KIND,
        spec_directory="specs",
        template_kind=TEST_TEMPLATE_KIND,
        template_directory="spec-templates",
    )
    store = InMemoryDefinitionStore([spec_kind, template_kind])
    return SpecRepository(
        store, spec_kind=TEST_SPEC_KIND, template_kind=TEST_TEMPLATE_KIND, **kwargs
    )
