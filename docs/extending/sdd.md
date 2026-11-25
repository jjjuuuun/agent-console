# SDD

스펙(SDD) 기능은 마크다운 문서에서 작업·요구·단계를 읽어 계획과 추적 표를 만든다. 문서를 읽는 규칙은 데이터이고([sdd-syntax](#sdd-syntax)), 새 스펙의 뼈대는 사용자가 만드는 정의다([spec-template](#spec-template)). 검증 결과([sdd-verification-source](#sdd-verification-source))와 작업 동작([sdd-task-integration](#sdd-task-integration))은 플러그인·연동 모듈로 붙인다.

## sdd-syntax

**언제 쓰나**: 기본 작업 문법(체크 칸 목록 줄, `[키: 값]` 필드, `~` 범위)과 다른 형식의 문서를 읽고 싶을 때. 팀이 쓰는 상태 표시(`[~]` 진행 중 등), 요구 id 모양, 단계로 볼 제목 수준을 바꾼다.

**최소 모양**: 워크스페이스 설정의 `sdd` 섹션 `syntax`(모든 스펙) 또는 스펙 규칙 `rules.syntax`(그 스펙만)다. 비운 항목은 아래 층을 따른다.

```yaml extdocs:validate=agent_console_contracts.sdd:SddSettings
include_default_syntax: true
syntax:
  task:
    statuses:
      - {id: todo, label: 할 일, marker: " "}
      - {id: doing, label: 진행 중, marker: "~", tone: info}
      - {id: done, label: 완료, marker: [x, X], done: true}
    roles: {after: dependencies, req: requirements, who: assignee}
  requirement:
    patterns: ['^#{2,6}\s+(?P<id>REQ-\d+)\b']
  stage:
    heading_levels: [2]
```

**규칙**
- 병합 순서는 패키지 기본 → 사용자 설정 `sdd.syntax` → 스펙 `rules.syntax`(+ `rules.task_statuses`)다. 첫 단계(`task`·`requirement`·`stage`)는 키 단위로 합치고, 그 아래 목록과 `roles`는 통째로 바꾼다. `null`은 상속, 빈 목록은 "이 층에서는 없음"이다.
- 코드가 뜻을 아는 필드 역할은 `dependencies`·`requirements`·`assignee`(+ 선택 `weight`)뿐이다. 어느 필드 이름이 그 역할인지는 `roles`가 정한다.
- 정규식은 이름 그룹을 쓴다(`id`, `key`·`value`). 길이·시간 상한이 있고, 위험한 중첩 반복은 거부된다(`sdd.invalid_pattern`).
- 상태를 바꾸면 그 작업 머리 줄의 체크 칸 글자와 필드 값만 고친다. 다른 바이트는 그대로다.

**흔한 실수**: `statuses`에 한 상태만 적어 기본 상태를 지우기(목록은 통째로 바뀐다), 같은 표시 글자를 두 상태에 주기(`sdd.duplicate_status_marker`), `roles`를 바꾸고 기존 문서의 필드 이름을 그대로 두기(의존이 비어 보인다).

**끄기**: `include_default_syntax: false`면 기본 문법이 빠진다. 사용자 문법도 없으면 작업이 0개이고 `sdd.syntax_missing`이 붙는다. 설정 일부가 깨지면 그 부분만 빼고 `sdd.settings_invalid`로 알린다.

<!-- extdocs:facts sdd-syntax -->
- 등록: 패키지 데이터 `data/default_syntax.yaml`를 설정(`sdd.syntax`)으로 덮어쓴다.
- 인터페이스:
  - `agent_console_contracts.sdd:SpecSyntax` — 작업·요구·단계를 문서에서 읽는 규칙입니다. 비운 항목은 앱 설정이나 기본 규칙을 따릅니다.
  - `agent_console_sdd:load_default_syntax` — 패키지 기본 작업 문법(`data/default_syntax.yaml`)을 읽는다.
- 기본 구현: —
- 예제:
  - snippet: 사용자 설정 sdd.syntax 데이터
- 끄기·제거: 끄는 키: `sdd.include_default_syntax`.
<!-- /extdocs:facts -->

## sdd-task-integration

**언제 쓰나**: 스펙 작업에 동작·링크·이슈·자동 진행을 붙인다. 예: 작업에서 팀 구성을 실행하고 실행 결과로 상태를 바꾸기, 외부 이슈 트래커의 항목을 작업 옆에 보이기. 다른 기능과 잇는 일이라 연동 모듈이 제공한다.

**최소 모양**: `id`와 비동기 메서드 셋이다. 참조 구현은 [실행·SDD 연동](../../packages/py/links/ac-link-runs-sdd/README.md)이다.

```python
class TrackerLinks:
    id = "example.tracker"
    link_kinds = ("issue",)

    async def actions(self, ctx, task):      # -> list[TaskAction]
        return []                            # 이 작업에서 할 수 있는 동작

    async def invoke(self, ctx, task, action, args):   # -> TaskActionResult
        raise NotImplementedError            # 동작을 내지 않으면 불리지 않는다

    async def links(self, ctx, tasks):       # -> list[TaskLink], 모든 작업을 한 번에
        return []
```

**선택 능력**: `check_profile(ctx, profile)`(실행 프로필 검사, 예: `sdd.profile_graph_missing`), `task_issues(ctx, tasks)`(작업마다 이슈를 더한다, 동기), `automation_state`·`control(op)`(자동 진행). 자동 진행 능력이 있는 연동이 없으면 화면에 자동 진행이 보이지 않는다.

**규칙**
- 다중 포트다. 여러 연동의 동작·링크를 모두 모은다.
- `links`는 작업 목록을 한 번에 받는다. 작업마다 따로 외부를 부르지 않는다.
- 파일을 읽어야 하면 `ctx`가 주는 스펙 파일 접근(그 공간 폴더 안만)을 쓴다.
- `link_kinds`에 `run`이 있으면 화면이 실행 능력을 켠다. 능력은 포트 유무로 계산하므로 웹은 모듈 id를 몰라도 된다.

**흔한 실수**: `invoke`에서 작업 문서를 직접 고치기(상태 바꾸기는 SDD 모듈의 고치기 경로로 한다), 외부 호출 실패를 예외로 흘려 목록 전체를 막기(이슈로 돌려준다).

**끄기**: 제공하는 연동을 끄면 그 동작·링크만 빠진다. 문서와 작업 상태는 그대로다.

<!-- extdocs:facts sdd-task-integration -->
- 등록: 서버 모듈이 포트 `sdd.integrations`(기호 `agent_console_mod_sdd.ports:SDD_INTEGRATIONS`, 다중 예)를 제공한다.
- 인터페이스:
  - `agent_console_sdd:TaskIntegration` — 작업 연동(다중 포트 `sdd.integrations`). 기본 구현은 실행(link-runs-sdd).
  - `agent_console_sdd:ProfileChecker` — 선택 능력: 실행 프로필 검사(예: 팀 구성이 공간에 있는지 → `sdd.profile_graph_missing`).
  - `agent_console_sdd:TaskIssueSource` — 선택 능력: 작업 이슈.
  - `agent_console_sdd:AutomationControl` — 선택 능력: 자동 진행 상태·멈춤·다시 시작. 없으면 `capabilities.automation=false`.
- 기본 구현: `link-runs-sdd`
- 예제:
  - reference: [packages/py/links/ac-link-runs-sdd](../../packages/py/links/ac-link-runs-sdd/README.md)
- 끄기·제거: 제공하는 모듈을 끄면(`modules.<id>.enabled: false`) 소비하는 쪽은 그 부분만 꺼진다.
<!-- /extdocs:facts -->

## sdd-verification-source

**언제 쓰나**: 추적 표의 검증 열에 다른 곳의 결과(테스트 보고서, CI 결과)를 넣는다. 결과 파일 형식 하나마다 출처 하나다.

**최소 모양**: `id`와 `async collect(ctx) -> list[VerificationResult]`이다. entry point 값은 출처 객체나 인자 없이 불러 출처를 만드는 클래스다. 전체 예는 [JUnit 예제](../../examples/extensions/agent-console-example-sdd-junit/README.md)다.

```toml
[project.entry-points."agent_console.sdd_verification_sources"]
"example.junit" = "agent_console_example_sdd_junit:JUnitVerificationSource"
```

설치만으로는 쓰이지 않는다. 사용자 설정에서 켜고 옵션을 준다.

```yaml extdocs:validate=agent_console_contracts.sdd:SddSettings
verification_sources:
  - id: example.junit
    enabled: true
    options: {paths: ["reports/**/*.xml"]}
```

**규칙**
- 파일은 `ctx.spec.files`(그 공간 폴더 안만, 링크·앱 구성 폴더 거부)로만 읽는다. 옵션의 경로가 폴더 밖을 가리키면 거부한다.
- 결과는 요구 id나 작업 키에 붙인다. 스펙에 없는 키는 버린다.
- 연동 모듈이 포트로 주는 출처는 설정 없이 쓰이고, 설정에 `enabled: false`로 적으면 꺼진다. 플러그인 출처는 설정에 적어야 켜진다.
- 옵션 값은 출처가 정한다. 틀린 옵션은 결과 없이 돌려주고, 비밀 값·파일 본문을 결과 문장에 싣지 않는다.

**흔한 실수**: 결과 파일을 절대 경로로 받기, XML 엔티티 선언을 그대로 읽기(외부 엔티티 공격).

**끄기와 남는 데이터**: 설정에서 끄거나 패키지를 지우면 검증 열에서 그 출처의 결과가 빠진다. 설정에 남은 항목은 지금은 경고 없이 무시된다.

<!-- extdocs:facts sdd-verification-source -->
- 등록: entry point 그룹 `agent_console.sdd_verification_sources`(상수 `agent_console_mod_sdd:VERIFICATION_SOURCES_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_sdd:VerificationSource` — 검증 결과 출처. entry point `agent_console.sdd_verification_sources` 또는 다중 포트
- 기본 구현: —
- 예제:
  - package: [examples/extensions/agent-console-example-sdd-junit](../../examples/extensions/agent-console-example-sdd-junit/README.md)
  - reference: [packages/py/links/ac-link-runs-sdd](../../packages/py/links/ac-link-runs-sdd/README.md)
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->

## spec-template

**언제 쓰나**: 새 스펙을 만들 때 복사할 문서 뼈대(요구·설계·작업 문서)와 규칙(작업 상태, 문서 상태, 관문, 실행 프로필)을 준비한다. 앱은 틀을 하나도 갖고 오지 않는다. 사용자가 화면·파일·가져오기로 만든다.

**최소 모양**: 정의 종류 `spec-template`의 문서 하나다. 문서마다 파일 이름과 역할(`tasks`·`requirements`)을 적는다. 뼈대 본문은 정의 옆 본문 폴더의 파일이다(화면의 틀 편집이나 SDD 모듈의 틀 파일 경로로 쓴다).

```yaml extdocs:validate=agent_console_contracts.sdd:SpecTemplate
kind: spec-template
id: feature
name: 기능 개발
description: 요구 → 작업 두 문서
documents:
  - {id: requirements, title: 요구사항, file: requirements.md, roles: [requirements]}
  - {id: tasks, title: 작업, file: tasks.md, roles: [tasks]}
rules:
  task_statuses:
    - {id: todo, label: 할 일, marker: " "}
    - {id: done, label: 완료, marker: x, done: true}
```

**규칙**
- 스펙을 만들 때 틀의 `documents`·`rules`와 뼈대 파일을 복사한다. 그 뒤 스펙은 틀과 독립이다. 틀을 고쳐도 이미 만든 스펙은 바뀌지 않는다.
- 문서 역할 `tasks`·`requirements`가 있는 문서만 작업·요구로 읽는다. 역할 없는 문서는 있는지와 해시만 본다.
- 틀은 라이브러리와 프로젝트 공간 모두에 둘 수 있고 프로젝트로 옮길 수 있다. 실행 프로필이 가리키는 팀 구성은 복사할 때 함께 따라간다.
- 종류 이름(`spec-template`)은 SDD 모듈 설치자 데이터의 기본값이다. 설치자가 바꾸면 `kind` 값도 그 이름이다.

**흔한 실수**: 같은 `file`을 두 문서에 주기, 실행 프로필의 팀 구성을 라이브러리에만 두고 틀을 프로젝트로 옮기기(복사 계획이 함께 가져오지만, 건너뛰면 `sdd.profile_graph_missing`).

**끄기**: 틀을 지워도 그 틀로 만든 스펙은 남는다.

<!-- extdocs:facts spec-template -->
- 등록: 등록 종류 `definition`.
- 인터페이스:
  - `agent_console_contracts.sdd:SpecTemplate` — 문서 틀입니다. 스펙을 만들 때 문서 뼈대와 규칙을 그대로 복사합니다.
- 기본 구현: —
- 예제:
  - snippet: 문서 틀 정의 데이터
<!-- /extdocs:facts -->
