# agent-console-resources

리소스 종류(X14) 등록과 **실행 묶음(ResourceBundle) 조립**. 종류 이름·칸 이름은 이 패키지에 없다.
설계: `specs/agent-console/design.md` §R12.1~§R12.4, §R2(층 병합), §R9.3(`x-merge: keyed_attachments`).

- **종류 등록**: entry point `agent_console.resource_types`, 명시 모듈 목록, 또는 **선언형 데이터**
  (`<workspace>/resource-types/*.yaml`, 코드 없음). 등록 key = 리소스 정의의 `type`.
- **첨부 병합**: 층(공통 → 팀 구성 → 에이전트 → 노드 …, 호출자 데이터)의 `ResourceAttachment` 목록을
  `ac-settings` 전략 표에 등록한 `keyed_attachments` 전략으로 합친다(`add`·`replace`·`remove`, 원소별 출처).
- **묶음 조립**: 남은 첨부마다 종류의 `validate`·`contribute`(순수 함수)를 부르고, 칸별로 종류의
  `combine` 전략(기본 `append`)으로 합쳐 `ResourceBundle{slots, sources}`를 만든다.
- 파일 쓰기·비밀 해석·네트워크를 하지 않는다. 비밀은 `secret://이름` 참조 그대로 묶음에 들어간다.
- 문제는 예외 대신 `Issue`로 돌려준다(리소스·종류 없음, 설정 오류, 받지 못하는 칸 등).

## 설치

```bash
uv sync --all-packages                        # 워크스페이스 안
uv pip install ./packages/py/features/ac-resources     # 단독
```

## 최소 사용 예

```python
>>> from agent_console_contracts import Resource, ResourceAttachment
>>> from agent_console_resources import (
...     AttachmentLayer,
...     InMemoryResources,
...     compose_bundle,
...     declarative_type_from_data,
...     load_resource_types,
...     new_resource_types,
... )

>>> types = new_resource_types()
>>> _ = load_resource_types(types)  # 설치된 플러그인(예: ac-resources-core). 보고서 목록을 돌려준다
>>> fragment = declarative_type_from_data(  # 선언형 종류(보통은 load_declarative_types(폴더, types))
...     {
...         "id": "prompt-fragment",
...         "title": "프롬프트 조각",
...         "config_schema": {"type": "object", "properties": {"title": {"type": "string"}}},
...         "slot_key": "title",
...         "contributes": [{"slot": "instructions", "template": "## {title}\n{content}"}],
...     }
... )
>>> _ = types.register(fragment.descriptor.id, fragment)

>>> resources = InMemoryResources(  # 보통은 저장소가 ResourceLookup을 구현
...     [
...         Resource(
...             id="tip",
...             type="prompt-fragment",
...             name="팁",
...             config={"title": "팁"},
...             content={"file": "content.md"},
...         )
...     ],
...     contents={"tip": "짧게 답한다."},
... )
>>> result = compose_bundle(
...     [
...         AttachmentLayer("team", [ResourceAttachment(ref="tip")], label="팀 구성"),
...         AttachmentLayer("node", [ResourceAttachment(ref="nope")], label="이 팀의 노드"),
...     ],
...     types=types,
...     resources=resources,
...     accepted_slots=["instructions", "files"],  # 백엔드 capabilities.resource_slots
... )
>>> result.bundle.slots
{'instructions': ['## 팁\n짧게 답한다.']}
>>> [(s.ref, s.layer) for s in result.bundle.sources["instructions"]]
[('tip', 'team')]
>>> [i.code for i in result.issues]  # 경고·오류(첨부는 건너뛰고 계속)
['resource.not_found']

```

### 설정 층 병합과 함께 (유효 설정 계산 쪽)

계약 `AgentSettings.resources`의 스키마 주석은 `x-merge: keyed_attachments`다. 유효 설정을 계산할 때
같은 전략 표를 넘기면 첨부도 같은 규칙으로 합쳐지고, 결과에서 바로 묶음을 만들 수 있다.

