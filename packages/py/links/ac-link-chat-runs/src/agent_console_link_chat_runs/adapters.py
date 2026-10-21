"""대화 ↔ 실행 어댑터(HTTP·modkit 없이 쓴다).

- ``RuntimeTurnLauncher``: ``agent_console_chat.TurnLauncher`` = ``runs.starter.start_run``.
  ``TurnStart.sessions``는 노드 서비스 ``SESSIONS``(이 Run에만, ``ac-nodes-core`` 키)로,
  ``conversation_id``·``origin``·``seed``·``resumed_from``은 Run으로 넘긴다.
- ``ConversationResume``: ``runs.resume_handlers`` 항목. 대화 턴이면 같은 대화의 새 턴으로
  이어 간다.
- ``ConversationNotifier``: ``runs.event`` 구독. 상호작용(``interaction.*``)·대기(``run.waiting``·
  ``run.resumed``) 이벤트가 대화 턴의 것이면 대화 요약을 다시 알린다. 자식 Run(중첩 팀,
  ``conversation_id``가 없음)의 이벤트는 루트 Run(``root_run_id``)의 대화로 알린다.
- ``RootInteractions``: ``chat.interactions``. 턴(루트 Run)의 상호작용을 루트 기준으로 모은다 —
  자식 Run 안에서 열린 요청도 같은 턴 카드로 나온다(design §5R.11).
- ``LineageSessions``: ``chat.turn_sessions``. 턴 Run과 그 아래 자식 Run(``root_run_id``)의 노드
  세션을 모아, 자식 Run 것은 ``parent_node_id`` 계보로 경로 키(``session_path_key`` — 손자는 경로를
  이어 붙인다)로 기록한다. 노드가 자식 Run 서비스 ``SESSIONS``에 넘기는 규칙(``child_sessions``)과
  짝이다(design §5R.7). 노드 종류 이름은 보지 않는다(Run 계보만 본다).
"""

from __future__ import annotations

import builtins
from collections.abc import Callable, Collection, Iterable, Mapping

from agent_console_chat import EventReader, TurnHandle, TurnStart, sessions_from_events
from agent_console_contracts import Interaction, Run, RunEvent, SessionRef
from agent_console_nodes_core import SESSIONS, session_path_key
from agent_console_runtime import ResumeStart, session_refs

from .ports import ChatLike, LineageRunReader, RootInteractionReader, RunStarter

INTERACTION_EVENT_PREFIX = "interaction."
RUN_STATE_EVENTS: frozenset[str] = frozenset({"run.waiting", "run.resumed"})
"""대화 요약(마지막 턴 상태)이 바뀌는 실행 이벤트."""


class RuntimeTurnLauncher:
    """대화 턴 시작·취소를 실행 시작 포트에 맡긴다.

    Args:
        starter: ``runs.starter`` 구현.
    """

    def __init__(self, starter: RunStarter) -> None:
        self._starter = starter

    async def start_turn(self, turn: TurnStart) -> TurnHandle:
        extra = {SESSIONS: session_refs(turn.sessions)} if turn.sessions else None
        return await self._starter.start_run(
            turn.graph,
            turn.input,
            origin=turn.origin,
            conversation_id=turn.conversation_id,
            extra_services=extra,
            seed=turn.seed,
            resumed_from=turn.resumed_from,
            project_id=turn.project_id,
        )

    def cancel(self, run_id: str, reason: str = "cancelled") -> bool:
        return bool(self._starter.cancel(run_id, reason))


class ConversationResume:
    """대화 턴(``conversation_id``가 있는 Run)의 이어 가기를 ``resume_turn``으로 맡는다.

    Args:
        chat: 대화 서비스를 돌려주는 함수(없으면 None — 그때는 받지 않는다).
    """

    def __init__(self, chat: Callable[[], ChatLike | None]) -> None:
        self._chat = chat

    def accepts(self, run: Run) -> bool:
        return run.conversation_id is not None and self._chat() is not None

    async def resume(self, request: ResumeStart) -> Run:
        chat = self._chat()
        if chat is None:  # pragma: no cover - accepts가 거른다
            raise RuntimeError("대화 서비스가 없습니다")
        return await chat.resume_turn(request.run.id, graph=request.graph, seed=request.seed)


