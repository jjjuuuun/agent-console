# agent-console-chat

대화(채팅) 서비스. 팀 구성(그래프) 하나를 골라 이어 가는 대화를 만들고, 메시지마다 턴(Run)을 시작하고,
턴 목록을 Run 기록에서 조립한다. 전송 계층(HTTP·WS·CLI), 저장소, 실행 엔진을 모른다.

- **대화 한 턴 = Run 하나.** 메시지를 따로 저장하지 않는다. 사용자 메시지 = Run 입력, 답변 = `run.reply` 이벤트,
  되묻기·승인·검토 = 그 Run의 상호작용(`ChatTurn.interactions`).
- **실행 중 새 메시지**: 유효 설정 `chat.busy_policy`(공통 → 팀 구성)가 `queue`면 대기열에 넣고 앞 턴이 끝나면 실행,
  `reject`면 `ConversationBusyError`(409 `conversation_busy`). 응답 대기(`waiting`) 중인 턴도 실행 중이다.
  대기열 항목은 `cancel_queued`로 취소한다.
- **세션 이어 쓰기(R4.6)**: 턴이 끝나면 노드별 마지막 `agent.session_started`(`node_path == [노드]`)를 대화 `sessions`에
  저장하고 다음 턴 `TurnStart.sessions`로 넘긴다. 쓸지 말지는 노드의 `session` 정책이 정한다.
  팀 구성을 바꾸면(`update(graph_id=)`) 새 팀 구성에 없는 노드의 세션은 버린다. 무엇을 모으고 키를 어떻게
  붙이는지는 `TurnSessions` 규칙(`collect`·`prune`)이 정한다. 기본 `RootRunSessions`는 위 규칙(턴 Run 자기
  노드, 키 = 노드 id)이고, 중첩 실행(자식 Run)까지 이으려면 조립이 규칙을 주입한다(예:
  `agent-console-link-chat-runs`의 `LineageSessions` — 경로 키 `"<팀 노드>/<자식 노드>"`).
- **턴 마무리 순서(5.2R.39)**: 답변(`run.reply` — 엔진이 Run 종료 상태보다 먼저 저장) → 세션 기록 → 끝난 상태
  공개 → 알림(`listener`). Run이 끝났어도 세션을 기록하기 전에는 `turns()`·`turn()`·요약 `last_status`가 그 턴을
  `running`(종료 시각 없음)으로 보인다. 그래서 끝난 상태가 보이는 턴에는 답변이 모두 들어 있다.
- **대화 제목**: 설정 `chat.title`이 `first_message`면 첫 메시지 앞 `ChatOptions.title_chars`(기본 40)자, `manual`이면 비워 둔다.
- **요약**: `ConversationSummary.last_status`·`queued`·`pending_interactions`. 바뀔 때마다 `listener`를 부른다(서버가 WS
  `conversation.updated`로 내보냄). 상호작용 상태가 바뀌면 앱이 `notify(conversation_id)`를 부른다.
- **대기열 저장(design §2R.10)**: 대기열은 주입한 `QueueStore`에 있다(기본 `MemoryQueue`; 서버는
  `agent_console_mod_chat.storage`의 대기열 저장소(SQLite)를 그대로 넘긴다). 실행 중 표시는 프로세스 메모리에 있다.
  - 재시작 뒤 `await apply_restart_policy()`(시작 시 한 번): 유효 설정 `chat.queue_after_restart`가
    `ask`(기본)면 모든 항목을 멈추고(`held`, 사유 `restart`), `run`이면 순서대로 실행, `drop`이면 지운다.
  - 멈춘 맨 앞 항목은 뒤의 항목을 막는다(순서 보존). `await release_queued(대화, 항목)`으로 풀고
    `cancel_queued`로 지운다. 쉬고 있는데 대기열이 남아 있으면 `queue` 정책의 새 메시지는 그 뒤에 선다.
  - 종료 직전 `stop_dispatch()`(엔진을 멈추기 전): 끊기는 턴 뒤에 대기열을 꺼내지 않는다. `aclose()`는
    대기열을 지우지 않는다.
- **끊긴 턴 이어 가기**: `await resume_turn(run_id, graph=, seed=)` → 같은 대화의 새 턴(Run, `origin =
  ChatOptions.resume_origin`(기본 `resume`), `resumed_from`, 입력은 원래 턴과 같음). 실행 중이면
  `ConversationBusyError`, 대화의 마지막 턴이 아니면 `TurnNotResumableError`(409 `run_not_resumable`).
  어떤 노드를 다시 실행해도 되는지는 호출자(`ac-runtime.ResumeService`)가 검사한다. `ChatTurn.resumed_from`.

설계 근거: `specs/agent-console/design.md` §R1.4, §R5.1, §R14.4, §R14.7.

## 주입 프로토콜

`ChatService(conversations, graphs, *, launcher=None, runs=None, events=None, interactions=None, settings=, listener=, clock=, ids=, options=, queue=)`.
대화 저장소와 팀 구성 조회만 필수다. **실행 연결**(`launcher`·`runs`·`events`·`interactions`)은 선택이다.

