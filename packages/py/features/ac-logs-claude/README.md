# agent-console-logs-claude

Claude Code 세션 기록(서브에이전트 포함)을 `agent-console-logs`의 정규화 이벤트로 읽는 플러그인.

- X5 출처 `claude-code-jsonl`(`ClaudeCodeJsonlSource`): Claude Code `projects` 폴더에서 세션 파일,
  `<세션>/subagents/**/agent-*.jsonl`, 그 옆 메타 파일(`.meta.json`)을 찾아 증분으로 읽는다.
  **기본 꺼짐**(F-5): 대화 원문이 색인으로 복사되므로 사용자가 켠다.
- X6 분류기 `claude-code`(`ClaudeCodeClassifier`): **행 단위 무상태**(F-7). 응답 묶기·호출 짝·소요
  시간은 질의 때 `message_id`·`call_id`로 계산한다.
- 위임·파일 변경·문서 읽기 도구 이름, 문서 종류, MCP 도구 이름 패턴, 범주 id, 태그, hook 등 행 대응은
  **전부 설정 데이터**다(F-6, `data/classifier_config.schema.json`의 기본값). 코드에 도구 이름 목록이 없다.
- 원본은 **읽기만** 한다. 파일은 주입된 `open_read`로만 연다(메타 파일 포함). `~`·`CLAUDE_CONFIG_DIR`는
  주입된 환경(`LogIngestor(environ=...)`)에서만 풀고, 프로세스 환경을 몰래 읽지 않는다.
