"""``POST /logs/index/purge`` 본문·응답 모양(M-3). 모듈 안 모델이다(계약 이동은 검토 대상).

의미는 ``agent_console_logs.purge_index``가 정한다. 출처·범주 이름은 사용자가 주는 데이터다.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from agent_console_logs import PurgeResult

__all__ = ["LogPurgeRequest", "LogPurgeResponse"]

_Name = Annotated[str, Field(min_length=1)]


class LogPurgeRequest(BaseModel):
    """색인 비우기 요청. 주어진 조건을 모두 만족하는 이벤트를 지운다(생략 = 그 조건 없음).

    범위가 하나도 없이 실제로 지우면(``dry_run: false``) 색인 전체가 지워지므로 ``all: true``
    확인이 있어야 한다(없으면 422, CLI ``--all``과 같은 안전장치).
    """

    model_config = ConfigDict(extra="forbid")

    sources: list[_Name] | None = Field(
        default=None, min_length=1, description="이벤트 출처 id 목록(생략 = 모든 출처)."
    )
    categories: list[_Name] | None = Field(
        default=None, min_length=1, description="이벤트 범주 id 목록(생략 = 모든 범주)."
    )
    before: float | None = Field(
        default=None,
        description="이 시각(Unix epoch 초)보다 이른 이벤트만(시각 없으면 색인 시각).",
    )
    rescan: bool = Field(
        default=True,
        description=(
            "범위 출처(없으면 전부)의 커서도 지워 다음 수집이 원본을 다시 읽게 한다. "
            "false면 지운 이벤트가 다시 색인되지 않는다."
        ),
    )
    dry_run: bool = Field(default=True, description="true(기본)면 지우지 않고 지울 행 수만 센다.")
    all: bool = Field(
        default=False,
        description=(
            "범위(출처·범주·시각) 없이 실제로 지울 때(dry_run=false) 필요한 확인 값. "
            "true여야 색인 전체를 지운다."
        ),
    )

    @property
    def unscoped(self) -> bool:
        """범위 조건(출처·범주·시각)이 하나도 없는지."""
        return self.sources is None and self.categories is None and self.before is None

    @property
    def needs_confirmation(self) -> bool:
        """범위 없이 실제로 지우려는데 ``all: true`` 확인이 없는지."""
        return not self.dry_run and self.unscoped and not self.all


class LogPurgeResponse(BaseModel):
    """지운(``dry_run``이면 지울) 행 수."""

    dry_run: bool
    events: int = Field(description="이벤트 수(본문·검색·태그·연결·근거 행은 이벤트를 따른다).")
    usage: int = Field(description="토큰 표본 행 수.")
    cursors: int = Field(description="커서 행 수(다음 수집에서 다시 읽는 단위).")
    agents: int = Field(description="에이전트 표시 행 수.")

    @classmethod
    def of(cls, result: PurgeResult) -> LogPurgeResponse:
        """``PurgeResult`` → 응답."""
        return cls(
            dry_run=result.dry_run,
            events=result.events,
            usage=result.usage,
            cursors=result.cursors,
            agents=result.agents,
        )
