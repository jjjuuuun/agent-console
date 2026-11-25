# 구조도

구조도는 로그 이벤트를 칸과 연결로 모아 그린 그림이다. 무엇을 셀지와 어디에 그릴지는 전부 프로필 데이터다. 프로필은 사용자 설정·플러그인으로 더하고([architecture-profile](#architecture-profile)), 검사는 다른 모듈이 보탠다([architecture-profile-check](#architecture-profile-check)). 칸의 색·모양 같은 그리기 이름(`tone`·`view`)을 해석하는 일은 웹 쪽 확장이 맡는다.

## architecture-profile

**언제 쓰나**: 기본 프로필과 다른 구조로 로그를 보고 싶을 때(다른 팀 구성 방식, 새 로그 출처의 형식). 한 사람이 쓰려면 사용자 설정에 적고, 로그 출처 플러그인처럼 자기 형식용 프로필을 함께 배포하려면 entry point로 낸다.

**데이터로 더하기**: 워크스페이스 설정의 `architecture` 섹션이다. 프로필 id마다 칸(`cells`)·연결(`edges`)·조건(`when`)을 적는다. 조건은 팀 구성의 연결 조건과 같은 문법이다.

```yaml extdocs:validate=agent_console_contracts.architecture:ArchitectureSettings
include_defaults: true
default_profile: tool-flow
profiles:
  tool-flow:
    title: 도구 흐름
    cells:
      ask:
        label: 질문
        x: 100
        y: 60
        when: {all: [{path: /category, op: eq, value: input}]}
      work:
        label: 도구
        x: 400
        y: 60
        metrics: [count, errors, duration]
        group_by: /tool
        when: {all: [{path: /category, op: eq, value: tool}]}
    edges:
      - {id: hand, from: ask, to: work, kind: structural}
    error_when: {all: [{path: /status, op: eq, value: failed}]}
```

**플러그인으로 더하기**: entry point 값은 인자 없는 함수이고 `{프로필 id: 프로필 데이터}`를 돌려준다. 데이터 파일을 패키지 안에 두고 읽어 돌려주는 방식을 권한다. 전체 예는 [구조도 예제](../../examples/extensions/agent-console-example-architecture/README.md)다.

**규칙**
- 병합 순서는 패키지 기본(`include_defaults`일 때) → 플러그인 → 사용자 설정이다. 같은 id면 프로필 전체가 바뀌고(칸 단위로 합치지 않는다), 사용자 설정에 `null`로 적으면 그 프로필이 꺼진다.
- 연결은 그 전달을 기록한 이벤트 하나가 조건에 맞을 때만 센다. 순서로만 아는 연결은 `kind: structural`로 두고 지표가 없다.
- 수집되지 않은 지표는 0이 아니라 "수집 안 됨"으로 보인다. 출처 종류마다 채우는 칸을 `coverage`에 적는다.
- 같은 사건을 여러 출처가 기록하면 `source_priority` 앞의 출처만 센다(이중 집계 방지).

**흔한 실수**: 조건 경로를 목록 질의에 없는 필드(`detail`·`raw` 안)로 적기(맞는 이벤트가 없어 칸이 비고 검사가 경고한다), 칸 id를 바꾸고 연결의 `from`·`to`를 그대로 두기(`architecture.unknown_cell`).

**끄기와 남는 데이터**: 플러그인을 지우면 그 프로필이 목록에서 사라진다. 설정의 `default_profile`이 그 id였으면 다른 프로필로 대신 열고 `architecture.profile_fallback` 안내를 단다. 사용자 설정에 적은 같은 id 프로필은 남는다.

<!-- extdocs:facts architecture-profile -->
- 등록: entry point 그룹 `agent_console.architecture_profiles`(상수 `agent_console_architecture:ARCHITECTURE_PROFILES_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_architecture:ProfileSource` — 한 출처가 내는 프로필 묶음.
  - `agent_console_contracts.architecture:ArchitectureProfile` — 구조도 규칙(프로필)입니다. 어떤 칸과 연결을 어디에 그리고 무엇을 셀지 정합니다.
- 설정: `architecture.profiles`, `architecture.include_defaults`
- 기본 구현: —
- 예제:
  - package: [examples/extensions/agent-console-example-architecture](../../examples/extensions/agent-console-example-architecture/README.md)
  - snippet: 사용자 설정 architecture.profiles 데이터
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->

## architecture-profile-check

**언제 쓰나**: 구조도 모듈의 프로필 검사에 다른 기능만 아는 경고를 더한다. 예: 로그 모듈과 잇는 연동이, 로그 목록 본문에 없는 필드를 조건 경로로 쓴 칸을 경고한다.

**최소 모양**: `check(profile, profile_id) -> list[Issue]`를 가진 객체다. `profile`은 계약 `ArchitectureProfile`, `profile_id`는 저장된 id(편집 중 검사면 요청 id 또는 `None`)다. 연동 모듈의 `build`에서 다중 포트로 낸다. 참조 구현은 [로그·구조도 연동](../../packages/py/links/ac-link-logs-architecture/README.md)이다.

```python
from agent_console_contracts import Issue


class NoEmptyCells:
    def check(self, profile, profile_id):
        return [
            Issue(severity="warning", code="example.cell_without_condition",
                  message=f"칸 {cell_id}에 조건이 없습니다", path=f"/cells/{cell_id}")
            for cell_id, cell in profile.cells.items()
            if cell.when is None
        ]
```

**규칙**
- 순수 함수여야 한다. 같은 프로필이면 같은 결과를 돌려준다. 구조도 모듈은 입력이 바뀔 때만 다시 부른다.
- 이슈 코드는 자기 접두사를 쓴다. 심각도는 보통 `warning`이다. 저장을 막지 않고 목록·편집 화면에 함께 보인다.
- 예외는 그 검사만 건너뛰게 한다. 프로필을 고치지 않는다.

**흔한 실수**: 검사 안에서 로그 색인 같은 무거운 저장소를 매번 읽기(필요한 값은 연동이 미리 받아 둔다).

**끄기**: 제공하는 연동 모듈을 끄면 그 경고만 빠진다.

<!-- extdocs:facts architecture-profile-check -->
- 등록: 서버 모듈이 포트 `architecture.profile_checks`(기호 `agent_console_mod_architecture.ports:PROFILE_CHECKS`, 다중 예)를 제공한다.
- 인터페이스:
  - `agent_console_mod_architecture.ports:ProfileCheck` — ``architecture.profile_checks`` 포트 모양: 프로필 검사 보탬.
- 기본 구현: `link-logs-architecture`
- 예제:
  - reference: [packages/py/links/ac-link-logs-architecture](../../packages/py/links/ac-link-logs-architecture/README.md)
- 끄기·제거: 제공하는 모듈을 끄면(`modules.<id>.enabled: false`) 소비하는 쪽은 그 부분만 꺼진다.
<!-- /extdocs:facts -->