| 프로토콜 | 메서드 | 보통 넘기는 것 | 없으면 |
| --- | --- | --- | --- |
| `ConversationRepository`(필수) | `get`, `save`, `delete`, `list(graph_id=, archived=)` | 저장소 대화 리포지토리 | — |
| `GraphLookup`(필수) | `get_graph(graph_id)` | 정의 저장소 위 함수 하나 | — |
| `TurnLauncher` | `async start_turn(TurnStart) -> TurnHandle`, `cancel(run_id, reason)` | `GraphRuntime`을 감싼 얇은 어댑터(`TurnStart.sessions`를 노드 서비스로, `conversation_id`·`origin`을 Run에) | 전송·이어 가기 `ChatFeatureUnavailableError`, 대기열은 꺼내지 않고 남긴다 |
| `TurnHandle` | `run_id`, `run`, `async wait()` | `GraphRuntime.start()`의 `RunHandle` 그대로 | — |
| `RunReader` | `get`, `list(conversation_id=, limit=)`(최신순) | 저장소 Run 리포지토리 | 턴 목록이 비고 마지막 상태는 null |
| `EventReader` | `list(run_id, since_seq=, limit=)` | 저장소 이벤트 리포지토리 | 답변·세션을 읽지 않는다 |
| `InteractionReader` | `list(run_id=, conversation_id=, status=)` | 저장소 상호작용 리포지토리 | 턴의 상호작용이 비고 대기 수는 0 |
| `TurnSessions` | `collect(run)`, `prune(sessions, node_ids)` | 실행 연동이 주는 세션 규칙 | 기본 `RootRunSessions(events)` |
| `ChatSettingsResolver` | `(graph) -> ChatSettings` | `layered_chat_settings(lambda: workspace.chat)` |
| `QueueStore`(선택) | `enqueue`·`get`·`list`·`remove`·`hold_all`·`release`·`pop_next`·`counts`·`clear` | `mod-chat`의 대기열 저장소(없으면 `MemoryQueue`) |

`agent_console_chat.testing`에 위 프로토콜의 인메모리 예제 구현과 가짜 실행기(`FakeLauncher`)가 있다.
조립 순서상 서비스를 먼저 만들고 실행 연결을 나중에 아는 조립기(서버 모듈)는 턴을 시작하기 전에
`connect(launcher=, runs=, events=, interactions=, sessions=)`를 한 번 부른다(`can_send`로 전송 가능 여부를 본다).

## 설치

```bash
uv sync --all-packages                   # 워크스페이스 안에서
uv pip install ./packages/py/features/ac-chat     # 다른 프로젝트에서 단독으로(ac-contracts 필요)
```

## 최소 사용 예

```python
>>> import asyncio
>>> from agent_console_chat import ChatService, layered_chat_settings
>>> from agent_console_chat.testing import (
...     FakeLauncher,
...     MemoryConversations,
...     MemoryEvents,
...     MemoryGraphs,
...     MemoryInteractions,
...     MemoryRuns,
... )
>>> from agent_console_contracts import CreateConversationRequest, Graph, NodeSpec, PostMessageRequest

>>> async def main():
...     runs, events = MemoryRuns(), MemoryEvents()
...     launcher = FakeLauncher(runs, events)  # 실제로는 엔진(GraphRuntime) 어댑터
...     chat = ChatService(
...         MemoryConversations(),
...         MemoryGraphs([Graph(id="team", name="팀", nodes=[NodeSpec(id="pl", type="agent")])]),
...         launcher=launcher,
...         runs=runs,
...         events=events,
...         interactions=MemoryInteractions(),
...         settings=layered_chat_settings(),
...     )
...     conv = chat.create(CreateConversationRequest(graph_id="team"))
...     run = await chat.post_message(conv.id, PostMessageRequest(text="로그인 화면 만들어 줘"))
...     queued = await chat.post_message(conv.id, PostMessageRequest(text="그리고 테스트도"))
...     print(type(run).__name__, type(queued).__name__, queued.position)  # 실행 중이면 대기열로
...     launcher.finish(run.id)  # 실제로는 엔진이 끝냄 → 대기열 다음 메시지가 자동 시작
...     second = await launcher.wait_started(2)
...     launcher.finish(second.run_id)
...     await chat.wait_idle(conv.id)
...     for turn in chat.turns(conv.id):  # ChatTurn[] (오래된 순)
...         print(turn.run_id, turn.user_text, turn.status)
>>> asyncio.run(main())
Run QueuedMessage 1
run-1 로그인 화면 만들어 줘 completed
run-2 그리고 테스트도 completed

```

실행 연결 없이도 대화·대기열은 동작한다. 전송만 `ChatFeatureUnavailableError`(`code = feature_unavailable`)다.

```python
>>> from agent_console_chat import ChatFeatureUnavailableError
>>> chat = ChatService(MemoryConversations(), MemoryGraphs([Graph(id="team", name="팀")]))
>>> conv = chat.create(CreateConversationRequest(graph_id="team"))
>>> [c.id for c in chat.list()] == [conv.id], chat.turns(conv.id), chat.can_send
(True, [], False)
>>> try:
...     asyncio.run(chat.post_message(conv.id, PostMessageRequest(text="안녕")))
... except ChatFeatureUnavailableError as exc:
...     print(exc.code, exc.details)
feature_unavailable {'dependency': 'launcher'}

```

## 오류

모두 `ChatError`(`code` = 계약 `ErrorCodes`, `details`)의 하위 클래스다.
`ConversationNotFoundError`·`GraphNotFoundError`·`QueuedMessageNotFoundError`·`TurnNotFoundError`(not_found),
`ConversationBusyError`(conversation_busy), `TurnNotResumableError`(run_not_resumable),
`InvalidMessageError`(bad_request), `ChatFeatureUnavailableError`(feature_unavailable, `details.dependency` =
`launcher`·`runs` — 실행 연결이 없음).
실행 엔진이 시작을 거부한 오류(예: 그래프 검증 실패)는 바꾸지 않고 그대로 올린다.

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-chat`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
uv run pytest packages/py/features/ac-chat
```