```python
from agent_console_resources import (
    attachment_slot_key,
    build_bundle,
    placed_from_resolved,
    resource_strategies,
)
from agent_console_settings import resolve_layers

table = resource_strategies(slot_key_of=attachment_slot_key(types, resources))
resolved = resolve_layers(layers, schema=agent_settings_schema, strategies=table)
bundle = build_bundle(
    placed_from_resolved(resolved), types=types, resources=resources, strategies=table
)
```

이미 있는 전략 표에 더하려면 `register_resource_strategies(table, slot_key_of=...)`.

## 첨부 방식

| 방식 | 동작 |
| --- | --- |
| `add`(기본) | 뒤에 붙인다. 같은 리소스·같은 덮어쓰기가 또 오면 묶음에서 한 번만 쓴다(`resource.duplicate`, info). |
| `replace` | 위 층 첨부 중 같은 리소스 id **또는** 같은 슬롯 키(종류의 `slot_key` config 값, 예: instruction의 `title`)를 가진 것을 그 자리에서 바꾼다. 없으면 더하고 `resource.replace_unmatched`(info). |
| `remove` | 위 층의 같은 리소스 id 첨부를 뺀다. 없으면 `resource.remove_unmatched`(info). |

`config_override`는 리소스 config에 얕게 덮어쓴다(`effective_resource`).

## 리소스 종류 만들기

### 1) 플러그인(코드)

```python
from agent_console_contracts import ResourceTypeDescriptor
from agent_console_resources import Contribution, SchemaResourceType


class GreetingType(SchemaResourceType):
    descriptor = ResourceTypeDescriptor(
        id="greeting",
        title="인사",
        contributes=["instructions"],
        config_schema={"type": "object", "properties": {"who": {"type": "string"}}},
    )

    def contribute(self, resource, content, ctx):
        return [Contribution("instructions", [f"{resource.config.get('who', '')}에게 인사한다."])]
```

```toml
[project.entry-points."agent_console.resource_types"]
greeting = "my_plugin:GreetingType"
```

`validate`는 `SchemaResourceType`이 `config_schema`로 검사한다(추가 검사는 `extra_issues`).
`Contribution(slot, value, combine=None, fallback=None)`의 `combine`으로 이 기여만 다른 전략(예: `prepend`)을 쓸 수 있다.

- **대체 칸**(`fallback`, 2R.12): 실행 백엔드가 `slot`을 받지 않으면(`accepted_slots`에 없음) 대신 쓸 기여.
  예: 경로 조건 지침(`rules`)을 못 받는 백엔드에는 일반 지침(`instructions`)으로. 바꾸면 info `resource.slot_fallback`.
- **여러 파일 본문**(2R.12): 디스크립터 `content.multi_file=true`인 종류는 `contribute`의 `content`로 `{경로: 바이트}`
  (`ContentFiles`)를 받는다. 조회 객체가 선택 능력 `FileContentLookup.read_files(resource)`를 가져야 한다
  (`InMemoryResources`·`MaskedResources`·ac-nodes-core `FunctionResources(find, read, read_files)`). 없으면
  `resource.content_unreadable` 경고와 함께 `None`.
- **받지 않는 칸 설명**: `build_bundle`·`compose_bundle`의 `slot_notes={칸: 설명}`(백엔드 `capabilities.slot_notes`)를
  주면 `resource.slot_unsupported` 경고의 `details.reason`·문구에 붙는다.

### 2) 선언형 데이터(코드 없음)

```yaml
# <workspace>/resource-types/prompt-fragment.yaml
id: prompt-fragment
title: 프롬프트 조각
config_schema: {type: object, properties: {title: {type: string}}}
content: {media_types: [text/markdown], editor: markdown}
slot_key: title
contributes:
  - slot: instructions
    template: "## {title}\n{content}"          # 결과 문자열 하나가 칸 항목 하나
  - slot: mcp_servers                          # 구조 값(문자열마다 치환) → 항목 하나
    value: {name: "{title}", type: stdio, command: echo}
  - slot: env_map                              # raw: 감싸지 않고 그대로(객체 칸 + merge)
    value: {A: "{title}"}
    raw: true
    combine: merge
```

치환은 안전 치환(`{이름}`만, 속성·인덱스 접근 없음, 모르는 이름은 그대로)이다. 변수는
`id`·`name`·`description`·`title`(기본 이름)·`content` + config 최상위 키.

