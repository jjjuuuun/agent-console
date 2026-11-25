# 리소스

리소스는 에이전트에 붙이는 재료(지침, 스킬, MCP 서버, 도구 허락, 파일, hook 등)다. 리소스 종류는 그 재료가 실행
묶음의 어느 칸(지침 칸, MCP 서버 칸 …)에 어떤 값으로 들어가는지 정한다. 칸 이름도 코드에 고정된 목록이 아니라
문자열이고, 그 칸을 받을지는 실행 백엔드가 선언한다.

새 종류는 두 길로 만든다.

| 길 | 언제 | 설치 |
| --- | --- | --- |
| 선언형 YAML(코드 없음) | 본문이나 설정 값을 틀에 끼워 칸에 넣으면 충분할 때 | 작업 공간 폴더에 파일 하나 |
| 플러그인(코드) | 값 계산·검사에 코드가 필요할 때(파일 읽기, 여러 칸, 조건부 기여) | 패키지 + entry point |

## resource-type

**언제 쓰나**: 기본 종류로 담을 수 없는 재료를 에이전트에 붙이고 싶을 때. 프롬프트 조각, 팀 공용 노트, 사내 도구
설정이 예다.

### 선언형 종류

작업 공간의 `resource-types/` 폴더(서버 설정 `modules.options.mod-resources.declarative_dir`)에 YAML 파일 하나를
둔다. 서버는 시작할 때 이 폴더를 읽으므로 넣거나 지운 뒤 서버를 다시 시작한다.

```yaml extdocs:validate=agent_console_resources:DeclarativeTypeSpec
id: acme.prompt-snippet
title: 프롬프트 조각
description: 마크다운 본문 하나를 지침에 제목과 함께 넣습니다.
config_schema:
  type: object
  properties:
    tone: {type: string, enum: [formal, casual], title: 말투}
content: {media_types: [text/markdown], editor: markdown}
contributes:
  - slot: instructions
    template: "## {title}\n{content}"
```

- `contributes[]`는 칸마다 하나다. `template`(문자열 틀) 또는 `value`(구조 값, 안의 문자열도 틀) 중 하나만 둔다.
  `raw: true`면 값을 감싸지 않고 그대로 합친다(객체 칸을 `combine: merge`로 합칠 때).
- 틀 변수: `id`·`name`·`description`·`title`(기본은 이름)·`content`(본문) + `config`의 최상위 키(같은 이름이면
  config가 이긴다).
- `content`가 있으면 문서형 종류다. 화면이 본문 편집기를 보인다.
- 형식 오류(모르는 키 포함)나 잘못된 `config_schema`는 그 파일만 로드 실패로 보고된다(`GET /api/v1/server-info`의
  `plugins`). 같은 id의 플러그인 종류가 이미 있으면 선언형 파일 쪽이 실패한다.
- 설치형 예는 [선언형 리소스 종류 예제](../../examples/resource-types/README.md).

### 플러그인 종류

**최소 모양**: `descriptor`(`ResourceTypeDescriptor`), `validate(resource) -> list[Issue]`,
`contribute(resource, content, ctx) -> list[Contribution]`. `config_schema`로 검사만 하면 되는 종류는
`SchemaResourceType`을 상속하고 `contribute`만 쓴다.

- `contribute`는 칸 이름과 값(`Contribution(slot, value)`)을 돌려준다. 실행 백엔드가 그 칸을 받지 않을 때 대신 쓸
  기여를 `fallback`으로 둘 수 있다. 대체 칸도 받지 않으면 묶음 미리보기·검증이 `resource.slot_unsupported`로 알린다.
- 서술자 `contributes`(쓰는 칸 목록)·`combine`(같은 칸에 여럿이 들어올 때 합치는 방법)·`slot_key`(같은 칸 안에서
  항목을 구분하는 설정 필드)를 정확히 적는다. 화면과 미리보기가 이 값으로 설명한다.
- `contribute`는 실행 준비 중에 불린다. 네트워크를 부르거나 오래 걸리는 일을 하지 않는다. 설정 값을 오류 문구에 넣지
  않는다(서버가 이슈에서 값을 가리지만 직접 넣은 문장은 가릴 수 없다).
- 리소스 종류 하나만으로 끝나지 않고 다른 기능(노트·메모리·위키)을 실행에 잇는 일이면 연동 모듈이 종류와 도구
  공급자를 함께 둔다. [연동 예제](../../examples/extensions/agent-console-example-link/README.md)가 그 모양이다.

### 흔한 실수

- 칸 이름을 기본 백엔드가 받지 않는 이름으로 지어 놓고 미리보기 경고를 보지 않는다. 받는 칸은
  `GET /api/v1/backends`의 백엔드 능력(`resource_slots`)에 있다.
- 선언형 파일의 `id`에 접두사를 붙이지 않아 기본 종류(`instruction`·`skill` 등)와 겹친다.

### 지운 뒤 남는 데이터

그 종류로 만든 리소스 파일은 지워지지 않는다. 검증이 `resource.unknown_type` **경고**로 알리고(저장은 막지 않는다,
나중에 다시 설치할 수 있으므로), 그 리소스는 실행 묶음에 기여하지 않는다. 그 리소스를 붙인 에이전트는 다른 리소스로
그대로 실행된다.

<!-- extdocs:facts resource-type -->
- 등록: entry point 그룹 `agent_console.resource_types`(상수 `agent_console_resources:RESOURCE_TYPES_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_resources:ResourceType` — 리소스 종류. entry point `agent_console.resource_types` 또는 선언형 데이터로 등록한다.
  - `agent_console_resources:SchemaResourceType` — `descriptor.config_schema`로 config를 검사하는 리소스 종류 베이스.
  - `agent_console_resources:DeclarativeTypeSpec` — 선언형 종류 파일의 형식.
- 기본 구현: `file (agent-console-resources-core)`, `hook (agent-console-resources-core)`, `instruction (agent-console-resources-core)`, `mcp-server (agent-console-resources-core)`, `memory (agent-console-link-memory-runs)`, `rule (agent-console-resources-core)`, `skill (agent-console-resources-core)`, `tool-permission (agent-console-resources-core)`, `wiki (agent-console-link-wiki-runs)`
- 예제:
  - package: [examples/extensions/agent-console-example-link](../../examples/extensions/agent-console-example-link/README.md)
  - reference: [examples/resource-types](../../examples/resource-types/README.md) — 코드 없는 선언형 종류 prompt-snippet.yaml(workspace resource-types 폴더)
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->
