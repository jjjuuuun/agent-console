# agent-console-link-chat-runs

채팅·실행 연동 모듈(design §3R.1.4 L1~L3). 채팅(`mod-chat`)과 실행(`mod-runs`)을 잇는다.

- **턴 시작**: `chat.turn_launcher` = `runs.starter.start_run(conversation_id=…)`. 대화가 이어 쓸 백엔드 세션은 노드 서비스 `SESSIONS`(`ac-nodes-core`)로 그 Run에만 넘긴다.
- **조회**: `chat.runs`·`chat.run_events`(받은 실행 포트 그대로), `chat.interactions`(`RootInteractions` — 턴의 상호작용을 루트 Run 기준으로 모은다. 중첩 팀의 자식 Run 안에서 열린 요청도 같은 턴에 나온다. 상호작용 포트가 없으면 주지 않는다).
- **세션 이어 쓰기**: `chat.turn_sessions`(`LineageSessions`) — 턴 Run과 그 아래 자식 Run(`runs.reader`의 `list(root_run_id=)`)의 노드 세션을 모은다. 자식 Run 노드는 `parent_node_id` 계보로 경로 키 `"<팀 노드>/<자식 노드>"`(`session_path_key`, 손자는 경로를 이어 붙임)로 기록해, 다음 턴에 노드가 같은 규칙(`child_sessions`)으로 자식 Run에 넘긴다. 팀 구성을 바꾸면 첫 구간이 남은 노드 id인 키만 남는다. 노드 종류 이름은 보지 않는다(Run 계보만).
- **이어 가기**: `runs.resume_handlers`에 대화 턴 처리기(`ConversationResume` → `ChatService.resume_turn`).
- **알림**: `runs.event` 구독 — 상호작용(`interaction.*`)·대기(`run.waiting`·`run.resumed`) 이벤트가 대화 턴의 것이면 `chat.notify`. 자식 Run(`conversation_id` 없음)의 이벤트는 루트 Run(`root_run_id`)의 대화로 알린다.
- **시작**: 저장된 대기열을 `chat.queue_after_restart`대로 처리(`apply_restart_policy`). 조립 순서상 실행 모듈(미종료 Run 정리)·채팅 모듈 뒤에 시작한다.
- **종료**(조립 역순이라 채팅·실행 모듈보다 먼저): 대기열 꺼내기 멈춤(`stop_dispatch`) → 실행 정리(`runs.starter.shutdown()`을 기다림). 그다음 채팅 모듈이 감시를 정리한다. 끊기는 턴 뒤에 대기열을 꺼내지 않는다.
- 이 연동이 꺼지면 대화·기록·대기열은 동작하고 전송만 409 `feature_unavailable`이다(웹 역할 `conversations:runs`).

## 설치

```bash
pip install agent-console-link-chat-runs
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-chat-runs
```

## 최소 사용

테스트용 대화 모듈·가짜 실행 시작(`testing`)과 조립한다. 메시지가 실행 시작 포트로 간다.

```python
>>> import asyncio
>>> from agent_console_contracts import CreateConversationRequest, Graph, PostMessageRequest
>>> from agent_console_modkit import assemble
>>> from agent_console_link_chat_runs import CHAT_CONVERSATIONS, module
>>> from agent_console_link_chat_runs.testing import (
...     LocalRunStarter, local_chat_module, local_runs_module,
... )
>>> starter = LocalRunStarter()
>>> assembly = assemble([
...     module,
...     local_chat_module(graphs=[Graph(id="team", name="팀")]),
...     local_runs_module(starter=starter),
... ])
>>> assembly.order
['local-chat', 'local-runs', 'link-chat-runs']
>>> chat = assembly.port(CHAT_CONVERSATIONS)
>>> async def main():
...     await assembly.start()
...     conv = chat.create(CreateConversationRequest(graph_id="team"))
...     run = await chat.post_message(conv.id, PostMessageRequest(text="안녕"))
...     print(starter.calls[0]["conversation_id"] == conv.id, starter.calls[0]["origin"])
...     await assembly.stop()  # 대기열 멈춤 → 실행 정리 → 대화 감시 정리
...     print(starter.current_run(run.id).status)
>>> asyncio.run(main())
True chat
interrupted

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 포트

| 방향 | 포트 | 모양 |
| --- | --- | --- |
| 필수 | `chat.conversations` | `ChatLike`(`notify`·`resume_turn`·`apply_restart_policy`·`stop_dispatch`) |
| 필수 | `runs.starter` | `RunStarter`(`start_run`·`cancel`·`current_run`·`shutdown`) |
| 필수 | `runs.reader` / `runs.events` | `LineageRunReader`(`get`·`list(…, root_run_id=)`) / 이벤트 조회 |
| 선택 | `interactions.port` | `RootInteractionReader`(`list(…, root_run_id=)`) |
| 구독 | `runs.event` | `RunEvent` |
| 제공 | `chat.turn_launcher` | `RuntimeTurnLauncher` |
| 제공 | `chat.runs` / `chat.run_events` | 받은 포트 그대로 |
| 제공 | `chat.interactions` | `RootInteractions`(루트 기준) |
| 제공 | `chat.turn_sessions` | `LineageSessions`(자식 Run 세션 = 경로 키) |
| 제공(multi) | `runs.resume_handlers` | `ConversationResume` |

## 단독 실행

```bash
python -m agent_console_link_chat_runs [--with ID] [--config PATH] [--port 0] [--check]
```

`--with`가 없으면 `testing.standalone_modules`(메모리 대화 서비스 + 가짜 실행 시작)를 붙인다. 실제 모듈과 함께: `--with mod-chat --with mod-runs --with mod-definitions`.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