## 비밀 필드 표시 `x-secret`

config 스키마에서 비밀 값이 들어갈 위치에 `x-secret: true`(상수 `SECRET_SCHEMA_KEY`)를 단다. 화면은 이 구조화
힌트로 비밀 입력 칸(가림·`secret://` 참조 고르기)을 그린다 — description 문구로 추측하지 않는다.
플러그인 종류와 선언형 종류 모두 같다. 2R.4부터 `SchemaResourceType.validate`가 이 위치의 평문(참조가 아닌 값)을
**일반 규칙으로 거부한다**(`find_schema_plain_secrets` → `resource.plain_secret` error, 값 없는 메시지). 선언형
종류도 `pattern`을 따로 달 필요가 없다. 종류가 `extra_issues`로 같은 위치를 이미 보고하면 한 번만 낸다.

```yaml
# <workspace>/resource-types/api-token.yaml
id: api-token
title: API 토큰
config_schema:
  type: object
  properties:
    token: {type: string, x-secret: true}   # 평문이면 resource.plain_secret
contributes:
  - slot: env_map
    value: {API_TOKEN: "{token}"}
    raw: true
    combine: merge
```

## 종류 검사(`validate`·`extra_issues`) 계약

리소스 종류를 만드는 쪽(플러그인·선언형)이 지켜야 한다. 서버는 저장(REST `POST/PUT /resources`, 프리셋 적용)
전에 `validate_resource`로 이 검사를 부르고 error 이슈가 있으면 저장하지 않는다.

- **메시지에 입력값을 넣지 않는다.** 무엇이 잘못됐는지(규칙)만 쓰고, 값은 쓰지 않는다.
- **`path`를 정확히 지정한다.** 문제 값의 config 기준 JSON Pointer(예: `/env/API_KEY`, `~`·`/`는 `~0`·`~1`).
  서버는 응답에서 문서 기준(`/config/env/API_KEY`, 첨부 덮어쓰기면 `/resources/0/config_override/env/API_KEY`)으로
  바꾸고, 화면은 이것으로 해당 칸에 오류를 붙인다. 첨부 검사(`validate_attachment`)도 이 path로 덮어쓰기 탓인지 가린다.
- `scrub_issue_values`는 안전망일 뿐이다: **`path`가 가리키는 값만** 메시지에서 지운다. path가 없거나 다른 곳을
  가리키면, 또는 짧은(3자 미만) 값이면 메시지에 남은 값을 지우지 못한다.
- 예외를 던지지 않는다(던지면 error `resource.type_failed`로 저장이 막힌다). 순수 함수(파일·네트워크·비밀 해석 없음).

## 공개 API

