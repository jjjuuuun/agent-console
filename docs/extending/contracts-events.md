# 계약과 이벤트

서버·웹·플러그인이 주고받는 데이터 모양(정의·설정·디스크립터·REST 요청과 응답·실행 이벤트)은 계약 패키지
`agent-console-contracts` 한 곳에 있다. 이 문서는 플러그인이 계약을 쓰는 법, 버전을 맞추는 법, 계약에 없는 자기
데이터를 내는 법을 설명한다.

## 한 곳에서 정의한다

- 계약은 Pydantic 모델이다. 여기서 JSON Schema를 만들고, 웹의 TypeScript 타입(`@agent-console/contracts`)은 그
  스키마에서 생성한다. 같은 모양을 두 언어로 손으로 쓰지 않는다.
- 저장소 안에서 계약을 바꾸면 생성물도 함께 바꾼다.

```bash
uv run poe contracts          # JSON Schema → TS 타입 다시 만들기
uv run poe contracts-check    # 생성물이 지금 코드와 같은지(다르면 실패)
```

- 플러그인은 계약 모델을 import해 쓴다(디스크립터·이슈·이벤트). 계약 모델의 필드를 바꾸거나 계약 패키지에 자기
  모델을 더하지 않는다.

## 버전

계약에는 버전이 두 층 있다.

| 무엇 | 어디 | 쓰임 |
| --- | --- | --- |
| 패키지 버전 | `agent-console-contracts` 배포 버전(0.x) | 플러그인 의존 범위. 같은 minor 안에서 호환. `>=0.15,<0.16`처럼 minor 하나로 묶는다 |
| 하위 모듈 버전 | `CONTRACT_VERSIONS`(기능 묶음 → semver) | 묶음별 변화 추적. 필드 더하기는 minor, 깨는 변경은 major. 서버 모듈은 자기가 쓰는 하위 모듈과 버전을 서술자 `contracts`로 알린다 |

지금 버전 표는 [계약 하위 모듈 버전](reference.md#계약-하위-모듈-버전)에 생성되어 있다.

```python
>>> from agent_console_contracts import CONTRACT_VERSIONS
>>> sorted(CONTRACT_VERSIONS)[:4]
['architecture', 'chat', 'common', 'definitions']
>>> all(v.count(".") == 2 for v in CONTRACT_VERSIONS.values())
True

```

## 열린 문자열과 `Known*` 상수

종류 이름은 계약에 고정 목록(enum)으로 들어 있지 않다. 노드 종류, 연결 종류, 리소스 종류, 백엔드 id, 로그 범주,
이슈 코드는 모두 **열린 문자열**이다. 그래서 플러그인이 새 이름을 써도 계약을 고치지 않는다.

- 계약에 고정 어휘로 남는 것은 엔진 의미가 걸린 값뿐이다(실행 상태, 연결의 스케줄링 방식 등).
- 기본 구현이 쓰는 이름은 문서 상수 `Known*`(예: `KnownIssueCodes`, `KnownInteractionKinds`, `KnownLogCategories`)로
  모아 둔다. 상수는 "이미 알려진 값"의 목록일 뿐 허용 목록이 아니다. 이 상수에 없는 값도 그대로 받고 그대로 보인다.

```python
>>> from agent_console_contracts import Issue, KnownIssueCodes
>>> KnownIssueCodes.CONDITION_UNKNOWN_OPERATOR
'condition.unknown_operator'
>>> Issue.model_validate({"severity": "warning", "code": "mine.too_long", "message": "글이 깁니다"}).code
'mine.too_long'

```

## 계약에 없는 것을 내보내는 법

바깥 플러그인은 계약을 고치지 않고 다음으로 자기 데이터를 낸다.

| 필요 | 방법 |
| --- | --- |
| 자기 REST 응답 모양 | 자기 패키지의 Pydantic 모델(모듈의 `models.py`). 오류 코드는 계약의 알려진 코드를 쓴다 |
| 자기 이슈·경고 | 계약 `Issue`에 자기 접두 `code`(`mine.too_long`) + 사람이 읽는 `message` + 필요하면 `details` |
| 오류 상세 | 오류 본문의 `details`(객체)에 자기 키 |
| 설정 | 디스크립터 `config_schema`(JSON Schema) 또는 모듈 `settings_schema` |
| 실행 중 사건 | 자기 접두 이벤트 type(아래) |

## 플러그인 자기 이벤트

실행 중 노드·백엔드·도구 공급자는 실행 문맥의 `emit(type, payload)`로 이벤트를 낸다. type이 계약이 아는 것이면
그 모양으로 검사되고, 모르는 type이면 일반 `RunEvent`로 저장·전달된다.

- type은 자기 접두사로 시작한다(`<접두>.<이름>`, 예: `example_notes.read`). 계약이 아는 type 목록은
  [알려진 RunEvent type](reference.md#알려진-runevent-type)이고, 그 이름은 쓰지 않는다.
- payload에는 본문·비밀·예외 원문을 넣지 않는다. 상태·개수·상관 id(`tool_use_id`) 정도만 싣는다.
- 웹은 모르는 type을 원문 그대로, 중립 색으로 보인다. 웹 코드를 고치지 않아도 실행 기록에 나온다.

```python
>>> from agent_console_contracts import KNOWN_RUN_EVENT_TYPES, parse_run_event
>>> "run.started" in KNOWN_RUN_EVENT_TYPES
True
>>> event = parse_run_event(
...     {"event_id": "e1", "run_id": "r1", "seq": 1, "ts": 0.0, "node_path": ["writer"],
...      "type": "mine.checked", "payload": {"status": "ok", "count": 2}}
... )
>>> type(event).__name__, event.type, event.payload
('RunEvent', 'mine.checked', {'status': 'ok', 'count': 2})

```

### 로그 화면에 범주 붙이기

실행 이벤트는 로그 화면에도 색인된다. 어떤 type이 어떤 범주·제목·상태로 보일지는 코드가 아니라 **대응표 데이터**가
정한다. 대응표에 없는 type은 범주 `other`로 보인다. 자기 이벤트에 범주를 붙이려면 사용자가 실행 기록 로그 출처의
설정에 대응표 항목을 더한다(키별로 기본 대응표를 덮어쓴다).

```yaml extdocs:validate=agent_console_contracts:WorkspaceSettings
logs:
  sources:
    - id: platform-runs
      config:
        event_map:
          "mine.*": {category: tool, title: "내 도구 {/payload/status}"}
          mine.checked:
            category: tool
            status: {pointer: /payload/status, map: {"ok": ok}, default: error}
```

값 틀은 `{/JSON 포인터}`·`{type}`·`{node}`로 이벤트 값을 끼워 넣는다. 대응표의 전체 키와 규칙은 [로그](logs.md)
영역 페이지에 있다.

## 웹 타입

웹 패키지는 `@agent-console/contracts`의 생성 타입을 쓴다. 웹 확장이 계약 모양을 따로 정의하지 않는다. 계약에 없는
자기 데이터는 웹 확장 쪽에서 자기 타입으로 둔다. → [웹](web.md)