- `thinking` 본문(과 서명)은 어디에도 저장하지 않는다. "내부 추론 본문 생략" 표시만 남는다.
- 비밀 의심 값 가림은 수집기(`LogIngestor(redact=...)`)가 저장 직전에 건다.
- 서버·웹 없이 쓴다. `agent_console_logs.LogRegistries().load()`가 entry point로 찾는다.
- **앱에서는 등록된 프로젝트 폴더의 세션만 읽는다**(5.7R.30 후속, 사용자 원칙 "기능은 앱이 만들거나 등록한 프로젝트에
  대해서만"). 수집기가 `LogIngestor(projects=...)`로 `ProjectFolders`(현재·등록된 프로젝트 폴더)를 주면 이 출처의
  `in_scope`가 `projects/<키>/…`의 키를 프로젝트 폴더 이름(`project_key`)과 맞춰 범위 밖 단위를 건너뛴다(메타 파일도
  읽지 않는다). 등록된 프로젝트가 없으면 아무것도 읽지 않는다(홈 전체를 읽는 대체 동작 없음). `roots`를 직접 적어도
  같은 필터가 걸린다. `projects`를 주지 않는 단독 사용은 예전처럼 루트 전체를 읽는다.
- **기본으로 읽는 곳은 두 곳이다**(5.7R.30b, 사용자 결정 2026-10-28 "앱 하나에 로그인 하나"): (a) CLI 세션
  `~/.claude/projects`(또는 `CLAUDE_CONFIG_DIR` 아래, 읽기 전용 — 앱이 `~/.claude`에서 읽는 유일한 예외), (b) 앱이
  실행한 세션 `<앱 workspace>/.state/claude/projects`(앱 전용 구독 자격 폴더 아래, `workspace_roots`). 둘 다 같은 범위
  필터(등록된 프로젝트 폴더 키)를 지난 것만 읽는다. 앱 workspace는 호스트 경로 `LogIngestor(paths={"workspace": …})`
  로 받는다. 프로젝트(작업) 폴더 안은 읽지 않는다.

## 설치

```bash
uv sync --all-packages                                  # 워크스페이스 안
uv pip install ./packages/py/features/ac-logs-claude    # 단독(logs·contracts 함께)
```

| 의존성 | 무엇을 | 왜 | 대안 |
| --- | --- | --- | --- |
| `agent-console-logs` | 출처 기반 클래스 `JsonlFileSource`, 초안·약속 태그, 수집기 | X5·X6 확장 지점의 코어 | — |
| `agent-console-contracts` | 디스크립터·`TokenSample`·`LogDocumentRef` | 계약 단일 소스 | — |

## 최소 사용

임시 폴더에 가짜 Claude Code 설정 폴더를 만들고(같은 응답이 두 행으로 나뉨) 메모리 색인으로 수집한다.

```python
>>> import json, tempfile
>>> from pathlib import Path
>>> from agent_console_contracts.logs import LogSettings
>>> from agent_console_logs import LogFilter, LogIngestor, LogRegistries, query_context
>>> from agent_console_logs.testing import MemoryLogIndex

>>> config_dir = Path(tempfile.mkdtemp())                  # 가짜 CLAUDE_CONFIG_DIR
>>> session = config_dir / "projects" / "-work-demo" / "S1.jsonl"
>>> session.parent.mkdir(parents=True)
>>> def reply(text, output):
...     return {"type": "assistant", "sessionId": "S1", "cwd": "/work/demo",
...             "timestamp": "2026-10-01T00:00:01Z",
...             "message": {"id": "msg_1", "model": "m", "content": [{"type": "text", "text": text}],
...                         "usage": {"input_tokens": 10, "output_tokens": output}}}
>>> rows = [
...     {"type": "user", "sessionId": "S1", "cwd": "/work/demo", "parentUuid": None,
...      "timestamp": "2026-10-01T00:00:00Z", "message": {"content": "문서 정리해 줘"}},
...     reply("네,", 3),
...     reply("정리했습니다.", 8),
... ]
>>> _ = session.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")

>>> registries = LogRegistries()
>>> _ = registries.load()                                   # entry point: claude-code-jsonl, claude-code
>>> index = MemoryLogIndex()
>>> ingestor = LogIngestor(index, registries, environ={"CLAUDE_CONFIG_DIR": str(config_dir)})
>>> settings = LogSettings.model_validate({"sources": [{"id": "claude-code-jsonl", "enabled": True}]})
>>> ingestor.scan(settings).new_events
3
>>> [summary] = index.list_sessions(LogFilter(), query_context(settings))
>>> (summary.title, summary.cwd, summary.tokens.output)    # 같은 응답 msg_1의 토큰은 한 번
('문서 정리해 줘', '/work/demo', 8)

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 출처 설정(`logs.sources[id=claude-code-jsonl].config`)

| 키 | 기본값 | 뜻 |
| --- | --- | --- |
| `project_scope` | `current` | 수집 범위: `current`(현재 프로젝트) / `registered`(등록된 프로젝트 전체). 설정 화면 기본 칸 |
| `workspace_roots` | `[".state/claude/projects"]` | 앱 실행 세션 폴더(앱 workspace 기준 상대 경로, 절대 경로 가능 — 앱 전용 구독 자격 폴더 아래). `roots`가 비었을 때만. 백엔드 `auth_dir.config_dir`를 바꾸면 함께 바꾼다. 5.7R.30의 `project_roots`(프로젝트 안 상대 경로)는 스키마에 `deprecated`로만 남아 읽지 않는다(값이 있으면 앱이 정보 이슈 `logs.ignored_key`) |
| `project_key_keep`·`project_key_replacement` | `""`·`-` | 작업 폴더 → `projects` 아래 폴더 이름 규칙(영문자·숫자·남길 글자 밖은 바꿈 글자로, 예: `/work/demo` → `-work-demo`). Claude Code가 문서로 정하지 않은 규칙이라 바뀌면 고친다 |
| `roots` | `[]` | 읽을 `projects` 폴더 목록. 비면 아래 규칙(CLI 세션) + `workspace_roots`(앱 실행 세션). 적어도 범위 필터는 그대로 |
| `config_dir_env`·`config_dir_subpath` | `CLAUDE_CONFIG_DIR`·`projects` | 주입된 환경에 이 변수가 있으면 그 아래 하위 경로 |
| `default_root` | `~/.claude/projects` | 둘 다 없을 때(`~`는 주입된 `HOME`·`USERPROFILE`) |
| `include` | `*/*.jsonl`, `*/*/subagents/**/agent-*.jsonl` | 루트 기준 글롭 |
| `exclude` | `[]` | 예: 서브에이전트 빼기 `*/*/subagents/**` |
| `subagents_dir`·`meta_suffix` | `subagents`·`.meta.json` | 서브에이전트 폴더·메타 파일 이름 |
| `meta_fields` | `role=/agentType`, `description=/description`, `tool_use_id=/toolUseId` | 메타 JSON에서 꺼낼 값(JSON 포인터) |
| `max_meta_bytes` | 65536 | 이보다 큰 메타 파일은 읽지 않음 |

범위가 바뀌어 이미 색인된 범위 밖 기록이 있으면 수집기가 다음 수집 때 이 출처 색인을 비우고(커서 포함) 범위 안만
처음부터 다시 읽는다(`LogIngestor.scope_purged`). 보존 기간(`retention_days`)은 그 뒤 수집·정리 주기에 그대로 걸린다.
자격 파일(`.credentials.json`)은 포함 패턴(`*.jsonl`) 밖이라 열지 않는다.

`SourceRef.meta`(분류기 맥락): `kind`(`session`·`subagent`), `project`, `session`, `thread`, 서브에이전트면
`parent`·`role`·`description`·`tool_use_id`, 메인 세션이면 `subagents`(위임 호출 id → 서브에이전트 thread).

## 분류기 설정(`logs.sources[].config.classifier.config`)

| 키 | 기본값(요지) | 뜻 |
| --- | --- | --- |
| `categories` | input·llm·tool·mcp·handoff·merge·error·other | 행 종류별 범주 id |
| `tags` | `tool_call`·`tool_result`·`error`·`mcp`·`agent` | 행 종류별 추가 태그(도구 이벤트에는 약속 태그 `tool`이 항상 붙음) |
| `delegation_tools` | `Agent`·`Task`(`/subagent_type`, via `Agent 도구`, 대상 없으면 `role:{value}`) | 위임 도구 |
| `delegation_result` | `/toolUseResult/agentId` | 결과 행에서 서브에이전트 id를 찾을 포인터 |
| `subagent_thread_template` | `agent-{value}` | 서브에이전트 id → thread |
| `file_change_tools` | `Write`(created)·`Edit`·`MultiEdit`(modified)·`NotebookEdit` | 호출 이벤트에 문서(경로·action)를 붙인다 |
| `document_read_tools` | `Read`(`read_requested`) | 읽기 요청 문서 |
| `document_kinds`·`default_document_kind` | `SPEC.md`→spec, `CLAUDE.md`·`CLAUDE.local.md`·`*/.claude/rules/*.md`→rules, `AGENTS.md`→agents_md, `SKILL.md`→skill / document | 파일 이름 또는 경로 글롭(`*`는 `/`도 넘음) → 문서 종류. 파일 이름이 먼저, 그다음 긴 글롭부터. 자동으로 읽힌 지침은 세션 기록에 남지 않으므로 도구로 연 문서만 보인다 |
| `row_correlation` | `request_id` ← `/requestRef` | 행에 값이 있으면 그 행의 모든 이벤트에 붙일 상관 근거(이벤트가 가진 같은 근거가 우선). 응답 행과 같은 요청의 `api-request` 기록(`request_id` ← `/id`)이 명시 id로 이어진다 |
| `mcp_tool_pattern` | `mcp__{server}__{tool}` | 이름 틀(정규식 아님): 자리 표시 `{server}`·`{tool}` 각 한 번 + `*`. 이름 전체가 맞으면 MCP 호출. 빈 문자열이면 MCP를 따로 보지 않음 |
| `session_title_skip_prefixes` | `<command-`·`<local-command-`·`Caveat:` | 세션 제목 후보에서 뺄 입력 |
| `session_title_from_input` | `true` | 끄면 사용자 입력을 세션 제목 후보로 보지 않는다(행 규칙의 `custom-title`·`ai-title` 후보만 남음) |
| `thinking_block_types`·`thinking_note` | `thinking`·`redacted_thinking` / 내부 추론 본문 생략 | 본문을 저장하지 않을 블록 |
| `row_rules`·`extra_row_rules` | 아래 표 | 선언형 행 대응(처음 맞는 규칙이 이김, `extra_row_rules`가 먼저) |
| `summaries` | input·assistant_text → `/text`, tool_call → `/input/description`·`/input/command`·`/input/file_path`…, mcp_call → `{/server}/{/tool} · {/input/description}`…`{/server}/{/tool}`, tool_call 마지막 대체 `{/name} · {/input/id}`·`{/name}`, tool_result·delegation_result → `/output` → "{첫 블록 종류} 블록 N개" → "결과 없음", thinking → `/note` | 행 종류별 목록 요약(평문) 위치(아래 "요약 항목", 앞쪽부터 처음 글이 나오는 것). 못 찾으면 detail 전체 문자열. 원문은 detail·raw에 남고 오류 여부는 상태(`failed`)로 |

행 규칙 하나: `match`(JSON 포인터 → 글롭, 목록이면 하나라도, 참·거짓·숫자는 `true`·`1`로 비교), `category`,
`title`(`{/포인터}` 틀), `stage`, `status`, `fields`(category·stage·status·tool·via·model·message_id·turn_id·role
→ 포인터), `value_maps`(필드 → {원래 값: 바꿀 값}, category는 대응표에 있을 때만 바뀜), `correlation`(근거
→ 포인터), `tags`, `detail`(포인터, 빈 문자열 = 행 전체), `summary`(목록 요약 항목 목록, detail 기준),
`store_raw`(기본 `true`. `false`면 원문을 색인에 넣지 않고 detail·raw를 `keep` 포인터 값 + `omitted`{`bytes`, `sha256`}로
바꾼다 — 크기·해시는 키 정렬·공백 없는 JSON의 UTF-8 기준, 검색에도 원문이 걸리지 않는다. 제목·필드·근거는 원문에서
읽으므로 틀에 본문 포인터를 넣지 않는다), `keep`(남길 값의 포인터, 같은 위치).

요약 항목(`summaries`·행 규칙 `summary`): `/`로 시작하고 `{/`가 없으면 JSON 포인터(문자열 그대로, 내용 블록
목록은 text 블록을 잇는다. 숫자·객체는 평문이 아니라 건너뜀). 그 밖은 틀이다. `{/포인터}`는 그 값(평문·숫자·
참거짓)으로, `{/포인터|keys}`는 객체 키 목록(`, `)으로, `{/포인터|count}`는 목록·객체 항목 수(0 포함)로 바뀐다. 자리 표시가 하나라도 비면 그 틀은 건너뛴다.
자리 표시가 없는 틀은 글자 그대로라서 마지막 대체 문구로 쓴다. 예: hook 첨부는
`["{/hookName} · {/content}", "{/hookName} · {/stdout}", …, "{/hookName} · {/type}"]` → `SessionStart:startup · ok`.

## 지원하는 행

행의 `type`과 내용 블록으로 나눈다. "규칙"은 `row_rules` 기본값(데이터)이고 "코드"는 기록 구조 해석이다.
`thread` = 세션 id(메인) 또는 `agent-<id>`(서브에이전트), `session` = 메인 세션 id, `cwd`·`turn_id`(`promptId`)·
`time`(`timestamp`)은 모든 행에 공통이다.

| 행 | 처리 | 이벤트 |
| --- | --- | --- |
| `assistant` + `text` 블록 | 코드 | `llm` "모델 응답", `message_id`·`model`. 첫 이벤트에 `usage`(TokenSample) |
| `assistant` + `thinking`·`redacted_thinking` | 코드 | `llm` "내부 추론"(본문·서명 없음) |
| `assistant` + `tool_use` | 코드 | `tool`(태그 `tool`·`tool_call`, `call_id`, 단계 `start`). 위임 도구면 `handoff`(from·to·via), MCP 패턴이면 `mcp`(detail `server`·`tool`, 상관 `mcp_server`), 파일·문서 도구면 `documents` |
| `assistant` + `isApiErrorMessage` | 코드 | `error`, 상태 `failed` |
| `user` + 텍스트(문자열 또는 `text` 블록) | 코드 | `input`. 메인 세션은 태그 `session_title`(제목 후보), 서브에이전트 첫 행(`parentUuid: null`)은 "위임 작업 수신"(from 부모, to 자기, 상관 `tool_use_id`) |
| `user` + `tool_result` | 코드 | `tool`(태그 `tool`·`tool_result`, 단계 `complete`, `is_error`면 상태 `failed`·태그 `error`). `toolUseResult.agentId`가 있으면 `merge`(from 서브에이전트, to 자기) |
| `user` + 이미지 등 그 밖의 블록 | 코드 | `input`의 detail에 블록 종류만(본문 없음) |
| `user` + `isMeta: true` | 규칙 | `context` "메타 입력" |
| `system` `compact_boundary`·`microcompact_boundary` | 규칙 | `context` "컨텍스트 압축" |
| `system` `stop_hook_summary` | 규칙 | `hook` "hook 요약 · N개", `preventedContinuation` → 상태 blocked·completed, 요약 `stopReason`·첫 hook 명령 |
| `system` `api_error` | 규칙 | `error` |
| 그 밖의 `system` | 규칙 | `system` "시스템 · {subtype}" |
| `progress` `hook_progress` | 규칙 | `hook` "hook 실행 · {hookName}"(단계 `start`, 상관 `tool_use_id`·`parent_tool_use_id`·`hook_event`), 요약 "hook 이름 · 명령" |
| `progress` `mcp_progress` | 규칙 | `mcp` "MCP 진행 · 서버/도구 · 상태"(상관 `tool_use_id` = 부모 호출), 요약 "서버/도구 · 상태" |
| 그 밖의 `progress` | 규칙 | `other` "진행 · {data.type}" |
| `attachment` `hook_*` | 규칙 | `hook` "hook · {hookName}", 상태 = 종류 대응(`hook_success` completed, `hook_blocking_error` blocked, `hook_non_blocking_error` failed + 범주 `error` …), 요약 "hook 이름 · 출력(content·stdout·stderr, 없으면 종료 코드·종류)" |
| `attachment` 하위 종류별 | 규칙 | `context` "첨부 맥락 · {attachment.type}". 요약: `total_tokens_reminder`·`silent_turn_reminder` → `text`, `edited_text_file`·`compact_file_reference` → "종류 · filename", `deferred_tools_record` → "지연 도구 N개 · 입력 사본 N개", `date` → "날짜 …", `language` → "언어 …", `command_permissions` → "허용 도구 N개" |
| `attachment` `credential*`·`*secret*`·`*password*`·`*auth*` | 규칙 | 요약은 종류만("… (값은 요약에 넣지 않음)"). 비밀 가림(수집기 `redact`)과 별개인 최소 노출 |
| 그 밖의 `attachment` | 규칙 | `context` "첨부 맥락 · {attachment.type}", 요약 = 종류 이름만(모르는 첨부의 본문을 목록에 내놓지 않음) |
| `summary` | 규칙 | `context` "요약 · …" |
| `custom-title`·`ai-title` | 규칙 | `custom-title`은 `other`, `ai-title`은 숨김 범주 `meta`(반복되는 자동 제목 — 타임라인 소음, 5R.19). 제목 = `customTitle`·`aiTitle` 값 그대로(세션 목록 제목으로 쓰이므로 접두어 없음), 요약 "세션 이름(/rename)"·"세션 제목(자동 생성)", 태그 `session_title` + 순위 태그 `session_title.renamed`·`session_title.generated`(아래 우선순위) |
| `agent-name` | 규칙 | `other` "에이전트 이름 · …" |
| `permission-mode`·`mode` | 규칙 | `control`(에이전트 제어) "권한 모드 · {permissionMode}"·"모드 · {mode}" |
| `atis-latch` | 규칙 | `meta`, 요약 "atis {값}"(스칼라일 때만, 아니면 종류) |
| `queue-operation` | 규칙 | `meta` "입력 대기열 · {operation}", 요약 "operation · content" |
| `last-prompt` | 규칙 | `other` "마지막 입력", 요약 `lastPrompt` |
| `file-history-*` | 규칙 | `meta` "파일 기록 · {type}", 요약 = `trackingPath` 또는 스냅샷의 추적 파일 경로 목록(없으면 "추적 파일 없음") |
| `cost-state`·`api-request*` | 규칙 | `meta` "비용 상태"·"API 요청 기록 · {type}" |
| `api-request-blob`(요청 본문) | 규칙 | `meta` "API 요청 기록 · api-request-blob". **원문을 저장하지 않는다**(`store_raw: false`): detail·raw = `type`·`id`·`uuid`·`timestamp`·`sessionId`·`message.role` + `omitted`(크기·sha256), 요약 "요청 본문 저장 안 함 · N바이트". 다시 저장하려면 아래 "요청 본문 저장" |
| `api-request`(요청 메타, Claude Code 2.1.30+) | 규칙 | `meta` "API 요청 · {모델}", `model` ← `/params/model`, 근거 `request_id` ← `/id`, detail = `/params`(모델·`max_tokens`·`thinking` 등 요청 설정, 본문 없음). 같은 요청의 응답 행은 `requestRef`로 같은 `request_id`를 가진다 |
| 모르는 행 | 코드 | `other`(제목 = 행 `type`), 원문 보존 |
| JSON이 아닌 줄 | 코어 | 진단 이벤트(`source = diagnostic`) |

형식 확인(2026-10-17): 공개 자료(커뮤니티 형식 정리, Claude Code hooks 문서)와 agent_bench
`claude_logs.py`로 확인했다. 작업 지시에 따라 실제 `~/.claude`는 읽지 않았다. 확인한 것은 세션 경로,
`subagents/agent-<id>.jsonl`·`.meta.json`(`agentType`·`description`·`toolUseId`), 서브에이전트 행의
`isSidechain`·`agentId`, `progress`의 `data.type = hook_progress`(`hookEvent`·`hookName`·`command`),
`system`의 hook 요약(`stop_hook_summary`)이다. `attachment` 행의 `hook_*` 종류와 `mcp_progress` 필드
이름은 공개 문서로 확인하지 못했다. 그래서 이 부분은 코드가 아니라 기본 규칙 데이터로 두었다. 형식이
바뀌면 `row_rules`나 `extra_row_rules`를 고치면 되고, 코드는 고칠 필요가 없다. 픽스처(`tests/data/claude_config`)는
개인 정보가 없는 합성 파일이다.

세션 제목 우선순위(5R.19): 이 분류기는 후보에 태그만 붙이고, 순위는 코어의 세션 제목 규칙 **데이터**
(`agent-console-logs` `data/default_session_title_rules.yaml`, 모듈 옵션 `mod-logs.session_title_rules`)가 정한다.
기본은 마지막 `session_title.renamed`(`custom-title`) > 마지막 `session_title.generated`(`ai-title`) > 첫
`session_title`(사용자 입력, 명령 표시 등 `session_title_skip_prefixes` 제외)이다. 입력을 후보에서 빼려면
`session_title_from_input: false`.

숨김 범주 `meta`(5R.19): 형식 내부 기록(`ai-title` 반복·`queue-operation`·`atis-latch`·`cost-state`·`api-request*`·
`file-history-*`)은 기본 분류 체계에서 `visible: false`인 `meta`로 보내 타임라인에서 숨긴다. 목록·검색·집계에는
남는다. 보이게 하려면 설정 `logs.taxonomy.categories.meta.visible: true`, 범주를 바꾸려면 `row_rules`를 고친다.

`ai-title`·`custom-title`·`agent-name`·`permission-mode`·`mode`·`queue-operation`·`last-prompt`·`file-history-*`의
필드 이름(`aiTitle`·`customTitle`·`agentName`·`permissionMode`·`mode`·`operation`·`content`·`lastPrompt`·
`trackingPath`·`snapshot.trackedFileBackups`)은 커뮤니티 형식 정리(2026-10-18 확인, 공식 문서 없음)를 따랐고,
`mode` 행의 필드 이름은 확인하지 못했다. 그래서 전부 기본 규칙 데이터이며 형식이 바뀌면 데이터만 고친다.

요청 본문 저장(5.5R.34): Claude Code `api-request-blob` 행에는 모델에 보낸 요청 본문 전체(대화·도구 결과·지침)가
들어 있다. 로그 색인에 같은 내용이 한 번 더 쌓이지 않도록 기본 규칙은 크기·해시만 남긴다. 원문을 다시 색인하려면
같은 행에 맞는 규칙을 `extra_row_rules`에 넣는다(먼저 맞는 규칙이 이긴다, `store_raw` 기본값 `true`):

```yaml
logs:
  sources:
    - id: claude-code-jsonl
      config:
        classifier:
          config:
            extra_row_rules:
              - {match: {/type: api-request-blob}, category: meta, title: "API 요청 본문"}
```

반대로 다른 행의 원문을 끄려면 그 행 규칙에 `store_raw: false`(필요하면 `keep`)를 준다.

설정 변경과 이미 색인된 이벤트: 분류기 설정(`document_kinds`·`row_rules`·`store_raw` 등)은 **바꾼 뒤 수집하는 행부터**
적용된다. 색인은 같은 이벤트(같은 identity)를 다시 쓰지 않으므로, 이미 색인된 행은 다시 스캔해도 그대로다. 예를 들어
문서 종류 기본값(`CLAUDE.md` → `rules`, 5.5R.7)이나 `api-request-blob` 원문 제외(5.5R.34)를 옛 이벤트에도 반영하려면
그 범위의 색인을 비우고(purge) 다시 스캔한다. 그 전까지 옛 색인의 원문은 남는다(보존 기간
`mod-logs.retention_days`가 지나면 지워진다). 분류 기본값이 바뀌면 purge 후 재스캔한다(5.7R.6, M-3):

```bash
# 서버에서(dry_run이 기본이라 먼저 지울 행 수만 본다). 요청 본문 행의 기본 범주는 meta다.
POST /api/v1/logs/index/purge  {"sources": ["claude-code-jsonl"], "categories": ["meta"]}
POST /api/v1/logs/index/purge  {"sources": ["claude-code-jsonl"], "categories": ["meta"], "dry_run": false}
POST /api/v1/logs/scan         {"source_ids": ["claude-code-jsonl"]}
# 서버 없이 색인 파일에(설정의 index_path → 서버 DB). --yes가 있어야 지운다.
agent-console logs purge --config agent-console.yaml --source claude-code-jsonl --category meta --yes
```

범주·출처 이름은 지금 설정의 값이다(`row_rules`로 범주를 바꿨다면 그 범주를 준다). 커서를 지우므로 다음 스캔이 그
출처의 파일을 처음부터 다시 읽는다. 지우지 않은 이벤트는 같은 identity라 다시 들어가지 않는다.

알려진 한계(행 단위 무상태 F-7의 결과):

- 도구 결과 행에는 도구 이름이 없다. MCP 결과는 범주 `tool`이고, MCP 호출(`start`)과 같은 `call_id`로 짝지어진다.
  타임라인 `duration_ms`와 상세 `related`도 이 짝으로 계산한다.
- 위임 대상 thread는 수집할 때 이미 있던 메타 파일로 찾는다. 메타 파일이 아직 없으면 `role:{subagent_type}`이
  대상이 된다. 위임 결과(`merge`)는 `toolUseResult.agentId`로 언제나 정확하다.
- 파일 변경 문서는 호출 이벤트에 붙는다(요청한 변경). 실제 성공 여부는 같은 `call_id`의 결과 상태로 본다.

## 공개 API

| 이름 | 용도 |
| --- | --- |
| `ClaudeCodeJsonlSource` | X5 출처(`JsonlFileSource` 상속, `default_roots`·`ref_meta`, 범위 `in_scope`·`allowed_keys`) |
| `project_key(folder, keep=, replacement=)` | 작업 폴더 → Claude Code `projects` 아래 폴더 이름 |
| `ClaudeCodeClassifier` | X6 분류기 |
| `source_config_schema()`·`classifier_config_schema()` | 설정 스키마(기본값 포함, 사본) |
| `compile_mcp_pattern(pattern)`·`McpPatternError` | MCP 이름 틀 → 매처(자리 표시 검사) |
| `summary_text(detail, items)` | 요약 평문 뽑기(설정 `summaries`와 같은 규칙: 포인터 또는 틀) |
| `omitted_row(row, keep)`·`OMITTED_KEY` | 원문 대신 저장할 값(행 규칙 `store_raw: false`와 같은 규칙: `keep` 값 + `omitted`{`bytes`, `sha256`}) |
| `CLAUDE_CODE_SOURCE_ID`·`CLAUDE_CODE_FORMAT`·`META_KIND_*`·`MCP_PATTERN_GROUPS` | 상수 |

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