| 이름 | 설명 |
| --- | --- |
| `ResourceType`(Protocol) | `descriptor`, `validate(resource) -> list[Issue]`, `contribute(resource, content, ctx) -> list[Contribution]` |
| `Contribution(slot, value, combine=None)`, `ContributeContext(attachment, layer)` | 기여·맥락 |
| `ResourceLookup`(Protocol), `InMemoryResources` | `get_resource(ref)`, `read_content(resource)` |
| `FileContentLookup`(Protocol, 선택 능력), `Content`, `ContentFiles` | `read_files(resource) -> {경로: 바이트} \| None`(여러 파일 본문 종류) |
| `SchemaResourceType` | config_schema 검사 베이스(`extra_issues` 훅) |
| `RESOURCE_TYPES_GROUP`, `new_resource_types()`, `load_resource_types(registry, *, enabled, modules, entry_points)`, `as_resource_type`, `list_descriptors` | 등록 |
| `load_declarative_types(dir, registry, *, read, files)`, `declarative_type_from_data(data)`, `DeclarativeResourceType`, `DeclarativeTypeSpec`, `ContributionSpec`, `DeclarativeTypeError` | 선언형 종류 |
| `ATTACHMENT_STRATEGY`(`keyed_attachments`), `PREPEND_STRATEGY`, `keyed_attachments_strategy(slot_key_of)`, `attachment_slot_key(types, resources)`, `prepend`, `register_resource_strategies`, `resource_strategies` | 병합 전략 |
| `compose_bundle(layers, *, types, resources, accepted_slots, strategies, slot_notes) -> ComposedBundle`, `SLOT_UNSUPPORTED`, `SLOT_FALLBACK`, `resolve_attachments`, `build_bundle`, `placed_from_resolved`, `unsupported_slots`, `AttachmentLayer`, `PlacedAttachment` | 묶음 |
| `effective_resource`, `content_text`, `is_secret_ref`, `find_plain_secrets`, `find_schema_plain_secrets`, `PLAIN_SECRET`, `SECRET_REF_PREFIX`, `SECRET_REF_PATTERN`, `SECRET_SCHEMA_KEY`(`x-secret`), `validate_config`, `check_config_schema`, `render_template`, `fill_value` | 도우미 |
| `validate_attachment(attachment, *, types, resources, path="", override_path=None, ref_path=None, secret_rules=None) -> list[Issue]` | 첨부 `config_override`를 리소스 config에 얕게 덮어쓴 결과를 종류 검사. 덮어쓰기가 만든 이슈만(덮어쓴 키 아래 이슈는 항상), path = `<override_path>/...`. 리소스 없음은 warning(ref 위치) + 비밀 의심 규칙(`ac-secret-rules`의 `SecretRules`, 기본 = 기본 규칙)에 걸린 값마다 error `resource.override_secret_suspected`, 종류 없음은 warning(ref 위치) |
| `mask_plain_secrets(value, schema)`, `mask_resource(resource, types)`, `mask_attachment(attachment, *, types, resources)`, `MaskedResources(lookup, types)`, `SECRET_MASK` | 표시용 안전망: `x-secret` 위치의 `secret://`가 아닌 값을 `***`로(`properties`·`additionalProperties`·`items`·`allOf/anyOf/oneOf`를 따라감, `$ref`는 안 따라감) |
| `validate_resource(resource, types) -> list[Issue]`, `scrub_issue_values(issues, config)` | 저장 전 검사: 종류의 `validate`를 부르고(모르는 종류 = warning `resource.unknown_type`, 예외 = error `resource.type_failed`) 이슈 `path`가 가리키는 config 값을 메시지에서 `***`로 지운다. 서버가 error 이슈면 저장을 거부한다 |

## 이슈 코드

`resource.not_found`·`resource.unknown_type`(warning, 첨부 건너뜀), `resource.invalid_config`·
`resource.invalid_type_schema`(error, 건너뜀), `resource.type_failed`(종류 구현 예외, error),
`resource.content_missing`·`resource.content_unreadable`, `resource.duplicate`,
`resource.replace_unmatched`·`resource.remove_unmatched`(info), `resource.slot_unsupported`(warning, `details.reason` =
백엔드 설명), `resource.slot_fallback`(info, `details.slot`·`fallback`),
`resource.merge.*`(전략 문제). `details`에 `resource`·`layer`·`slot` 등이 들어간다.

**이슈 메시지에는 입력값이 들어가지 않는다**(비밀 누출 방지). `validate_config`는 jsonschema의
`err.message`(입력값을 담음) 대신 검사 종류와 스키마의 기대값(형식, 허용 값 목록, pattern 존재 여부,
필수 키 이름 등)만으로 메시지를 만들고, 위치는 `Issue.path`(JSON Pointer)로 알린다. 종류 구현의 예외도
메시지에는 예외 타입 이름만 남긴다.

## 의존성

| 무엇을 | 왜 | 대안 |
| --- | --- | --- |
| `jsonschema` | config_schema 검사(워크스페이스에서 이미 사용) | 직접 검사(불완전) |
| `ruamel.yaml` | 선언형 종류 YAML 읽기(정의 저장과 같은 라이브러리) | PyYAML |
| `pydantic` | 선언형 종류 형식 검사·계약 모델 | 손 검사 |
| `ac-secret-rules`(사내) | 리소스가 없는 첨부 덮어쓰기의 비밀 의심 판정(서버·가져오기와 같은 규칙, 사용자 규칙 주입) | 계약 패키지 안 모듈(1R, 사용자 규칙을 넣을 수 없었음) |

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-resources`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
uv run pytest packages/py/features/ac-resources
```
