# 사용량

사용량 화면은 출처가 준 창(5시간 창, 주간 창 …)의 사용률·초기화 시각을 모아 보인다. 서비스는 출처 이름도 창 이름도
모른다. 출처가 주지 않은 값은 지어내지 않고 비워 둔다(`None`). 출처를 더하는 길은 두 가지다.

| 길 | 언제 |
| --- | --- |
| 플러그인 출처([usage-source](#usage-source)) | 출처가 혼자 값을 얻을 수 있을 때(파일, 외부 API, 설정에 적은 값) |
| 모듈이 주는 출처([runtime-usage-source](#runtime-usage-source)) | 값을 얻는 데 다른 서버 기능의 데이터(로그 색인, 실행 기록)가 필요할 때 |

어느 길이든 사용자는 같은 설정으로 켜고 끄고 값을 준다. 작업 공간 설정 `usage.sources`의 항목 `id`가 출처 id다.

```yaml extdocs:validate=agent_console_contracts:WorkspaceSettings
usage:
  sources:
    - id: acme.gateway
      enabled: true
      config:
        endpoint_env: ACME_USAGE_URL
    - id: statusline-file
      enabled: false
  window_labels:
    five_hour: 5시간
```

설정에 없는 출처는 서술자 `auto_enable`이 참일 때만 켜진다. 설정 `config`는 그 출처 서술자의 `config_schema`로
검증되고, 틀리면 저장 전 검사가 `usage.source_config_invalid` 오류로 막는다(값은 문구에 넣지 않는다).

## runtime-usage-source

**언제 쓰나**: 사용량 값을 계산하려면 다른 서버 기능의 데이터가 필요할 때. 기본 구현은 로그·사용량 연동이 주는
`local-logs`(로그 색인의 토큰 표본으로 창 사용량을 추정)다. 출처 패키지가 그 기능을 import하면 기능 독립이 깨지므로,
연동 모듈이 두 기능의 공개 포트를 받아 출처 객체를 만들어 사용량 모듈의 포트에 넣는다.

**최소 모양**: 연동 모듈의 서술자에 `provides=[USAGE_SOURCES]`(포트 이름 `usage.sources`, 여러 제공자)를 적고
`build`에서 `ctx.provide(USAGE_SOURCES, 출처)`를 부른다. 출처 객체는 [usage-source](#usage-source)와 같은
`UsageSource`다. 포트 키는 사용량 모듈을 import하지 않고 같은 이름의 `PortKey`를 자기 패키지에 선언한다
([연동 모듈](links.md#공개-포트만-본다)).

**규칙**

- 출처 id는 entry point 출처와 겹치지 않게 한다. 겹치면 사용량 목록에서 한쪽만 보인다.
- 데이터가 바뀌는 시점을 알 수 있으면(예: 로그 색인 알림 구독) 캐시를 그때 버린다. `snapshot`이 불릴 때마다 전체를
  다시 읽지 않는다.
- 신뢰 등급(`trust`)을 정직하게 적는다. 다른 데이터로 짐작한 값은 `estimated`다.

**흔한 실수**: 사용량 모듈이 꺼진 환경을 생각하지 않는다. 필수 포트가 없으면 연동은 `unsatisfied`로 꺼지고 서버는
그대로 시작해야 한다. 연동 `build`에서 다른 모듈을 직접 찾지 않는다.

**지운 뒤 남는 데이터**: 연동이 꺼지거나(그 연동, 또는 필수 포트를 주는 모듈 하나라도) 제거되면 출처 목록에서
사라진다. 설정 `usage.sources`의 항목은 남지만 등록된 출처가 없으므로 이슈 없이 무시된다.

<!-- extdocs:facts runtime-usage-source -->
- 등록: 서버 모듈이 포트 `usage.sources`(기호 `agent_console_mod_usage:USAGE_SOURCES`, 다중 예)를 제공한다.
- 인터페이스:
  - `agent_console_usage:UsageSource` — 사용량 출처. entry point `agent_console.usage_sources`로 등록한다.
- 기본 구현: `link-logs-usage`
- 예제:
  - reference: [packages/py/links/ac-link-logs-usage](../../packages/py/links/ac-link-logs-usage/README.md)
- 끄기·제거: 제공하는 모듈을 끄면(`modules.<id>.enabled: false`) 소비하는 쪽은 그 부분만 꺼진다.
<!-- /extdocs:facts -->

## usage-source

**언제 쓰나**: 기본 출처(실행 이벤트 토큰, Claude Code 상태 줄 파일, 시험용 가짜)로 볼 수 없는 사용량이 있을 때.
사내 게이트웨이 할당량, 다른 도구의 사용량 API, 사용자가 직접 적는 팀 공용 한도가 예다.

**최소 모양**: `descriptor`(`UsageSourceDescriptor` — `id`·`title`·`trust`, 선택 `config_schema`·`auto_enable`·
`setup_help`)와 `async snapshot(ctx) -> list[UsageWindowSnapshot]` 하나. `ctx`(`UsageSourceContext`)에 지금
설정(`config`)과 주입된 시계 값(`now`)이 있다.

**규칙**

- **값을 지어내지 않는다.** 출처가 모르는 사용률·초기화 시각·상태는 `None`으로 둔다. 화면은 비어 있는 값을 숫자로
  채우지 않는다. 관측할 것이 없으면 빈 목록이다.
- 창 id(`five_hour` 등)는 출처가 정하는 문자열이다. 표시 이름은 사용자 설정 `usage.window_labels`가 바꾼다.
- 신뢰 등급 `trust`는 열린 문자열이다. 알려진 값(`official`·`observed`·`estimated`·`unofficial`) 밖의 값도 되고
  화면은 기본 배지로 보인다.
- 시각은 `ctx.now`를 쓴다(테스트에서 바꿀 수 있게). 외부 호출이 있으면 시간 제한 안에서 끝낸다. 시간 안에 답하지
  않으면 서비스가 그 출처만 `usage_source_timeout`으로 표시하고 다른 출처는 그대로 보인다. 읽기 실패는 예외로 알리면
  `usage_source_failed`가 된다.
- 비밀(API 토큰)은 `config`에 값으로 받지 않는다. 환경변수 이름이나 `secret://` 참조를 받는다.
- 설정이 있어야 동작하는 출처는 `auto_enable`을 끄고 `setup_help`에 무엇을 적어야 하는지 한 문단으로 쓴다.

**흔한 실수**: 초기화 시각을 버리고 사용률만 낸다. 서비스는 초기화 시각이 지난 창을 현재 값에서 빼는데, 시각이 없으면
오래된 값이 현재 값처럼 보인다.

**지운 뒤 남는 데이터**: 출처 목록과 창 카드에서 사라진다. 설정 `usage.sources`의 그 항목은 남지만 등록된 출처가
없으므로 이슈 없이 무시된다. 다시 설치하면 같은 설정으로 다시 보인다.

<!-- extdocs:facts usage-source -->
- 등록: entry point 그룹 `agent_console.usage_sources`(상수 `agent_console_usage:USAGE_SOURCES_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_usage:UsageSource` — 사용량 출처. entry point `agent_console.usage_sources`로 등록한다.
  - `agent_console_usage:UsageSourceContext` — `UsageSource.snapshot`에 넘기는 맥락(읽기 전용).
  - `agent_console_usage:UsageRecord` — 사용량 한 건(집계 재료). 모르는 차원은 `None`.
- 설정: `usage.sources`
- 기본 구현: `fake (agent-console-usage)`, `run-events (agent-console-usage)`, `statusline-file (agent-console-usage)`
- 예제:
  - package: [examples/extensions/agent-console-example-usage](../../examples/extensions/agent-console-example-usage/README.md)
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->