class ConversationNotifier:
    """``runs.event`` 처리기: 대화 턴의 상호작용·대기 상태가 바뀌면 ``chat.notify``.

    Args:
        chat: 대화 서비스.
        starter: 실행 중 Run 조회(``current_run``).
        prefixes: 알릴 이벤트 형식 접두.
        types: 알릴 이벤트 형식.
    """

    def __init__(
        self,
        chat: ChatLike,
        starter: RunStarter,
        *,
        prefixes: Collection[str] = (INTERACTION_EVENT_PREFIX,),
        types: Collection[str] = RUN_STATE_EVENTS,
    ) -> None:
        self._chat = chat
        self._starter = starter
        self._prefixes = tuple(prefixes)
        self._types = frozenset(types)

    def __call__(self, event: RunEvent) -> None:
        if not (event.type.startswith(self._prefixes) or event.type in self._types):
            return
        run = self._starter.current_run(event.run_id)
        if run is not None and run.conversation_id is None and run.root_run_id is not None:
            run = self._starter.current_run(run.root_run_id)  # 자식 Run → 루트 대화
        if run is not None and run.conversation_id is not None:
            self._chat.notify(run.conversation_id)


class RootInteractions:
    """``chat.interactions``: 턴의 상호작용을 루트 Run 기준으로 모은다.

    ``list(run_id=턴)``은 그 Run과 아래 모든 자식 Run의 상호작용(``root_run_id``)이다. 대화 단위
    조회(``conversation_id``)는 그대로 넘긴다 — 자식 Run 안의 요청도 루트 대화 id를 갖는다.

    Args:
        source: ``interactions.port``(``root_run_id`` 조회가 되는 것).
    """

    def __init__(self, source: RootInteractionReader) -> None:
        self._source = source

    def list(
        self,
        *,
        run_id: str | None = None,
        conversation_id: str | None = None,
        status: str | None = None,
    ) -> builtins.list[Interaction]:
        return self._source.list(root_run_id=run_id, conversation_id=conversation_id, status=status)


class LineageSessions:
    """``chat.turn_sessions``: 턴(루트 Run)과 자식 Run의 노드 세션을 경로 키로 모은다.

    - 루트 Run 노드: 키 = 노드 id(``agent_console_chat.sessions_from_events`` 규칙 그대로).
    - 자식 Run 노드: 키 = ``session_path_key(부모 노드, 노드)``, 손자는
      ``session_path_key(부모 노드, session_path_key(자식 안 부모 노드, 노드))``.
      계보(``parent_run_id``·``parent_node_id``)가 끊긴 Run은 건너뛴다.
    - 같은 키는 나중에 만든 Run이 이긴다(한 턴에 같은 자리가 여러 번 돈 경우).
    - ``prune``: 키가 노드 id이거나 노드 id 경로 접두(``session_path_key(노드, "")``)로 시작하면
      남긴다.

    Args:
        runs: Run 조회(``list(root_run_id=)``).
        events: 이벤트 조회.
    """

    def __init__(self, runs: LineageRunReader, events: EventReader) -> None:
        self._runs = runs
        self._events = events

    def collect(self, run: Run) -> dict[str, SessionRef]:
        found = sessions_from_events(self._events.list(run.id))
        descendants = self._runs.list(root_run_id=run.id, limit=None)
        by_id = {r.id: r for r in descendants}
        for child in sorted(descendants, key=lambda r: (r.created_at, r.id)):
            path = _lineage(child, by_id, run.id)
            if path is None:
                continue
            for key, ref in sessions_from_events(self._events.list(child.id)).items():
                for node in path:  # 안쪽 부모부터 감싼다
                    key = session_path_key(node, key)
                found[key] = ref
        return found

    def prune(
        self, sessions: Mapping[str, SessionRef], node_ids: Iterable[str]
    ) -> dict[str, SessionRef]:
        keep = set(node_ids)
        prefixes = tuple(session_path_key(n, "") for n in keep)
        return {
            key: ref for key, ref in sessions.items() if key in keep or key.startswith(prefixes)
        }


def _lineage(run: Run, by_id: Mapping[str, Run], root_id: str) -> builtins.list[str] | None:
    """자식 Run → 루트까지의 부모 노드 id(안쪽부터). 계보가 끊기거나 돌면 None."""
    path: builtins.list[str] = []
    current = run
    while True:
        if current.parent_node_id is None or current.parent_run_id is None:
            return None
        path.append(current.parent_node_id)
        if current.parent_run_id == root_id:
            return path
        parent = by_id.get(current.parent_run_id)
        if parent is None or len(path) > len(by_id):
            return None
        current = parent


__all__ = [
    "INTERACTION_EVENT_PREFIX",
    "RUN_STATE_EVENTS",
    "ConversationNotifier",
    "ConversationResume",
    "LineageSessions",
    "RootInteractions",
    "RuntimeTurnLauncher",
]
