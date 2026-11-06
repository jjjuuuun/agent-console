"""확장 지점 프로토콜: 검증 결과 출처(X42 `VerificationSource`)와 작업 연동(X43 `TaskIntegration`).

이 패키지는 실행·이슈 트래커·CI를 모른다. 연동 모듈(예: `link-runs-sdd`)과 플러그인이 이 프로토콜을
구현하고, 서버 모듈(`mod-sdd`)이 다중 포트로 모아 부른다. 외부 호출이 있을 수 있어 모두 비동기다.
선택 능력은 따로 둔 프로토콜이고 `isinstance`로 확인한다(`runtime_checkable`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts.sdd import (
    AutomationState,
    EffectiveSyntax,
    ParsedTask,
    RunProfile,
    SpecDefinition,
    SpecIndex,
    SpecIssue,
    TaskAction,
    TaskActionResult,
    TaskLink,
    VerificationResult,
)

from ._files import SpecFiles

__all__ = [
    "AutomationControl",
    "ProfileChecker",
    "SpecContext",
    "TaskIntegration",
    "TaskIssueSource",
    "VerificationContext",
    "VerificationSource",
]


@dataclass(frozen=True, slots=True)
class SpecContext:
    """연동·검증 출처가 받는 스펙 하나의 맥락.

    Attributes:
        space: 공간 이름(REST `?project=`, 단독 루트면 None). 뜻은 공간 제공자만 안다.
        spec: 스펙 정의.
        index: 파싱 결과.
        syntax: 유효 작업 문법.
        version_hash: 스펙 정의 버전.
        directory: 스펙 문서 폴더(프로젝트 폴더 기준 상대 경로 — 입력 틀 `spec_dir`).
        files: 프로젝트 폴더 파일 접근(폴더 안만). 없으면 None.
    """

    space: str | None
    spec: SpecDefinition
    index: SpecIndex
    syntax: EffectiveSyntax
    version_hash: str
    directory: str = ""
    files: SpecFiles | None = None


@dataclass(frozen=True, slots=True)
class VerificationContext:
    """검증 결과 출처(X42) 맥락. `options`는 설정 `sdd.verification_sources[].options`."""

    spec: SpecContext
    options: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class VerificationSource(Protocol):
    """검증 결과 출처(X42). entry point `agent_console.sdd_verification_sources` 또는 다중 포트
    `sdd.verification_sources`로 들어온다. 기본 구현은 `runs`(link-runs-sdd)."""

    @property
    def id(self) -> str:
        """출처 id(`VerificationResult.source`, 설정 `verification_sources[].id`)."""
        ...

    async def collect(self, ctx: VerificationContext) -> list[VerificationResult]:
        """그 스펙의 검증 결과. 파일을 읽는 출처는 `ctx.spec.files`만 쓴다(폴더 안만)."""
        ...


@runtime_checkable
class TaskIntegration(Protocol):
    """작업 연동(X43, 다중 포트 `sdd.integrations`). 기본 구현은 실행(link-runs-sdd).

    선택 능력(따로 둔 프로토콜, 구현하면 쓴다): `ProfileChecker.check_profile`,
    `TaskIssueSource.task_issues`(작업 이슈를 `ParsedTask.issues`에 더함), `AutomationControl`.
    선택 속성 `link_kinds`(이어진 항목 종류, 예: `("run",)`)도 있다.
    """

    @property
    def id(self) -> str:
        """연동 id(`TaskAction.integration`)."""
        ...

    async def actions(self, ctx: SpecContext, task: ParsedTask) -> list[TaskAction]:
        """그 작업에서 고를 수 있는 동작(쓸 수 없으면 `disabled`에 이유)."""
        ...

    async def invoke(
        self, ctx: SpecContext, task: ParsedTask, action: str, args: Mapping[str, Any]
    ) -> TaskActionResult:
        """동작을 실행한다. 관문에 막히면 `status=blocked` + `sdd.gate_blocked` 이슈."""
        ...

    async def links(self, ctx: SpecContext, tasks: Sequence[ParsedTask]) -> list[TaskLink]:
        """작업들과 이어진 항목(한 번에 모아 돌려준다 — 작업마다 질의하지 않는다)."""
        ...


@runtime_checkable
class ProfileChecker(Protocol):
    """선택 능력: 실행 프로필 검사(예: 팀 구성이 공간에 있는지 → `sdd.profile_graph_missing`)."""

    async def check_profile(self, ctx: SpecContext, profile: RunProfile) -> list[SpecIssue]: ...


@runtime_checkable
class TaskIssueSource(Protocol):
    """선택 능력: 작업 이슈(6R.15). 서버 모듈은 작업 목록·스펙 보기를 만들 때 부르고, 돌려준
    이슈를 `task_key`가 같은 작업의 `ParsedTask.issues`에 더한다(`task_key`가 없는 이슈는 버린다).

    예: 실행 결과를 상태에 반영하지 못함 `sdd.status_not_applied`, 자동 진행이 건너뜀
    `sdd.automation_skipped`. 메모리에 둔 상태만 보는 빠른 동기 호출이어야 한다(외부 호출 금지).
    예외를 내면 그 연동의 이슈만 빠진다.
    """

    def task_issues(self, ctx: SpecContext, tasks: Sequence[ParsedTask]) -> list[SpecIssue]: ...


@runtime_checkable
class AutomationControl(Protocol):
    """선택 능력: 자동 진행 상태·멈춤·다시 시작(§6R.18 Q7). 없으면
    `capabilities.automation=false`."""

    def automation_state(self, ctx: SpecContext) -> AutomationState | None: ...

    async def control(self, ctx: SpecContext, op: str) -> AutomationState | None:
        """`op` = stop·resume(열린 문자열). 멈춤은 새 실행만 막고 진행 중 실행은 끊지 않는다."""
        ...
