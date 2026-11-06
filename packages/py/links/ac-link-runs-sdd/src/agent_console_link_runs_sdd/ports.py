"""link-runs-sdd의 포트(이름 = 포트, design §6R.3·§6R.4·§6R.5).

받음(소비자 쪽 프로토콜 — 실행 모듈은 import하지 않고 같은 이름으로 맞춘다. 스펙 모듈은 공개 포트
``agent_console_mod_sdd.ports``만 본다):

- 필수 ``runs.starter``: 실행 시작(``RunStarter`` — ``start_graph``). 선택 메서드
  ``definitions_for``·``find_graph``가 있으면 실행 프로필 그래프 검사(``check_profile``)를 한다.
- 필수 ``runs.reader``: Run 조회(``RunReader`` — ``page``·``get``).
- 필수 ``sdd.service``: 스펙 서비스(``SddServicePort``).
- 토픽 ``runs.event``(구독): 라벨이 있는 루트 Run의 상태 변화 → 실행 프로필 ``status_on`` 반영.

제공:

- ``sdd.integrations``(여러 제공자, X43): ``RunsTaskIntegration``(실행 프로필 = 작업 동작).
- ``sdd.verification_sources``(여러 제공자, X42): ``RunsVerificationSource``(출처 ``runs``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import Run, RunEvent
from agent_console_mod_sdd.ports import (
    LABEL_PROFILE,
    LABEL_PURPOSE,
    LABEL_SPEC,
    LABEL_TASK,
    SDD_INTEGRATIONS,
    SDD_SERVICE,
    SDD_VERIFICATION_SOURCES,
    SddScopeLike,
    SddServicePort,
)
from agent_console_modkit import PortKey, Topic


class RunHandleLike(Protocol):
    """``start_graph`` 결과 모양(``agent_console_runtime.RunHandle``이 만족)."""

    @property
    def run_id(self) -> str: ...


@runtime_checkable
class RunStarter(Protocol):
    """``runs.starter`` 모양(``agent_console_mod_runs.RunService``가 만족).

    선택 메서드(있으면 쓴다):

    - ``definitions_for(project_id, graph_id)``: 그 Run의 정의 조회 출처. 막히면 ``error``
      (``ErrorInfo``) 속성이 있는 예외(예: 422 ``project.not_imported`` — ``details.in_library``).
    - ``find_graph(graph_id, *, project_id)``: 지금 팀 구성(없거나 읽을 수 없으면 None).
    """

    async def start_graph(
        self,
        graph_id: str,
        input: Mapping[str, Any] | None = None,
        *,
        origin: str = ...,
        project_id: str | None = None,
        labels: Mapping[str, str] | None = None,
    ) -> RunHandleLike:
        """저장된 팀 구성을 실행한다(Run을 만들고 바로 돌려준다 — 끝나기를 기다리지 않음)."""
        ...


@runtime_checkable
class RunReader(Protocol):
    """``runs.reader`` 모양(실행 모듈 기록 읽기 — ``RunRepository.page`` 인자)."""

    def page(self, **filters: Any) -> tuple[list[Run], str | None]:
        """커서 페이지(``cursor``·``limit``·``project_id``·``root_only``·``labels``)."""
        ...

    def get(self, run_id: str) -> Run | None: ...


RUNS_STARTER: PortKey[RunStarter] = PortKey("runs.starter", "실행 시작·검증·취소")
RUNS_READER: PortKey[RunReader] = PortKey("runs.reader", "Run·NodeRun 조회")
RUNS_EVENT: Topic[RunEvent] = Topic("runs.event")

__all__ = [
    "LABEL_PROFILE",
    "LABEL_PURPOSE",
    "LABEL_SPEC",
    "LABEL_TASK",
    "RUNS_EVENT",
    "RUNS_READER",
    "RUNS_STARTER",
    "SDD_INTEGRATIONS",
    "SDD_SERVICE",
    "SDD_VERIFICATION_SOURCES",
    "RunHandleLike",
    "RunReader",
    "RunStarter",
    "SddScopeLike",
    "SddServicePort",
]
