"""대화 서비스가 주입받는 프로토콜(구조적 타이핑).

저장소·실행 엔진을 import하지 않는다. 메서드 이름은 `agent_console_store` 저장소와
`GraphRuntime`에 맞춰 두어 앱이 얇은 어댑터(또는 그대로)로 넘길 수 있게 했다.
"""

import builtins
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from agent_console_contracts import (
    ChatSettings,
    Conversation,
    ConversationSummary,
    Graph,
    Interaction,
    Run,
    RunEvent,
    SessionRef,
)


class ConversationRepository(Protocol):
    """대화 저장소."""

    def get(self, conversation_id: str) -> Conversation | None:
        """대화 하나. 없으면 None."""
        ...

    def save(self, conversation: Conversation) -> None:
        """대화를 저장한다(없으면 만들고 있으면 전체 교체)."""
        ...

    def delete(self, conversation_id: str) -> bool:
        """대화를 지운다. 있었으면 True. 대화의 Run 기록은 지우지 않는다."""
        ...

    def list(
        self,
        *,
        graph_id: str | None = None,
        archived: bool | None = None,
        project_id: str | None = None,
    ) -> builtins.list[Conversation]:
        """필터에 맞는 대화 목록(순서 무관, 서비스가 정렬한다). `project_id`는 불투명 문자열."""
        ...


class RunReader(Protocol):
    """Run 조회(대화 한 턴 = Run 하나)."""

    def get(self, run_id: str) -> Run | None: ...

    def list(
        self, *, conversation_id: str | None = None, limit: int | None = None
    ) -> builtins.list[Run]:
        """대화의 Run 목록. **최신 생성순**(created_at 내림차순)."""
        ...


class EventReader(Protocol):
    """RunEvent 조회(`run.reply`·`agent.session_started`를 읽는다)."""

    def list(self, run_id: str, *, since_seq: int = 0, limit: int | None = None) -> list[RunEvent]:
        """`seq > since_seq`인 이벤트를 seq 오름차순으로."""
        ...


class InteractionReader(Protocol):
    """상호작용 조회(턴의 상호작용 목록, 대화의 대기 수)."""

    def list(
        self,
        *,
        run_id: str | None = None,
        conversation_id: str | None = None,
        status: str | None = None,
    ) -> builtins.list[Interaction]:
        """필터에 맞는 상호작용. 순서는 서비스가 `created_at`으로 다시 정렬한다."""
        ...


class TurnSessions(Protocol):
    """턴이 남긴 백엔드 세션을 모으고, 팀 구성에 맞춰 거르는 규칙.

    대화 `sessions`의 키 모양(노드 id, 또는 중첩 실행의 경로 키)은 이 규칙이 정한다. 서비스는 키를
    해석하지 않고 `collect`의 결과를 저장하고 `prune`으로 거른다. 주입하지 않으면 기본
    `RootRunSessions`(턴 Run 자기 이벤트, 키 = 노드 id)를 쓴다.
    """

    def collect(self, run: Run) -> dict[str, SessionRef]:
        """끝난 턴 Run이 남긴 세션(키 → 마지막 세션). 실패하면 예외 대신 찾은 것만."""
        ...

    def prune(
        self, sessions: Mapping[str, SessionRef], node_ids: Iterable[str]
    ) -> dict[str, SessionRef]:
        """팀 구성 노드(`node_ids`)에 속한 키만 남긴다(팀 구성 전환·노드 삭제 시)."""
        ...


class GraphLookup(Protocol):
    """팀 구성(그래프) 정의 조회."""

    def get_graph(self, graph_id: str) -> Graph | None:
        """정의가 없으면 None."""
        ...


@dataclass(frozen=True, slots=True)
class TurnStart:
    """턴 하나를 시작하라는 요청(실행 엔진 어댑터가 받는다).

    Attributes:
        conversation_id: 대화 id(`Run.conversation_id`로 기록해야 한다).
        graph: 실행할 팀 구성(대화의 현재 `graph_id`로 찾은 정의).
        input: Run 입력(메시지 본문이 `ChatOptions.message_input_key`에 들어 있다).
        text: 사용자 메시지 원문.
        sessions: 노드 id → 이어 쓸 백엔드 세션. 노드가 정책(`session`)에 따라 쓰거나 버린다.
        origin: `Run.origin` 값.
        seed: 이어 가기(§2R.10)면 노드 id → 저장된 입력(`GraphRuntime.start(seed=)`), 아니면 None.
        resumed_from: 이어 가기면 끊긴 원래 Run id(`Run.resumed_from`으로 기록해야 한다).
        project_id: 대화의 프로젝트 id(`Run.project_id`로 기록한다, 5.2R.32). 없으면 None.
    """

    conversation_id: str
    graph: Graph
    input: dict[str, Any]
    text: str
    sessions: dict[str, SessionRef] = field(default_factory=dict)
    origin: str = "chat"
    seed: Mapping[str, Mapping[str, Any]] | None = None
    resumed_from: str | None = None
    project_id: str | None = None


class TurnHandle(Protocol):
    """시작한 턴의 손잡이. `GraphRuntime.start()`의 `RunHandle`이 그대로 만족한다."""

    @property
    def run_id(self) -> str: ...

    @property
    def run(self) -> Run:
        """현재 Run(메모리의 최신 상태)."""
        ...

    async def wait(self) -> Run:
        """Run이 끝날 때까지 기다려 마지막 상태를 돌려준다."""
        ...


class TurnLauncher(Protocol):
    """턴(Run)을 시작·취소하는 실행 엔진 어댑터."""

    async def start_turn(self, turn: TurnStart) -> TurnHandle:
        """Run을 만들고(저장 후) 백그라운드 실행을 시작한다.

        Raises:
            Exception: 그래프 검증 실패 등. 서비스는 그대로 호출자에게 올린다.
        """
        ...

    def cancel(self, run_id: str, reason: str = "cancelled") -> bool:
        """실행 중인 Run을 취소한다. 실행 중이 아니면 False."""
        ...


type ChatSettingsResolver = Callable[[Graph | None], ChatSettings]
"""팀 구성의 유효 채팅 설정(공통 → 팀 구성). 그래프가 없으면 공통 값."""

type ConversationListener = Callable[[ConversationSummary], None]
"""대화 요약이 바뀔 때 부르는 콜백(서버가 WS `conversation.updated`로 내보낸다)."""

type Clock = Callable[[], float]
type IdFactory = Callable[[], str]
