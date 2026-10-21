# agent-console-mod-chat

채팅 기능 모듈(design §3R.1.3). 대화 서비스(`ac-chat`)를 서버에 꽂는다.

- 경로: `GET/POST /conversations`, `GET/PATCH/DELETE /conversations/{id}`, `GET /conversations/{id}/turns`, `POST /conversations/{id}/messages`, 대기열(`GET …/queue`, `DELETE …/queue/{queued_id}`, `POST …/queue/{queued_id}/release`).
- WS 토픽: `conversation:<id>`(구독 직후 현재 요약, 이후 바뀔 때마다 `conversation.updated`).
- 턴 실행·Run 조회·상호작용은 **선택 포트**로 받는다(보통 `link-chat-runs`가 준다). 없으면 대화·기록·대기열은 동작하고 메시지 전송만 409 `feature_unavailable{module: mod-chat, port: chat.turn_launcher}`이다. 정의 읽기(`definitions.lookup`)가 없으면 대화 만들기·팀 구성 바꾸기가 409다.
- 저장소: 대화·대기열(`conversations`·`chat_queue`)은 이 모듈이 소유한다(`agent_console_mod_chat.storage`). 호스트의 DB 핸들(`BaseServices.database`, 예: `agent_console_store.SqliteDatabase`) 엔진 위에 만들고, 마이그레이션 계보 `chat`(패키지 데이터 `storage/migrations/versions`)은 모듈이 켜질 때만 올라간다. 테이블은 legacy 0002·0003이 만든 그대로다(변경 없음). 대화를 지우면 대기열도 같은 트랜잭션에서 지운다. DB가 없으면 메모리(경고 `chat.storage_memory`). **legacy는 다운그레이드하지 않는다** — 되돌릴 때는 `chat` 계보만 되돌린다.

## 설치

```bash
pip install agent-console-mod-chat
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-mod-chat
```

## 최소 사용

정의 읽기만 붙이면 대화를 만들고 목록을 볼 수 있다. 턴 실행기가 없으니 전송은 `feature_unavailable`이다.

```python
>>> import asyncio
>>> from types import SimpleNamespace
>>> from agent_console_chat import ChatFeatureUnavailableError
>>> from agent_console_contracts import CreateConversationRequest, PostMessageRequest
>>> from agent_console_modkit import assemble
>>> from agent_console_modkit.testing import fake_module
>>> from agent_console_mod_chat import CHAT_CONVERSATIONS, DEFINITIONS_LOOKUP, module
>>> class Graphs:  # definitions.lookup 모양: get(kind, id).document
...     def get(self, kind, id):
...         return SimpleNamespace(document={"id": id, "name": "팀"})
>>> definitions = fake_module(
...     "my-definitions", provides=[DEFINITIONS_LOOKUP],
...     on_build=lambda ctx: ctx.provide(DEFINITIONS_LOOKUP, Graphs()),
... )
>>> assembly = assemble([module, definitions])
>>> [(r.id, r.state.value) for r in assembly.report]
[('mod-chat', 'active'), ('my-definitions', 'active')]
>>> chat = assembly.port(CHAT_CONVERSATIONS)
>>> async def main():
...     await assembly.start()
...     conv = chat.create(CreateConversationRequest(graph_id="team"))
...     print([c.id for c in chat.list()] == [conv.id], chat.can_send)
...     try:
...         await chat.post_message(conv.id, PostMessageRequest(text="안녕"))
...     except ChatFeatureUnavailableError as exc:
...         print(exc.code)
...     await assembly.stop()
>>> asyncio.run(main())
True False
feature_unavailable

```

실행 연결을 주는 모듈(여기서는 테스트용 가짜 `fake_turns_module`)을 붙이면 메시지가 턴(Run)이 된다.

```python
>>> from agent_console_mod_chat.testing import fake_turns_module
>>> assembly = assemble([module, definitions, fake_turns_module()])
>>> chat = assembly.port(CHAT_CONVERSATIONS)
>>> async def main():
...     await assembly.start()
...     conv = chat.create(CreateConversationRequest(graph_id="team"))
...     run = await chat.post_message(conv.id, PostMessageRequest(text="안녕"))
...     print(run.conversation_id == conv.id, run.status, chat.summary(conv.id).last_status)
...     await assembly.stop()
>>> asyncio.run(main())
True running running

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 포트

| 방향 | 포트 | 모양 |
| --- | --- | --- |
| 제공 | `chat.conversations` | `ChatService`(대화·대기열·턴 조립, `notify`·`resume_turn`·`apply_restart_policy`·`stop_dispatch`·`connect`) |
| 제공(multi) | `server.warnings` | DB가 없으면 `chat.storage_memory` |
| 토픽 | `conversations.updated` | `ConversationSummary` |
| 선택 | `chat.turn_launcher` | `TurnLauncher`(`start_turn`·`cancel`) — 없으면 전송·이어 가기 409 |
| 선택 | `chat.runs` / `chat.run_events` / `chat.interactions` | `RunReader` / `EventReader` / `InteractionReader` — 없으면 턴 목록 빈 값·대기 수 0 |
| 선택 | `chat.turn_sessions` | `TurnSessions`(`collect`·`prune`) — 없으면 기본 규칙(턴 Run 자기 노드만, 키 = 노드 id) |
| 선택 | `definitions.lookup` | `get(kind, id).document` — 없으면 대화 만들기 409 |
| 선택 | `workspace.settings` | `() -> WorkspaceSettings`(`chat.*`) — 없으면 스키마 기본값 |

실행 연결은 이 모듈이 시작할 때 읽는다(`ChatService.connect`). 연결 모듈은 `chat.conversations`가 필수라 조립 순서상 이 모듈보다 뒤에 빌드되기 때문이다. 재시작 대기열 정책(`chat.queue_after_restart`)은 턴 실행기를 주는 연동 모듈이 시작할 때 적용한다(실행기 없이는 대기열을 꺼내지 않고 남긴다).

## 단독 실행

```bash
python -m agent_console_mod_chat [--with ID] [--config PATH] [--port 0] [--check]
```

`--with`가 없으면 `testing.local_definitions_module`(워크스페이스 파일 저장소)을 붙인다. 대화는 `<state>/console.sqlite3`. 턴까지 띄우려면 `--with mod-definitions --with mod-runs --with link-chat-runs`.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
