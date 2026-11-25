# 서버 호스트·모듈

서버 앱은 기능 이름을 모른다. 기능은 서버 모듈로, 기본 서비스(플러그인 레지스트리 묶음, 플러그인 로더, DB)는 호스트
확장 entry point로 들어온다. 이 페이지는 그 지점과, 모듈이 다른 모듈에 기여하는 공용 지점(정의 종류, DB 계보 범위,
실행 라벨)을 다룬다. 모듈 자체를 만드는 방법은 [서버 모듈](modules.md)과 [연동 모듈](links.md)에 있고, 여기서는 지점마다
다른 것만 적는다.

| 하고 싶은 일 | 지점 |
| --- | --- |
| 새 기능(REST·저장소·설정 섹션)을 서버에 더한다 | [server-module](#server-module) |
| 정의 저장소에 새 정의 종류를 더한다 | [definition-kind-contribution](#definition-kind-contribution) |
| 모듈의 DB 표를 프로젝트 기록 DB에도 둔다 | [migration-scope](#migration-scope) |
| 실행에 꼬리표를 달아 묶고 거른다 | [run-labels](#run-labels) |
| 정의를 파일 말고 다른 곳에 저장하는 라이브러리를 쓴다 | [definition-store](#definition-store) |
| 서버를 다른 앱에 넣으며 기본 서비스를 바꾼다 | [host-registries](#host-registries), [host-plugin-loader](#host-plugin-loader), [host-database](#host-database) |

뒤의 세 호스트 지점은 서버를 다른 앱에 넣거나 기본 서비스를 통째로 바꾸는 사람을 위한 것이다. 플러그인·모듈을 만드는
일에는 필요 없다.

## definition-kind-contribution

**언제 쓰나**: 모듈이 자기 데이터를 사용자가 고치는 정의(작업 공간의 YAML 파일, 버전 기록, 사용처 표시, 내보내기·
프로젝트 공간 포함)로 두고 싶을 때. 문서 틀, 규칙 묶음, 프로필처럼 사용자가 화면·파일로 만들고 고치는 것이다.

**최소 모양**: 모듈 서술자에 `provides=[DEFINITION_KIND_CONTRIBUTIONS]`(포트 `definitions.kind_contributions`, 여러
제공자)를 적고 `build`에서 종류마다 `ctx.provide(DEFINITION_KIND_CONTRIBUTIONS, KindContribution(kind, references=,
summary_fields=))`를 한 번씩 부른다. `kind`는 정의 저장소의 종류 규칙(`DefinitionKind` — 이름, 폴더, 검증 모델, 본문
방식, `library`·`portable`)이다. 정의 모듈이 모아 저장소에 등록한다.

**규칙**

- 종류 이름과 폴더는 모듈 접두사로 짓는다. 기본 종류(`agent`·`graph`·`resource` …)와 겹치면 안 된다.
- `references`는 문서 하나에서 다른 정의 참조 `(종류, id)` 목록을 뽑는 순수 함수다. 사용처 표시와 지우기 전 경고에
  쓰인다. 예외는 소비자가 삼키므로 참조가 조용히 빠진다. 시험으로 확인한다.
- 검증 모델은 계약 쪽 Pydantic 모델을 쓰고, 모르는 키를 받을지 거부할지 모델이 정한다.
- 정의 모듈이 꺼져 있어도 내 모듈은 시작해야 한다. 이 포트는 내가 **제공**하는 것이라 소비자가 없으면 그냥 쓰이지 않는다.

**흔한 실수**: 종류 문서를 모듈 자기 DB 표에 따로 저장한다. 그러면 버전·내보내기·프로젝트 공간이 따라오지 않는다.
사용자가 고치는 것은 정의 종류로, 실행 결과처럼 쌓이는 것은 자기 표로 둔다.

**지운 뒤 남는 데이터**: 모듈을 끄거나 지우면 종류가 등록되지 않아 목록·화면에 나오지 않는다. 작업 공간의 그 종류
폴더와 파일은 남고, 다시 켜면 그대로 보인다.

<!-- extdocs:facts definition-kind-contribution -->
- 등록: 서버 모듈이 포트 `definitions.kind_contributions`(기호 `agent_console_modkit:DEFINITION_KIND_CONTRIBUTIONS`, 다중 예)를 제공한다.
- 인터페이스:
  - `agent_console_modkit:KindContribution` — 정의 종류 하나의 기여.
  - `agent_console_modkit:KindReferences` — 기여 종류 문서 하나가 쓰는 정의의 ``(종류, id)``(복사 계획의 참조 닫힘).
  - `agent_console_modkit:KindDelete` — 기여 종류 항목 하나 지우기 ``(공간, id, 기대 버전)``.
- 기본 구현: `mod-sdd`, `mod-wiki`
- 예제:
  - package: [examples/extensions/agent-console-example-module](../../examples/extensions/agent-console-example-module/README.md)
- 끄기·제거: 제공하는 모듈을 끄면(`modules.<id>.enabled: false`) 소비하는 쪽은 그 부분만 꺼진다.
<!-- /extdocs:facts -->

## definition-store

**언제 쓰나**: 정의 라이브러리(`agent-console-store`)를 서버 없이 다른 스크립트·앱에서 쓰면서 저장 위치를 바꾸고 싶을
때. 데이터베이스, 원격 저장소, 시험용 메모리가 예다. 서버 안에서는 정의 모듈이 파일 저장소를 만들며, 이를 바꾸는 설정은
없다.

**최소 모양**: `BaseDefinitionStore`를 상속하고 원시 입출력 `_read`·`_write`·`_remove`·`_ids`를 채운다. 본문 파일이 있는
종류(리소스 등)를 다루려면 본문 훅(`_read_body`·`_write_body`·`_remove_body`·`_list_body`·`_body_ids`)도 채운다. 버전
기록·해시·낙관적 잠금(`expected_version`)·크기 한도는 기반 클래스가 한다.

**규칙**

- `_read`는 없으면 None, 읽을 수 없으면 `DefinitionCorrupt`다. 다른 예외로 바꾸지 않는다.
- 종류 목록·버전 기록 저장소·시계·해시 함수는 생성자로 주입받는다. 전역에서 꺼내지 않는다.
- 쓰기 전에 검사가 필요하면 `write_guard`를 넘긴다. 거부하면 아무것도 바뀌지 않는다.

**흔한 실수**: 공개 메서드(`save`·`create`)를 재정의한다. 버전·잠금 규칙이 깨진다. 원시 메서드만 채운다.

**지운 뒤 남는 데이터**: 라이브러리 지점이라 서버 설정·사용자 데이터에 이름이 남지 않는다.

<!-- extdocs:facts definition-store -->
- 등록: 생성자·인자로 구현을 주입한다(인터페이스를 따르는 객체).
- 인터페이스:
  - `agent_console_store:DefinitionStore` — 정의(graph, agent, settings 등) 저장소. 종류는 `DefinitionKind`로 등록한다.
  - `agent_console_store:BaseDefinitionStore` — `DefinitionStore` 공통 구현. 하위 클래스는 원시 문서 입출력 다섯 개만 채운다.
- 기본 구현: —
- 예제:
  - reference: [packages/py/features/ac-store](../../packages/py/features/ac-store/README.md) — FileDefinitionStore(파일 YAML)·InMemoryDefinitionStore
- 끄기·제거: 주입하지 않으면 기본 구현을 쓴다.
<!-- /extdocs:facts -->

## host-database

**언제 쓰나**: 서버가 쓰는 공용 DB를 다른 엔진·위치로 바꾸고 싶을 때. 기본 구현은 SQLite다.

**최소 모양**: entry point가 `(Path) -> DatabaseHandle` 함수를 가리킨다. 핸들은 `engine`(SQLAlchemy 엔진),
`upgrade(branches)`(켜진 모듈의 계보 올리기), `close()`다. 이름 순 첫 번째 공장 하나만 쓴다.

**규칙**

- 공장이 DB를 열지 못하면 예외를 던진다. 서버 시작 실패로 본다.
- 계보 올리기는 모듈이 켜질 때만 그 모듈 계보로 불린다. 핸들이 계보를 고르지 않는다.
- 공장이 하나도 없으면 서버는 DB 없이 시작하고, 저장소가 필요한 모듈은 메모리로 동작하거나 그 기능을 끄고 알린다.

**흔한 실수**: 기본 공장과 다른 이름으로 하나 더 설치하고 쓰일 거라 기대한다. 이름 순 첫 번째만 쓰이므로 기본 공장을
지우거나 이름 순서를 맞춘다.

**지운 뒤 남는 데이터**: DB 파일은 지워지지 않는다. 공장이 없어지면 다음 시작부터 DB 없이 동작한다.

<!-- extdocs:facts host-database -->
- 등록: entry point 그룹 `agent_console.host_database`(상수 `agent_console_modkit:HOST_DATABASE_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_modkit:DatabaseHandle` — 공용 DB 핸들(호스트가 만들어 모듈에 준다). 모듈은 엔진을 직접 만들지 않는다.
- 기본 구현: `sqlite (agent-console-store)`
- 예제:
  - contract-tests: `agent_console_modkit.testing:open_recording_database`
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->

## host-plugin-loader

**언제 쓰나**: 새 확장 지점을 정의하는 모듈이 자기 그룹의 플러그인을 서버 시작 때 레지스트리에 읽어 들여야 할 때. 기본
모듈(실행·리소스·로그·사용량 …)이 각자 이 로더로 자기 그룹을 읽는다. 플러그인을 만드는 사람에게는 필요 없다.

**최소 모양**: entry point가 `PluginLoader`, 즉 `(PluginLoadContext) -> (보고 그룹, LoadReport) 목록` 함수를 가리킨다.
맥락에는 레지스트리 묶음, 읽을 이름(`enabled` — `plugins.enabled`에서 `plugins.disabled`를 이미 뺀 값), 제외 목록
(`disabled`), 호스트 경로, 설치자 모듈 설정 원본이 있다. entry point를 `load_entry_points(..., enabled=ctx.enabled)`로
읽으면 두 설정이 다른 그룹과 같은 규칙으로 걸린다. entry point가 아닌 이름을 쓰는 로더는 `ctx.allows(이름)`으로
판정한다.

**규칙**

- `registries.extension(이름, validator=)`로 자기 레지스트리에 검사기를 붙인 뒤 entry point를 읽는다. 그 뒤
  `plugins.modules`로 들어오는 플러그인도 같은 검사기를 거친다.
- 허용 목록(`ctx.enabled`)을 지킨다. 없으면(None) 설치된 것 전부다.
- 실패는 예외 대신 보고로 돌려준다. 보고는 `GET /api/v1/server-info`의 `plugins`에 나온다.
- 자기 모듈 설정은 `ctx.options[모듈 id]`에서 읽고 직접 검증한다. 틀리면 기본값을 쓰고 경고를 남긴다.

**흔한 실수**: 로더가 모듈 `build`에서 쓸 서비스를 만든다. 로더는 레지스트리에 등록만 하고, 서비스는 `build`에서 만든다.

**지운 뒤 남는 데이터**: 그 그룹의 플러그인이 읽히지 않는다. 그 그룹 이름을 쓰는 사용자 데이터는 해당 지점의 "모르는
이름" 이슈로 알린다.

<!-- extdocs:facts host-plugin-loader -->
- 등록: entry point 그룹 `agent_console.host_plugin_loaders`(상수 `agent_console_modkit:HOST_PLUGIN_LOADERS_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_modkit:PluginLoader` — 플러그인 로더: 묶음에 로드하고 ``(보고 그룹, 보고)``를 돌려준다. 실패는 예외 대신 보고.
  - `agent_console_modkit:PluginLoadContext` — 플러그인 로더가 받는 것.
- 기본 구현: `architecture (agent-console-mod-architecture)`, `exports (agent-console-mod-exports)`, `imports (agent-console-mod-imports)`, `logs (agent-console-mod-logs)`, `memory (agent-console-mod-memory)`, `projects (agent-console-mod-projects)`, `resources (agent-console-mod-resources)`, `runs (agent-console-mod-runs)`, `sdd (agent-console-mod-sdd)`, `usage (agent-console-mod-usage)`, `wiki (agent-console-mod-wiki)`
- 예제:
  - contract-tests: `agent_console_modkit.testing:example_plugin_loader`
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->

## host-registries

**언제 쓰나**: 서버를 다른 앱에 넣으면서 레지스트리 묶음을 자기 것으로 바꾸고 싶을 때. 묶음이 이름 붙은 레지스트리
외에 속성(형식이 있는 필드)을 가져야 하는 경우다. 기본 구현은 실행 모듈이 주는 묶음이다.

**최소 모양**: entry point가 인자 없는 함수를 가리키고, 함수는 `RegistryBundle`(`extension(name, *, validator=None)`·
`all()`)을 돌려준다. 이름 순 첫 번째 공장 하나만 쓴다. 없거나 실패하면 이름 붙은 레지스트리만 있는 `ExtensionRegistries`다.

**규칙**

- `extension(name)`은 없으면 만들고, 검사기를 주면 붙인다. 같은 이름이면 같은 레지스트리를 돌려준다.
- 비밀 공급자는 묶음의 `secret_providers` 레지스트리에서 찾는다. 묶음을 바꿔도 이 이름은 지킨다.

**흔한 실수**: 공장이 실패하면 서버가 멈출 거라 생각한다. 실패는 보고로 남고 기본 묶음으로 시작하므로, 보고를 확인한다.

**지운 뒤 남는 데이터**: 없다. 다음 시작부터 기본 묶음을 쓴다.

<!-- extdocs:facts host-registries -->
- 등록: entry point 그룹 `agent_console.host_registries`(상수 `agent_console_modkit:HOST_REGISTRIES_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_modkit:RegistryBundle` — 레지스트리 묶음이 갖출 최소 모양.
  - `agent_console_modkit:ExtensionRegistries` — 기본 레지스트리 묶음(공장 entry point가 없을 때). 이름 붙은 레지스트리만 있다.
- 기본 구현: `runs (agent-console-mod-runs)`
- 예제:
  - reference: [packages/py/modules/ac-mod-runs](../../packages/py/modules/ac-mod-runs/README.md) — plugins.create_registries — 실행 레지스트리 묶음
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->

## migration-scope

**언제 쓰나**: 모듈의 표가 앱 DB 하나에만 있으면 안 되고, 프로젝트 폴더에 딸린 기록 DB에도 있어야 할 때. 실행 기록처럼
프로젝트와 함께 옮겨 다녀야 하는 데이터다.

**최소 모양**: 서술자 `migrations`의 `MigrationBranch(name, versions, scopes)`에서 `scopes`를 적는다. 기본 `("app",)`은
앱 DB에만, `("app", "project")`면 프로젝트 기록 DB를 여는 연동이 같은 계보를 그 DB에도 올린다. 범위 이름은 열린
문자열이다. 계보 전체 설명은 [서버 모듈의 저장소](modules.md#저장소db-계보).

**규칙**

- 같은 계보가 두 DB에 올라가므로 리비전은 두 곳 모두에서 같은 결과를 내야 한다. 앱 DB에만 있는 다른 표에 기대지 않는다.
- 프로젝트 기록 DB를 열고 계보를 올리는 쪽은 프로젝트 연동이다. 내 모듈이 그 DB가 열려 있다고 가정하지 않는다.

**흔한 실수**: 범위를 더한 뒤 옛 리비전을 고친다. 이미 올라간 DB가 있으므로 새 리비전을 더한다.

**지운 뒤 남는 데이터**: 범위에서 빼면 새로 여는 프로젝트 DB에는 계보를 올리지 않는다. 이미 만든 표와 데이터는 남는다.

<!-- extdocs:facts migration-scope -->
- 등록: 서술자 필드 `MigrationBranch.scopes`에 값을 넣는다.
- 인터페이스:
  - `agent_console_modkit:MigrationBranch` — 모듈이 소유한 마이그레이션 계보(패키지 데이터 폴더).
- 기본 구현: —
- 예제:
  - package: [examples/extensions/agent-console-example-module](../../examples/extensions/agent-console-example-module/README.md)
- 끄기·제거: 필드를 비우면 기본값을 쓴다.
<!-- /extdocs:facts -->

## run-labels

**언제 쓰나**: 다른 기능·스크립트가 자기가 시작한 실행을 묶고 나중에 거르고 싶을 때. 어떤 명세로 시작한 실행인지,
어떤 배치 작업의 실행인지를 꼬리표로 단다. 코드 등록은 없고 실행 기록의 필드 하나다.

**모양**: 실행 시작 요청 `POST /api/v1/runs`의 `labels`(문자열 → 문자열). 루트 실행에 붙는다.

```json extdocs:validate=agent_console_contracts:CreateRunRequest
{
  "graph_id": "review-team",
  "input": {"task": "변경 검토"},
  "origin": "acme.nightly",
  "labels": {"acme.batch": "2026-11-07", "acme.ticket": "OPS-142"}
}
```

목록은 `GET /api/v1/runs?label=acme.batch=2026-11-07`처럼 거른다. 여러 번 주면 모두 맞아야 한다(AND). 값에 `=`가 있어도
된다(첫 `=`에서 나눈다).

화면에 칩으로 보이려면 라벨을 다는 모듈이 `build` 결과 `ModuleParts.label_display`에 표시 규칙을 낸다. 웹은
`GET /api/v1/modules`에서 모아 같은 키의 라벨을 칩으로 그리고, `target.role`을 맡은 화면이 있으면 링크로 만든다.

```yaml extdocs:validate=agent_console_contracts:LabelDisplay
key: acme.ticket
title: 티켓
target: {role: acme-tickets, id_from: acme.ticket}
order: 10
```

**규칙**

- 키는 자기 접두사로 짓는다(다른 기능의 라벨과 겹치지 않게). 접두사를 설치자 설정으로 바꿀 수 있게 하면 더 좋다.
- 상한: 라벨 16개, 키 64자, 값 256자. 넘으면 시작 요청이 검증 오류(422)다. 키는 비면 안 되고 값은 빈 문자열도 된다.
- 라벨에 비밀·개인 정보·긴 본문을 넣지 않는다. 라벨은 목록 응답에 그대로 나간다.

**흔한 실수**: 라벨로 실행 동작을 바꾸려 한다. 라벨은 묶기·거르기·표시용이다. 실행에 영향을 주는 값은 입력이나 설정으로
넘긴다.

**지운 뒤 남는 데이터**: 라벨을 다는 기능을 지워도 이미 단 라벨은 실행 기록에 남고 거르기에 쓸 수 있다. 표시 규칙이
없어지면 그 키의 칩 표시 규칙도 함께 사라진다.

<!-- extdocs:facts run-labels -->
- 등록: 계약 필드 `Run.labels`에 값을 넣는다(열린 값, 코드 등록 없음).
- 인터페이스:
  - `agent_console_contracts:Run` — 그래프 1회 실행. 하위 그래프는 자식 Run(parent_run_id).
- 기본 구현: —
- 예제:
  - snippet: —
- 끄기·제거: 값을 넣지 않으면 그 필드를 쓰는 기능만 비어 있다.
<!-- /extdocs:facts -->

## server-module

**언제 쓰나**: 자기 REST 경로, 자기 저장소(DB 표), 자기 설정 섹션이 있는 새 기능을 서버에 더할 때. 같은 종류를 하나 더
두는 일이면 모듈이 아니라 플러그인이다. 두 기능을 잇는 일이면 연동 모듈(`kind = "link"`)이다.

**최소 모양**: `descriptor`(`ModuleDescriptor`)와 `build(ctx) -> ModuleParts`를 가진 객체를 entry point
`agent_console.server_modules`에 등록한다. 이름이 모듈 id다. 필드·포트·설정·켜고 끄기·단독 실행은
[서버 모듈](modules.md)에 모두 있다.

**규칙**

- 다른 모듈을 import하지 않고 포트 이름으로만 잇는다. 필수 포트가 없으면 내 모듈만 `unsatisfied`로 꺼진다.
- 모듈 id·이슈 코드·이벤트 `type`·라벨 키·정의 종류 이름에 같은 접두사를 쓴다.
- 설치자 옵션 스키마의 필드마다 `title`·`description`·`x-ui`를 단다. 옵션이 틀리면 그 모듈만 `failed`다.
- `build`에서 오래 걸리는 일(파일 스캔·네트워크)을 하지 않는다. 시작 훅이나 백그라운드 작업으로 미룬다. 서버 준비 신호는
  모든 시작 훅이 끝난 뒤에 온다.

**흔한 실수**: 서버 앱 설정 키를 새로 만든다. 모듈 설정은 `modules.options.<모듈 id>` 아래에만 둔다. 키를 옮기면
`settings_compat`에 옛 키 안내를 둔다.

**지운 뒤 남는 데이터**: 경로는 404가 되고 웹 메뉴에서 빠진다. 표·파일·설정 섹션은 남는다(표까지 지우려면 제거 전에
계보를 내린다). 설정 파일에 `modules.options.<id>`가 남아 있어도 서버는 시작하고 경고만 남긴다. 그 모듈의 포트를 필수로
쓰던 연동은 `unsatisfied`가 된다.

<!-- extdocs:facts server-module -->
- 등록: entry point 그룹 `agent_console.server_modules`(상수 `agent_console_modkit:MODULES_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_modkit:Module` — 서버 모듈. entry point 그룹 ``MODULES_GROUP``으로 설치하거나 직접 넘긴다.
  - `agent_console_modkit:ModuleDescriptor` — 모듈이 스스로를 설명하는 데이터. 조립 순서·켜고 끄기·보고에 쓴다.
  - `agent_console_modkit:ModuleContext` — ``Module.build``가 받는 것(전역 없음). 조립기가 모듈마다 만든다.
  - `agent_console_modkit:SettingsCompat` — 모듈 하나의 호스트 설정 호환 선언.
- 기본 구현: `link-chat-runs (agent-console-link-chat-runs)`, `link-definitions-resources (agent-console-link-definitions-resources)`, `link-definitions-teams (agent-console-link-definitions-teams)`, `link-exports-teams (agent-console-link-exports-teams)`, `link-logs-architecture (agent-console-link-logs-architecture)`, `link-logs-runs (agent-console-link-logs-runs)`, `link-logs-trace (agent-console-link-logs-trace)`, `link-logs-usage (agent-console-link-logs-usage)`, `link-memory-runs (agent-console-link-memory-runs)`, `link-projects-memory (agent-console-link-projects-memory)`, `link-projects-records (agent-console-link-projects-records)`, `link-projects-runs (agent-console-link-projects-runs)`, `link-projects-sdd (agent-console-link-projects-sdd)`, `link-projects-wiki (agent-console-link-projects-wiki)`, `link-runs-sdd (agent-console-link-runs-sdd)`, `link-runs-teams (agent-console-link-runs-teams)`, `link-runs-trace (agent-console-link-runs-trace)`, `link-runs-usage (agent-console-link-runs-usage)`, `link-wiki-runs (agent-console-link-wiki-runs)`, `mod-architecture (agent-console-mod-architecture)`, `mod-chat (agent-console-mod-chat)`, `mod-definitions (agent-console-mod-definitions)`, `mod-exports (agent-console-mod-exports)`, `mod-imports (agent-console-mod-imports)`, `mod-logs (agent-console-mod-logs)`, `mod-memory (agent-console-mod-memory)`, `mod-projects (agent-console-mod-projects)`, `mod-resources (agent-console-mod-resources)`, `mod-runs (agent-console-mod-runs)`, `mod-sdd (agent-console-mod-sdd)`, `mod-usage (agent-console-mod-usage)`, `mod-versions (agent-console-mod-versions)`, `mod-wiki (agent-console-mod-wiki)`
- 예제:
  - package: [examples/extensions/agent-console-example-module](../../examples/extensions/agent-console-example-module/README.md)
  - contract-tests: `agent_console_modkit.testing:echo_module`, `agent_console_modkit.testing:fake_module`
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->
