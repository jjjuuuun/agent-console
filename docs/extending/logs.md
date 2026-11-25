# 로그

로그 화면은 여러 출처(Claude Code 세션 로그, 이 콘솔의 실행 이벤트, hook 기록, 다른 도구의 jsonl)를 같은 모양의
정규화 이벤트로 색인해 보인다. 흐름은 **출처가 원본을 읽고 → 분류기가 행 하나를 이벤트 초안으로 바꾸고 → 색인이
저장한다**. 출처는 원본을 읽기만 한다. 범주 이름(`tool`·`llm`·`error` …)은 분류기가 내는 열린 문자열이고, 화면의
이름·색은 사용자 설정 `logs.taxonomy`(데이터)가 정한다.

| 하고 싶은 일 | 지점 |
| --- | --- |
| 새 로그 파일·형식을 읽는다 | [log-source](#log-source) + [log-classifier](#log-classifier) |
| 같은 원본을 다르게 분류한다 | [log-classifier](#log-classifier) |
| 다른 서버 기능의 데이터를 로그로 보인다 | [runtime-log-source](#runtime-log-source) |
| 실행 중 hook·도구 호출을 더 자세히 기록한다 | [collector](#collector) |
| 로그 질의에 새 범위(`scope=<종류>:<값>`)를 더한다 | [log-scope-kind](#log-scope-kind) |
| 로그 질의에 새 필터 이름을 더한다 | [log-filter-predicate](#log-filter-predicate) |
| 실행 이벤트의 범주·제목을 바꾼다(코드 없음) | [실행 이벤트 대응표](#실행-이벤트-대응표) |

출처 설정은 작업 공간 설정 `logs.sources`다. 항목 `id`가 출처 id, `config`가 그 출처 `config_schema`에 맞는 값,
`config.classifier`가 분류기 선택(`{id?, config?}`, id를 비우면 출처 서술자의 `format`)이다.

## collector

**언제 쓰나**: Claude Agent SDK 백엔드로 실행할 때 기본 기록(hook 실행, MCP 도구 호출) 말고 더 모으고 싶은 것이
있을 때. 도구 이름별 호출 수, 특정 hook의 입력 요약, 응답 시간 분포가 예다. 이 지점은 그 백엔드 패키지가 정의한
것이라 다른 백엔드에는 걸리지 않는다. 다른 백엔드라면 그 백엔드가 이벤트를 직접 낸다.

**최소 모양**: `BaseClaudeSdkCollector`를 상속하고 필요한 메서드만 고친다. `on_message(message, ctx)`(모델 응답·
결과 메시지마다), `on_hook(event, data, tool_use_id, ctx)`(hook마다), `hook_events(config)`(받을 hook 이름),
`config_problems(config)`(설정 검사). 서술자(`CollectorDescriptor`)의 `backend`가 이 수집기를 쓸 백엔드 id다.

**규칙**

- 실행에 개입하지 않는다. 메시지를 바꾸거나 막지 않고 보기만 한다. 예외는 백엔드가 삼키고 실행마다 경고 이벤트
  하나로 남긴다.
- 실행 하나 동안의 상태는 `ctx.state`에 둔다. 수집기 객체에 실행별 값을 두지 않는다(실행이 동시에 돈다).
- 이벤트는 자기 접두사 `type`으로 낸다. 백엔드가 실행 이벤트로 내보내므로 실행 화면과 로그 화면(`platform-runs`
  출처)에 그대로 보인다. 로그의 범주·제목은 [실행 이벤트 대응표](#실행-이벤트-대응표)로 붙인다.
- 도구 입력·출력 원문, 비밀, 경로는 싣지 않는다. 이름·개수·시간·결과 상태 정도만 싣는다.
- 켜기는 에이전트·팀·공통 설정의 `observe.collectors.<id>`(`enabled`, `config`)다. 정하지 않은 수집기는 꺼져 있다.

**흔한 실수**: `config` 모양을 서술자 `config_schema`에만 적고 `config_problems`에서 검사하지 않는다. 스키마가
없거나 느슨하면 틀린 설정이 실행 때 조용히 무시된다.

**지운 뒤 남는 데이터**: 설정의 `observe.collectors.<id>`는 남는다. 검증이 `observe.unknown_collector` **경고**로
알리고 실행은 그대로 된다. 설정이 수집기 스키마와 맞지 않을 때는 `observe.collector_config_invalid` 경고다. 이미 낸
이벤트는 실행 기록에 남는다.

<!-- extdocs:facts collector -->
- 등록: entry point 그룹 `agent_console.collectors`(상수 `agent_console_backend_claude_sdk.collectors:COLLECTORS_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_backend_claude_sdk.collectors:ClaudeSdkCollector` — claude-sdk 관측 수집기 프로토콜.
  - `agent_console_backend_claude_sdk.collectors:BaseClaudeSdkCollector` — 수집기 공통 베이스: 모든 메서드의 기본 구현(아무것도 하지 않음)과 설정 모델 검증.
  - `agent_console_backend_claude_sdk.collectors:CollectorContext` — 실행 하나와 수집기 하나의 문맥. 백엔드가 실행마다 새로 만든다.
- 기본 구현: `mcp-calls (agent-console-backend-claude-sdk)`, `sdk-hooks (agent-console-backend-claude-sdk)`
- 예제:
  - package: [examples/extensions/agent-console-example-collector](../../examples/extensions/agent-console-example-collector/README.md)
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->

## log-classifier

**언제 쓰나**: 출처가 읽은 행을 다른 범주·제목·근거로 나누고 싶을 때, 또는 새 출처에 맞는 분류기가 필요할 때.
출처 하나에 분류기 여럿을 두고 설정으로 고를 수 있다.

**코드 없이 되는 경우**: 행이 JSON이면 기본 분류기 `mapped-jsonl`이 설정만으로 필드를 채운다(`fields`: 초안 필드 →
JSON 포인터, `defaults`, `value_maps`, `correlation`, `usage`, `skip_if_missing`).

```yaml extdocs:validate=agent_console_contracts:WorkspaceSettings
logs:
  sources:
    - id: mapped-jsonl
      enabled: true
      config:
        roots: ["~/tool-logs"]
        classifier:
          config:
            fields: {title: /msg, time: /ts, category: /level}
            value_maps: {category: {ERROR: error, WARN: error}}
            defaults: {category: other}
```

**최소 모양**: `descriptor`(`LogClassifierDescriptor` — `id`·`title`, 선택 `formats`·`config_schema`)와
`classify(record, ctx) -> list[LogEventDraft]`.

**규칙**

- **행 단위 무상태**다. 행 하나만 보고 판단한다. 앞뒤 행을 이어야 하는 정보(세션 id 등)는 출처가 원본 행
  `RawRecord`에 실어 준다.
- 행 하나가 이벤트 여럿이 될 수 있고(한 응답의 여러 도구 호출), 버릴 행은 빈 목록이다. 형식이 틀린 행은 버리지
  말고 진단 범주 초안으로 낸다(색인에서 찾을 수 있게).
- 범주·상태 이름을 코드에 고정하지 않는다. 대응은 분류기 설정 데이터로 받는다.
- **같은 응답의 토큰을 두 번 세지 않는다.** 원본이 응답 하나를 여러 행으로 나눠 쓰면(같은 메시지 id) 토큰 표본에
  메시지 id를 실어 한 번만 세게 한다. 같은 세션을 두 출처가 함께 읽는 경우(실행 이벤트와 세션 로그)에도 한쪽만 토큰을
  낸다.
- 원본 형식이 바뀌면 분류기를 고치지 말고 새 id(버전)로 하나 더 둔다. 옛 원본은 옛 분류기가 계속 읽는다.

**흔한 실수**: 프롬프트·도구 출력 원문을 제목에 그대로 넣는다. 제목은 짧게 자르고, 비밀 의심 값은 색인이 가리지만
분류기가 바꾼 문자열(인코딩·일부)은 가릴 수 없다.

**지운 뒤 남는 데이터**: 그 분류기를 고른 출처는 다음 수집 때 실패하고, 서버 경고가 `logs.unknown_classifier`
**경고**(출처 id·분류기 id)로 알린다. 다른 출처는 계속 수집되고, 이미 색인된 이벤트는 남는다.

<!-- extdocs:facts log-classifier -->
- 등록: entry point 그룹 `agent_console.log_classifiers`(상수 `agent_console_logs:LOG_CLASSIFIERS_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_logs:LogClassifier` — 로그 분류기. 행 단위 무상태.
  - `agent_console_logs:ClassifyContext` — 분류기에 넘기는 맥락.
  - `agent_console_logs:LogEventDraft` — 분류기가 원본 행 하나에서 만든 이벤트 초안. `LogEvent`에서 uid·seq·observed_at을 뺀 것.
- 기본 구현: `claude-code (agent-console-logs-claude)`, `hook-probe (agent-console-hook-probe)`, `mapped-jsonl (agent-console-logs)`, `normalized-v1 (agent-console-logs)`
- 예제:
  - package: [examples/extensions/agent-console-example-log-source](../../examples/extensions/agent-console-example-log-source/README.md)
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->

## log-filter-predicate

**언제 쓰나**: 로그 이벤트 질의에 새 필터 이름을 더하고 싶을 때. 다른 기능의 판단을 로그 표에 걸어야 하는 경우다.
기본 구현은 로그·구조도 연동이 더하는 `arch`·`arch_group`·`arch_sources`(구조도 칸에 든 이벤트만)다.

**최소 모양**: 연동 모듈이 포트 `logs.filter_predicates`(여러 제공자)에 `LogFilterExtension`을 준다. `fields`(받는
필터 이름과 표시 정보 — `GET /api/v1/logs/schema`의 `filters`에 실린다)와 `build(values, context) -> EventPredicate`
(이벤트 하나 → 참·거짓).

**규칙**

- 필터 이름은 기본 필터·다른 확장과 겹치지 않게 자기 접두사를 붙인다. 겹치면 먼저 모은 것만 남고 뒤의 것은 빠진다.
- 값이 틀리면 `ValueError`를 던진다. 서버가 422로 바꾼다.
- `build`는 질의마다 한 번 불리고, 판정 함수는 이벤트마다 불린다. 비싼 준비는 `build`에서 끝내고 판정은 가볍게 한다.

**흔한 실수**: 판정 함수 안에서 다른 모듈을 질의한다. 이벤트 수만큼 질의가 나간다.

**지운 뒤 남는 데이터**: 사용자 데이터는 남지 않는다. 연동이 꺼지면 그 필터 이름은 모르는 필터가 되어 질의가 422다.
그 필터를 쓰던 링크·저장된 질의가 있으면 그 질의만 실패한다.

<!-- extdocs:facts log-filter-predicate -->
- 등록: 서버 모듈이 포트 `logs.filter_predicates`(기호 `agent_console_mod_logs.ports:LOG_FILTER_PREDICATES`, 다중 예)를 제공한다.
- 인터페이스:
  - `agent_console_logs:LogFilterExtension` — 필터 확장 하나(포트 `logs.filter_predicates`).
- 기본 구현: `link-logs-architecture`
- 예제:
  - reference: [packages/py/links/ac-link-logs-architecture](../../packages/py/links/ac-link-logs-architecture/README.md)
- 끄기·제거: 제공하는 모듈을 끄면(`modules.<id>.enabled: false`) 소비하는 쪽은 그 부분만 꺼진다.
<!-- /extdocs:facts -->

## log-scope-kind

**언제 쓰나**: 로그 질의를 "어떤 것에 속한 이벤트"로 좁히는 새 범위가 필요할 때. 기본 구현은 로그·실행 연동의
`run`(실행 하나)·`run-tree`(실행과 자식 실행 전부)다. 질의는 `scope=<종류>:<값>`이다.

**최소 모양**: 연동 모듈이 포트 `logs.scope_kinds`(여러 제공자)에 `LogScopeKind`를 준다. `id`(종류 이름, `:` 없음)와
`resolve(value) -> LogScope`. 범위는 세션 id와 실행 id의 합집합이다.

```python
>>> from agent_console_logs import LogScope
>>> scope = LogScope.of(sessions=["s-1"], run_ids=["r-1", ""])
>>> scope.contains("s-1", ""), scope.contains("", "r-1"), scope.contains("s-2", "r-2")
(True, True, False)

```

**규칙**

- 없는 대상·빈 값이면 `ValueError`를 던진다. 서버가 422(`details.path = scope`)로 바꾼다.
- 이벤트 목록·집계·세션 목록·타임라인이 같은 범위를 쓴다. 범위 계산은 한 곳(`resolve`)에만 둔다.
- 종류 이름은 다른 연동과 겹치지 않게 짓는다. 겹치면 먼저 모은 것만 남는다.

**흔한 실수**: `resolve`에서 이벤트를 직접 고른다. 범위는 세션·실행 id만 돌려주고, 이벤트 고르기는 색인이 한다.

**지운 뒤 남는 데이터**: 그 범위로 만든 링크는 모르는 범위 종류가 되어 422다. 이벤트와 색인은 그대로다.

<!-- extdocs:facts log-scope-kind -->
- 등록: 서버 모듈이 포트 `logs.scope_kinds`(기호 `agent_console_mod_logs.ports:LOG_SCOPE_KINDS`, 다중 예)를 제공한다.
- 인터페이스:
  - `agent_console_logs:LogScopeKind` — 범위 종류 하나(포트 `logs.scope_kinds`).
- 기본 구현: `link-logs-runs`
- 예제:
  - reference: [packages/py/links/ac-link-logs-runs](../../packages/py/links/ac-link-logs-runs/README.md)
- 끄기·제거: 제공하는 모듈을 끄면(`modules.<id>.enabled: false`) 소비하는 쪽은 그 부분만 꺼진다.
<!-- /extdocs:facts -->

## log-source

**언제 쓰나**: 로그 화면에서 다른 도구의 로그를 함께 보고 싶을 때. 다른 에이전트 CLI의 세션 파일, 사내 도구의 텍스트
로그가 예다. 행이 JSON이면 먼저 기본 출처 `mapped-jsonl`(설정만으로 폴더를 읽음)으로 되는지 본다.

**최소 모양**: `descriptor`(`LogSourceDescriptor` — `id`·`title`·`format`, 선택 `config_schema`·`default_enabled`·
`reads_paths`·`setup_help`), `discover(ctx)`(읽을 원본 목록), `read(ref, cursor, ctx, budget=, final=)`(커서 뒤를 예산만큼
읽기). 줄 단위 파일이면 `JsonlFileSource`를 상속하고 `parse_line`만 바꾸면 증분 읽기·끝나지 않은 줄 보류·파일 회전
감지·읽기 전용 열기를 기반 클래스가 한다.

**규칙**

- **원본은 읽기 전용이다.** 쓰기·이름 바꾸기·잠금을 하지 않는다. 기반 클래스의 읽기 전용 열기를 쓴다.
- 읽을 폴더는 설정(`roots` 등)으로 받고 코드에 고정하지 않는다. 앱은 등록된 프로젝트 폴더 범위 밖은 읽지 않는다
  (범위 밖 루트는 `logs.out_of_scope`로 알린다).
- 증분으로 읽는다. 커서(바이트 오프셋 등)를 돌려주고 다음 수집은 그 뒤부터다. 한 번에 `budget`을 넘게 읽지 않는다.
- 대화 원문을 색인에 복사하는 출처는 `default_enabled = false`로 둔다. 사용자가 켜야 읽는다.
- 서술자 `format`이 기본 분류기 id다. 짝 분류기를 같은 패키지에 두는 것이 보통이다.
- 하위 에이전트 로그처럼 원본이 여러 파일로 나뉘면 `discover`가 모두 찾고, 세션을 잇는 정보를 행에 싣는다.

**흔한 실수**: 형식이 틀린 줄을 버린다. 버리지 말고 행으로 넘겨 분류기가 진단 이벤트로 내게 한다(어디서 깨졌는지
찾을 수 있게).

**지운 뒤 남는 데이터**: 출처 목록에서 사라진다. 설정 `logs.sources`의 항목과 이미 색인한 이벤트는 남지만 새로 수집하지
않는다. 색인은 보관 기간(`modules.options.mod-logs.retention_days`)이 지나면 정리된다.

<!-- extdocs:facts log-source -->
- 등록: entry point 그룹 `agent_console.log_sources`(상수 `agent_console_logs:LOG_SOURCES_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_logs:LogSource` — 로그 출처. 원본을 읽기만 한다.
  - `agent_console_logs:LogSourceContext` — 출처에 넘기는 맥락(모두 주입, 전역 없음).
  - `agent_console_logs:RawRecord` — 원본 행 하나.
- 기본 구현: `claude-code-jsonl (agent-console-logs-claude)`, `hook-probe-jsonl (agent-console-hook-probe)`, `mapped-jsonl (agent-console-logs)`, `normalized-v1 (agent-console-logs)`
- 예제:
  - package: [examples/extensions/agent-console-example-log-source](../../examples/extensions/agent-console-example-log-source/README.md)
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->

## runtime-log-source

**언제 쓰나**: 다른 서버 기능의 데이터를 로그로 보이고 싶을 때. 기본 구현은 로그·실행 연동의 `platform-runs`(이
콘솔의 실행 이벤트)다. 그 데이터는 파일이 아니라 다른 모듈의 포트로만 읽을 수 있으므로 entry point 출처로는 만들 수
없다.

**최소 모양**: 연동 모듈이 포트 `logs.sources`(여러 제공자)에 `RuntimeLogSource`(`source`, `classifier` 두 속성)를
준다. 출처와 분류기는 [log-source](#log-source)·[log-classifier](#log-classifier)와 같은 프로토콜이고, 분류기는
레지스트리를 거치지 않고 출처가 직접 지정한다.

**규칙**

- 출처 id는 entry point 출처와 겹치지 않게 한다. 겹치면 그 런타임 출처는 붙지 않고 `logs.source_failed` 경고(이유
  `logs.runtime_source_rejected`)가 남는다.
- 새 데이터가 생기는 시점(예: 실행 이벤트 알림)을 구독해 수집을 예약한다. 주기 수집에만 기대면 화면이 늦다.
- 상대 모듈의 데이터는 읽기만 한다.
- 분류 규칙을 코드에 두지 말고 데이터(대응표)로 둔다. `platform-runs`의 대응표가 그 예다(아래).

**흔한 실수**: 출처가 상대 모듈 패키지를 import한다. 포트로 받은 객체만 쓴다([연동 모듈](links.md)).

**지운 뒤 남는 데이터**: 연동이 꺼지면 출처가 사라지고 이미 색인한 이벤트는 남는다. 설정 `logs.sources`의 항목도
남지만 쓰이지 않는다.

<!-- extdocs:facts runtime-log-source -->
- 등록: 서버 모듈이 포트 `logs.sources`(기호 `agent_console_mod_logs.ports:LOG_SOURCES`, 다중 예)를 제공한다.
- 인터페이스:
  - `agent_console_mod_logs.ports:RuntimeLogSource` — ``logs.sources`` 포트 한 항목: 다른 모듈의 데이터를 읽는 출처와 그 분류기.
- 기본 구현: `link-logs-runs`
- 예제:
  - reference: [packages/py/links/ac-link-logs-runs](../../packages/py/links/ac-link-logs-runs/README.md)
- 끄기·제거: 제공하는 모듈을 끄면(`modules.<id>.enabled: false`) 소비하는 쪽은 그 부분만 꺼진다.
<!-- /extdocs:facts -->

## 실행 이벤트 대응표

`platform-runs` 출처는 실행 이벤트(`RunEvent`의 `type`)를 대응표로 로그 이벤트에 옮긴다. 대응표는 데이터다. 기본값은
로그·실행 연동 패키지의 데이터 파일이고, 작업 공간 설정 `logs.sources[id=platform-runs].config.event_map`이 키(형식)별로
**통째로** 덮어쓴다. 플러그인이 자기 이벤트에 범주를 붙일 때도 이 표를 쓴다
([계약과 이벤트](contracts-events.md#로그-화면에-범주-붙이기)).

```yaml extdocs:validate=agent_console_contracts:WorkspaceSettings
logs:
  sources:
    - id: platform-runs
      config:
        max_runs: 200
        event_map:
          "acme.*": {category: tool, title: "acme {type} {/payload/status}"}
          acme.call_finished:
            category: tool
            stage: complete
            call_id: "{/payload/call_id}"
            status: {pointer: /payload/ok, map: {"true": ok}, default: error}
            duration_ms: /payload/duration_ms
            tags: [tool]
          acme.noise: {skip: true}
```

**키**: 형식 이름 또는 글롭(`*`·`?`). 정확한 이름이 먼저, 그다음 글롭은 긴 것부터 하나만 맞는다. 맞는 규칙이 없으면
범주 `other`다. `"memory.*": {}`처럼 빈 규칙을 적으면 기본 규칙이 꺼져 범주 `other`가 된다.

**값**: 문자열 틀은 `{/JSON 포인터}`(이벤트 JSON 기준)와 이름 `{type}`·`{node}`·`{parent_node}`·`{thread}`·`{actor}`·
`{run_id}`를 채운다. 없는 값은 빈 문자열이다. 조건부 값 `{pointer, map, default}`는 포인터 값을 문자열(`true`·`false`·
`null`·숫자는 JSON 표기)로 바꿔 `map`에서 찾고, 없으면 `default`(없으면 읽은 값 그대로)를 쓴다. `map` 값과 `default`도
틀이다.

| 키 | 값 | 뜻 |
| --- | --- | --- |
| `category`·`title`·`stage`·`status`·`tool`·`call_id`·`via`·`model`·`message_id`·`role` | 틀 또는 조건부 값 | 로그 이벤트의 같은 이름 필드 |
| `from`·`to` | 틀 또는 조건부 값 | 보낸 쪽·받는 쪽(비면 없음) |
| `tags` | 문자열 목록, 또는 목록 값 `{each, value}` | 태그. `tool`은 도구 호출 약속 태그(같은 호출이 한 번만 색인된다) |
| `correlation` | 근거 이름 → 틀 또는 목록 값 | 이벤트를 잇는 근거(`session`·`call_id`는 값이 있으면 자동) |
| `documents` | 문서 틀 `{path, kind, action}` 하나 또는 목록 | 이벤트가 가리키는 문서. `each`를 주면 원소마다 하나, `path`가 비면 뺀다 |
| `duration_ms` | 포인터 | 끝난 구간의 소요 시간. 있으면 시작(추정)·끝 두 이벤트를 낸다 |
| `session_from` | 포인터 | 이 이벤트가 노드의 세션 id를 알린다(그 노드·하위 노드 이벤트의 세션) |
| `cwd_from` | 포인터 | 이 이벤트가 실행의 작업 폴더를 알린다(그 뒤 같은 실행 이벤트의 프로젝트 묶기 기준) |
| `usage` | 토큰 항목(`input_tokens`·`output_tokens`·`cache_read_input_tokens`·`cache_creation_input_tokens`) → 포인터 | 토큰 표본 |
| `skip` | `true` | 색인하지 않는다 |

목록 값 `{each: <목록 포인터>, value: <항목 틀>}`은 이벤트 안 목록의 원소마다 항목 하나를 만든다. 항목 틀 안의
`{./키}`·`{.}`(원소 자체)와 조건부 값의 `pointer: ./키`는 원소 기준이다. 빈 항목은 빼고 같은 항목은 한 번만 남는다.

**토큰을 두 번 세지 않게**: 기본 대응표는 실행 이벤트의 토큰을 표본으로 쓰지 않는다. 같은 세션을 Claude Code 세션 로그
출처로도 읽으면 두 번 세어지기 때문이다. 세션 로그 출처를 켜지 않는 환경에서 실행 단위 토큰을 보려면 토큰을 싣는 이벤트
규칙에 `usage`를 넣는다.

모양이 틀린 대응표(모르는 키 포함)는 출처 설정 스키마 검사에 걸려 그 출처의 수집이 실패하고, 서버 경고
`logs.source_failed`(오류 코드 `logs.invalid_config`)로 알린다. 다른 출처는 계속 수집된다.
