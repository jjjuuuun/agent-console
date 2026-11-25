# 프로젝트

프로젝트는 로컬 폴더 하나와 그 안의 구성 사본 공간이다. 이 페이지의 지점은 세 갈래다.

- 폴더 고르기: 찾아보기 시작 위치·숨김 이름([folder-browse-defaults](#folder-browse-defaults)), 운영체제 선택 창([folder-dialog-provider](#folder-dialog-provider))
- 사본 공간: 어떤 정의 종류가 들어가나([portable-definition-kind](#portable-definition-kind)), 폴더 이름과 `.gitignore` 틀([project-space-layout](#project-space-layout)), 경로 지킴([path-field](#path-field))
- 정의 옮기기와 실행: 참조 추출·고치기([definition-references](#definition-references), [definition-reference-rewriter](#definition-reference-rewriter)), 실행 범위([run-scope](#run-scope)), 범위 설정 층([settings-scope-layer](#settings-scope-layer))

포트 지점은 서버 모듈이나 연동 모듈이 제공한다. 모양과 조립 규칙은 [서버 모듈](modules.md#포트)과 [연동 모듈](links.md#여러-제공자-포트에-항목-더하기)을 본다.

## definition-reference-rewriter

**언제 쓰나**: 공간 사이에 정의를 복사하면서 이름을 바꿀 때(예: 대상 공간에 같은 id가 이미 있어 `coder`를 `coder-2`로 복사), 복사 묶음 안의 다른 정의가 옛 id를 가리키지 않게 고친다. 새 정의 종류가 다른 정의를 id로 가리키면, 그 종류를 만든 모듈이 참조 추출([definition-references](#definition-references))과 짝으로 제공한다.

**최소 모양**: `rewrite(kind, document, renames) -> new_document` 함수 하나다. `renames`는 `(종류, 옛 id) → 새 id`다. 모르는 종류면 문서를 그대로 돌려준다. 모듈의 `build`에서 `ctx.provide(DEFINITIONS_REWRITERS, rewrite)`로 낸다.

```python
>>> from agent_console_projects import apply_renames
>>> def rewrite(kind, doc, renames):
...     if kind != "graph":
...         return doc
...     return {**doc, "uses": [renames.get(("agent", u), u) for u in doc.get("uses", [])]}
>>> docs = {("graph", "team"): {"id": "team", "uses": ["coder"]}, ("agent", "coder"): {"id": "coder"}}
>>> out = apply_renames(docs, {("agent", "coder"): "coder-2"}, rewrite_references=rewrite)
>>> sorted(out), out[("graph", "team")]["uses"]
([('agent', 'coder-2'), ('graph', 'team')], ['coder-2'])

```

**규칙**
- 입력 문서를 바꾸지 말고 새 문서를 돌려준다. 프로젝트 모듈은 받은 문서를 깊은 복사해 쓰지만, 같은 문서를 다른 제공자도 받는다.
- 제공자가 여럿이면 차례로 이어 적용한다. 각 제공자는 자기가 아는 종류·필드만 고치고 나머지는 그대로 둔다.
- 참조 추출과 같은 필드를 다룬다. 추출은 하는데 고치지 않으면, 이름을 바꿔 복사한 묶음이 옛 id를 가리켜 실행 전 검사에서 막힌다.

**흔한 실수**: `id` 필드까지 바꾸기(복사하는 쪽이 이미 바꾼다), 이름이 바뀌지 않은 참조를 지우기.

**끄기**: 제공자가 하나도 없으면 이름 바꾸기 복사는 참조를 고치지 않고 그대로 쓴다.

<!-- extdocs:facts definition-reference-rewriter -->
- 등록: 서버 모듈이 포트 `definitions.reference_rewriters`(기호 `agent_console_mod_projects.ports:DEFINITIONS_REWRITERS`, 다중 예)를 제공한다.
- 인터페이스:
  - `agent_console_projects:RewriteReferences` — 참조 고치기 `rewrite(kind, document, renames) -> new_document`(주입, `references`의 짝).
- 기본 구현: —
- 예제:
  - snippet: 참조 고치기 함수 하나를 포트로 제공
- 끄기·제거: 제공하는 모듈을 끄면(`modules.<id>.enabled: false`) 소비하는 쪽은 그 부분만 꺼진다.
<!-- /extdocs:facts -->

## definition-references

**언제 쓰나**: 정의를 프로젝트로 복사하거나 범위를 검사할 때, 이 정의가 쓰는 다른 정의를 함께 가져오게 한다. 팀 구성이 에이전트를, 에이전트가 리소스를 가리키는 것처럼 정의끼리 이어진 종류를 새로 만들었을 때 제공한다.

**최소 모양**: `references(kind, document) -> [(종류, id), ...]` 함수 하나다. 모르는 종류면 빈 목록을 돌려준다. 프로젝트 순수 규칙 `copy_plan`이 이 함수로 참조 닫힘(함께 가져올 항목)과 순환·빠진 참조 경고를 만든다. 서버에서는 포트로 낸다.

**규칙**
- 순수 함수여야 한다. 저장소를 읽지 않고 문서만 본다(복사 계획이 여러 번 부른다).
- 없는 정의를 가리켜도 그대로 돌려준다. 빠진 참조 경고는 계획이 낸다.
- 새 정의 종류를 정의 종류 기여로 등록할 때는 기여의 `references`에 같은 함수를 줄 수도 있다([정의 종류 기여](host.md#definition-kind-contribution)). 프로젝트 모듈은 둘을 합쳐 쓴다.

**흔한 실수**: 문서 안의 비어 있는 값(`""`, `None`)을 참조로 내기, 같은 참조를 여러 번 내기(해롭지는 않지만 계획 화면에 같은 항목이 겹쳐 보일 수 있다).

**끄기**: 제공자가 없으면 복사 계획은 고른 항목만 복사하고 정보 이슈 `project.references_unavailable`를 단다.

<!-- extdocs:facts definition-references -->
- 등록: 서버 모듈이 포트 `definitions.references`(기호 `agent_console_mod_projects.ports:DEFINITIONS_REFERENCES`, 다중 예)를 제공한다.
- 인터페이스:
  - `agent_console_mod_projects.ports:References` — ``definitions.references`` 모양: 문서 하나가 쓰는 정의의 ``(종류, id)``.
- 기본 구현: `link-definitions-teams`
- 예제:
  - reference: [packages/py/links/ac-link-definitions-teams](../../packages/py/links/ac-link-definitions-teams/README.md)
- 끄기·제거: 제공하는 모듈을 끄면(`modules.<id>.enabled: false`) 소비하는 쪽은 그 부분만 꺼진다.
<!-- /extdocs:facts -->

## folder-browse-defaults

**언제 쓰나**: 프로젝트를 등록할 때 쓰는 앱 안 폴더 찾아보기의 범위를 바꾼다. 서버 설치자는 시작 위치(이 밖으로는 나가지 않는다)를, 라이브러리를 직접 쓰는 사람은 숨김 이름과 경로 방식별 기본 시작 위치 규칙까지 바꾼다.

**최소 모양**: 서버는 설치자 설정 `modules.options.mod-projects.browse_roots`(절대 경로 목록)만 읽는다.

```yaml extdocs:validate=agent_console_mod_projects.settings:ProjectModuleSettings
browse_roots:
  - /srv/work
  - /srv/shared
```

라이브러리(`agent-console-local-folders`)를 바로 쓸 때는 기본 데이터와 같은 모양의 딕셔너리를 `load_browse_defaults`로 읽어 `check_folder`·`list_dirs`·`default_roots`의 `defaults=`로 넘긴다.

```python
>>> from agent_console_local_folders import MemoryFileSystem, list_dirs, load_browse_defaults
>>> defaults = load_browse_defaults({"hidden_names": ["node_modules"], "roots": {}})
>>> fs = MemoryFileSystem().add_dir("/srv/work/app").add_dir("/srv/work/node_modules")
>>> listing = list_dirs("/srv/work", fs=fs, defaults=defaults)
>>> [e.name for e in listing.entries], listing.hidden_count
(['app'], 1)

```

**규칙**
- 숨김 이름은 대소문자를 무시한다. 점으로 시작하는 이름과 OS 숨김 속성은 데이터와 상관없이 숨김이다(화면의 "숨김 보기"로 보인다).
- 시작 위치 규칙은 경로 방식(`posix`·`windows`)마다 `path` 틀(`~` = 홈, `each`가 있으면 `{item}`) 또는 `parent` + `name_pattern`이다. 있는 폴더만 시작 위치가 된다.
- `browse_roots`를 주면 찾아보기와 폴더 확인이 그 아래로 제한된다(밖이면 `folders.outside_roots`).

**흔한 실수**: 상대 경로를 `browse_roots`에 적기(절대 경로만 뜻이 있다), 숨김 이름에 경로를 적기(폴더 이름 하나만 비교한다).

**끄기**: `browse_roots`를 비우면 홈·드라이브 같은 기본 시작 위치로 돌아간다. 서버 설정으로는 숨김 이름을 바꿀 수 없고, 패키지 기본 숨김 이름은 빈 목록이다.

<!-- extdocs:facts folder-browse-defaults -->
- 등록: 패키지 데이터 `data/browse_defaults.json`를 설정(`mod-projects.browse_roots`)으로 덮어쓴다.
- 인터페이스:
  - `agent_console_local_folders:load_browse_defaults` — 탐색 기본값. `data`가 없으면 패키지 기본 데이터(`data/browse_defaults.json`).
- 기본 구현: —
- 예제:
  - snippet: 설치자 설정 mod-projects.browse_roots
- 끄기·제거: 설정(`mod-projects.browse_roots`)을 지우면 패키지 데이터 기본값으로 돌아간다.
<!-- /extdocs:facts -->

## folder-dialog-provider

**언제 쓰나**: [폴더 선택…] 버튼이 띄우는 서버 컴퓨터의 폴더 선택 창을 바꾸거나 더한다. 대부분은 명령 하나를 데이터로 더하면 된다. 명령줄로 띄울 수 없는 창(라이브러리 호출이 필요한 창)만 코드 제공자로 만든다.

**데이터로 더하기**: 설치자 설정 `modules.options.mod-projects.folder_dialog.providers`에 항목을 적는다. 같은 id는 기본 항목을 바꾸고 `enabled: false`면 뺀다. 새 id는 기본 항목보다 먼저 판정한다. 항목 형식(`platforms`·`requires`·`env_requires`·`argv`·`env`·`cancel_exit_codes`)은 [로컬 폴더 패키지 README](../../packages/py/features/ac-local-folders/README.md)에 있다.

```yaml extdocs:validate=agent_console_mod_projects.settings:ProjectModuleSettings
folder_dialog:
  mode: auto
  include_default_providers: true
  providers:
    - id: my-picker
      platforms: [linux]
      requires: my-picker
      argv: [my-picker, {when: initial, args: ["--start", "{initial}"]}]
      cancel_exit_codes: [1]
    - {id: kdialog, enabled: false}
```

**코드 제공자**: `id`, `available(environ) -> bool`, `pick(*, initial, title, timeout, cancel) -> str | None`을 갖춘 객체다. entry point 값은 그 객체나 인자 없이 불러 객체를 만드는 클래스다.

```python
>>> from agent_console_mod_projects import FolderDialogProvider
>>> class FixedPicker:
...     id = "fixed"
...     def available(self, environ):
...         return "DISPLAY" in environ
...     def pick(self, *, initial, title, timeout, cancel):
...         return None if cancel.is_set() else "/srv/work/app"
>>> isinstance(FixedPicker(), FolderDialogProvider)
True

```

```toml
[project.entry-points."agent_console.folder_dialogs"]
fixed = "my_package.picker:FixedPicker"
```

**규칙**
- 코드 제공자는 설치된 것이 모두 데이터 명령보다 먼저 판정된다. `available`이 참인 첫 제공자를 쓴다.
- 사용자 값(`initial`·`title`)을 스크립트 문자열 안에 끼우지 말고 별도 인자나 환경변수로 넘긴다. 데이터 명령은 셸 없이 실행된다.
- 고른 경로는 프로젝트 모듈이 다시 확인한다. 제공자는 경로를 돌려주기만 한다. 취소면 `None`, 실패는 예외다.
- 선택 창은 서버가 루프백 주소에 묶였을 때만 열린다. 한 번에 하나만 열린다.

**흔한 실수**: `available`에서 창을 띄우거나 명령을 실행하기(판정은 가벼워야 한다), `cancel`을 보지 않아 요청이 끊긴 뒤에도 창이 남기.

**끄기**: `folder_dialog.mode: off`면 앱 안 찾아보기만 쓴다. 코드 제공자는 패키지를 제거하면 빠진다. 쓸 창이 없으면 화면은 버튼을 숨기고 찾아보기만 보인다.

<!-- extdocs:facts folder-dialog-provider -->
- 등록: entry point 그룹 `agent_console.folder_dialogs`(상수 `agent_console_mod_projects:FOLDER_DIALOGS_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_mod_projects:FolderDialogProvider` — 코드 선택 창 제공자(entry point ``agent_console.folder_dialogs``).
- 설정: `mod-projects.folder_dialog.providers`, `mod-projects.folder_dialog.include_default_providers`
- 기본 구현: —
- 예제:
  - reference: [packages/py/features/ac-local-folders](../../packages/py/features/ac-local-folders/README.md) — 명령 표 데이터 data/folder_dialogs.json
  - snippet: 코드 제공자
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->

## path-field

**언제 쓰나**: 노드·백엔드·리소스 종류의 설정 스키마에 로컬 경로를 받는 속성이 있을 때, 그 속성에 `x-path` 주석을 단다. 프로젝트 실행에서 이 값이 프로젝트 폴더 밖을 가리키면 경로 지킴이 알린다. 경로 지킴은 필드 이름을 보지 않고 이 주석만 본다.

**최소 모양**: Pydantic 필드의 `json_schema_extra`에 `x_path()`(폴더) 또는 `x_path("file")`(파일)을 넣는다. 목록 필드에 달면 각 항목이 경로다.

```python
>>> from pydantic import BaseModel, Field
>>> from agent_console_contracts import x_path
>>> from agent_console_projects import outside_paths
>>> class ToolOptions(BaseModel):
...     cwd: str = Field(default=".", json_schema_extra=x_path())
...     extra_files: list[str] = Field(default_factory=list, json_schema_extra=x_path("file"))
>>> schema = ToolOptions.model_json_schema()
>>> schema["properties"]["cwd"]["x-path"], schema["properties"]["extra_files"]["x-path"]
('directory', 'file')
>>> value = {"cwd": "../other", "extra_files": ["notes.md"]}
>>> [p.resolved for p in outside_paths(value, schema, "/srv/work/app", flavor="posix")]
['/srv/work/other']

```

**규칙**
- 값은 `directory`·`file` 둘뿐이다. 다른 값이면 `x_path`가 `ValueError`를 낸다.
- 상대 경로는 프로젝트 폴더 기준으로 푼다. 다른 확장 키와 함께 쓰려면 `{**x_ui(...), **x_path()}`처럼 합친다.

**흔한 실수**: 경로를 받는 필드에 주석을 빠뜨리기(그 값은 검사 없이 지나간다), URL이나 경로가 아닌 식별자에 주석 달기.

**끄기**: 주석을 지우면 그 필드는 경로 검사를 받지 않는다.

<!-- extdocs:facts path-field -->
- 등록: 스키마 주석 키 `x-path`를 단다.
- 인터페이스:
  - `agent_console_contracts:x_path` — Pydantic `Field(json_schema_extra=...)`에 넣을 `{"x-path": kind}`를 만든다.
- 기본 구현: —
- 예제:
  - snippet: 스키마 속성에 x-path 주석 달기
- 끄기·제거: 주석을 지우면 기본 동작으로 돌아간다.
<!-- /extdocs:facts -->

## portable-definition-kind

**언제 쓰나**: 새 정의 종류를 등록할 때, 그 종류가 프로젝트 폴더의 사본 공간에 들어갈 수 있는지(`portable`)와 앱 라이브러리에 둘 수 있는지(`library`)를 정한다. 예를 들어 프로젝트마다 따로인 문서는 `library=False`, 앱 등록부 같은 것은 `portable=False`다.

**최소 모양**: `DefinitionKind`의 두 필드다. 종류를 서버에 더하는 방법은 [정의 종류 기여](host.md#definition-kind-contribution)를 본다.

```python
>>> from agent_console_store import DefinitionKind
>>> notes = DefinitionKind(name="note", directory="notes", portable=True, library=False)
>>> notes.is_portable, notes.library
(True, False)
>>> DefinitionKind(name="app-settings", singleton_file="app.yaml").is_portable
False

```

**규칙**
- 싱글턴 종류(`singleton_file`)는 `portable` 값과 상관없이 옮길 수 없다.
- `library=False` 종류는 라이브러리 저장소에서 모르는 종류로 보인다(요청하면 없음). 프로젝트·단독 공간에만 둔다.
- 옮길 수 없는 종류를 복사 계획에 넣으면 그 항목만 빠지고 경고가 붙는다.

**흔한 실수**: 다른 정의를 가리키는 종류를 `portable`로 두고 참조 추출을 제공하지 않기(복사한 공간에서 참조가 끊긴다).

**끄기**: 필드를 생략하면 `portable=True`, `library=True`다.

<!-- extdocs:facts portable-definition-kind -->
- 등록: 서술자 필드 `DefinitionKind.portable`에 값을 넣는다.
- 인터페이스:
  - `agent_console_store:DefinitionKind` — 정의 종류 하나의 저장 규칙.
- 기본 구현: —
- 예제:
  - snippet: DefinitionKind(portable=..., library=...)
- 끄기·제거: 필드를 비우면 기본값을 쓴다.
<!-- /extdocs:facts -->

## project-space-layout

**언제 쓰나**: 프로젝트 폴더 안에 앱이 만드는 구성 폴더의 이름이나, 등록할 때 함께 만드는 `.gitignore`의 기본 줄을 바꾼다. 같은 폴더를 다른 이름의 구성 폴더로 쓰는 앱과 나눠 쓰거나, 사내 규칙에 맞는 무시 목록이 필요할 때다.

**최소 모양**: 서버에서는 설치자 설정 `modules.options.mod-projects.config_dir` 하나다.

```yaml extdocs:validate=agent_console_mod_projects.settings:ProjectModuleSettings
config_dir: .team-console
records_file: records.sqlite3
```

라이브러리(`agent-console-project-space`)를 바로 쓸 때는 `open_space(folder, config_dir=...)`와 `init_space(..., gitignore_template=...)`로 바꾼다. 기본 틀은 패키지 데이터다.

```python
>>> from agent_console_project_space import default_gitignore_template
>>> [line for line in default_gitignore_template().splitlines() if line.startswith("/")][:2]
['/.state/', '/memory.sqlite3']

```

**규칙**
- 틀에서 앱이 관리하는 줄은 `/`로 시작하는 줄이다. 구성 폴더 바로 아래만 가리켜 정의 이름과 겹치지 않게 한다.
- 틀에는 이름 자리 `{state_dir}`·`{memory_file}`·`{records_file}`·`{sessions_dir}`가 있다. 등록·빠진 줄 점검·[덧붙이기]는 그 공간의 배치 값(설정 `records_file`·`sessions_dir`)으로 채워 쓰므로, 이름을 바꾸면 git 제외 줄도 따라간다. 직접 준 틀에도 같은 자리를 쓸 수 있다(`render_gitignore_template`).
- 등록할 때 `project.yaml`과 `.gitignore`는 없을 때만 만든다. 있으면 고치지 않고, 틀에서 빠진 줄은 `project.gitignore_outdated` 정보로 알린다. 사용자가 [덧붙이기]를 누를 때만 끝에 더한다.
- 구성 폴더 이름은 폴더 밖으로 나가지 않는 상대 이름이어야 한다(`..`·절대 경로·역슬래시 거부).

**흔한 실수**: 이미 등록한 프로젝트가 있는데 `config_dir`를 바꾸기. 옛 구성 폴더를 읽지 않으므로 그 프로젝트의 정의·기록이 안 보인다(지워지지는 않는다).

**끄기**: 설정을 지우면 기본 이름으로 돌아간다.

<!-- extdocs:facts project-space-layout -->
- 등록: 패키지 데이터 `data/gitignore.template`를 설정(`mod-projects.config_dir`)으로 덮어쓴다.
- 인터페이스:
  - `agent_console_project_space:default_gitignore_template` — 패키지에 들어 있는 `.gitignore` 기본 틀 텍스트(UTF-8, 마지막 줄바꿈 포함).
- 기본 구현: —
- 예제:
  - snippet: 설치자 설정 mod-projects.config_dir
- 끄기·제거: 설정(`mod-projects.config_dir`)을 지우면 패키지 데이터 기본값으로 돌아간다.
<!-- /extdocs:facts -->

## run-scope

**언제 쓰나**: 실행이 시작될 때마다 그 Run에만 노드 서비스·경고·정의 출처를 더한다. 예: 프로젝트 실행이면 그 프로젝트 공간의 정의와 기록을 쓰게 하기, 메모리·위키가 켜져 있으면 에이전트 도구 공급자를 넣기. 두 기능을 잇는 연동 모듈이 주로 제공한다.

**최소 모양**: `scope_run(graph, services, *, project_id) -> RunScope | None`을 가진 객체다. 정의 출처까지 정하려면 선택 메서드 `run_definitions(project_id, graph_id)`를 더한다. 전체 예는 [연동 예제](../../examples/extensions/agent-console-example-link/README.md)에 있다.

```python
from agent_console_mod_runs.ports import RunScope
from agent_console_nodes_core import TOOL_PROVIDERS


class NotesScope:
    def scope_run(self, graph, services, *, project_id):
        if not uses_notes(graph):          # 옵트인: 해당 없는 실행은 그대로 둔다
            return None
        existing = services.get(TOOL_PROVIDERS) or ()
        return RunScope(services={TOOL_PROVIDERS: (*existing, NotesTools())})
```

**규칙**
- 실행 시작(일반 실행·이어 가기·대화 턴)마다 검사·준비보다 먼저 부른다. 자식 Run은 부르지 않고 부모 서비스를 물려받는다.
- 여러 제공자가 같은 서비스 키를 주면 뒤 제공자가 이긴다. 목록 서비스(도구 공급자 등)는 받은 목록에 더해서 돌려준다.
- `warnings`는 실행을 막지 않고 `log.warning`으로 남는다. 실행을 막으려면 `errors`를 준다(Run이 만들어지지 않는다).
- 예외를 던지면 그 제공자만 건너뛰고 실행은 범위 없이 계속한다.

**흔한 실수**: 모든 실행에 서비스를 넣기(사용자가 켜지 않은 동작이 생긴다), 다른 프로젝트 공간으로 대신 열기(열 수 없으면 오류로 알린다).

**끄기**: 제공하는 연동 모듈을 끄면 그 범위만 빠진다.

<!-- extdocs:facts run-scope -->
- 등록: 서버 모듈이 포트 `runs.scopes`(기호 `agent_console_mod_runs.ports:RUN_SCOPES`, 다중 예)를 제공한다.
- 인터페이스:
  - `agent_console_mod_runs.ports:RunScoper` — ``runs.scopes`` 항목: 실행 범위.
  - `agent_console_mod_runs.ports:RunScopeLike` — ``RunScoper.scope_run`` 결과 모양(``RunScope``가 만족).
  - `agent_console_mod_runs.ports:RunDefinitionsScoper` — ``runs.scopes`` 항목의 **선택** 메서드: Run의 정의 조회 출처.
  - `agent_console_mod_runs.ports:RunChildScoper` — ``runs.scopes`` 항목의 **선택** 메서드: 자식 Run(중첩 팀) 점검.
  - `agent_console_mod_runs.ports:RunProjectScoper` — ``runs.scopes`` 항목의 **선택** 메서드: 프로젝트 범위를 맡는가.
- 기본 구현: `link-memory-runs`, `link-projects-runs`, `link-wiki-runs`
- 예제:
  - package: [examples/extensions/agent-console-example-link](../../examples/extensions/agent-console-example-link/README.md)
  - reference: [packages/py/links/ac-link-projects-runs](../../packages/py/links/ac-link-projects-runs/README.md)
- 끄기·제거: 제공하는 모듈을 끄면(`modules.<id>.enabled: false`) 소비하는 쪽은 그 부분만 꺼진다.
<!-- /extdocs:facts -->

## settings-scope-layer

**언제 쓰나**: 범위 id(예: 프로젝트 id)마다 유효 설정에 끼울 설정 층을 준다. 유효 설정을 `?project=<id>`로 물으면 공통 설정 바로 아래에 이 층이 들어간다. 프로젝트 폴더의 매니페스트에 적은 설정을 실행과 화면에 반영하는 연동이 기본 구현이다.

**최소 모양**: `scope_layers(scope_id) -> 결과`를 가진 객체다. 결과는 `layers`(층 목록)와 `warnings`(이슈 목록) 두 속성을 가진다. 모르는 범위 id면 빈 층을 돌려준다. 참조 구현은 [프로젝트·실행 연동](../../packages/py/links/ac-link-projects-runs/README.md)이다.

**규칙**
- 이 포트를 쓰는 쪽은 범위의 뜻을 모른다. id 해석은 제공자가 한다.
- 층을 읽지 못하면 예외 대신 경고와 빈 층을 돌려준다. 유효 설정은 공통 설정으로 계속 계산된다.
- 여러 제공자의 층은 제공자 순서로 쌓인다.

**흔한 실수**: 층에 비밀 값을 그대로 싣기(유효 설정은 화면에 보인다, 비밀은 `secret://` 참조로).

**끄기**: 제공자가 없으면 `?project=`를 무시하고 공통 설정만 쓴다.

<!-- extdocs:facts settings-scope-layer -->
- 등록: 서버 모듈이 포트 `settings.scope_layers`(기호 `agent_console_link_definitions_teams.ports:SCOPE_LAYERS`, 다중 예)를 제공한다.
- 인터페이스:
  - `agent_console_link_definitions_teams.ports:ScopeLayersSource` — ``settings.scope_layers`` 모양: 범위 id → 설정 층(이 연동은 범위의 뜻을 모른다).
- 기본 구현: `link-projects-runs`
- 예제:
  - reference: [packages/py/links/ac-link-projects-runs](../../packages/py/links/ac-link-projects-runs/README.md)
- 끄기·제거: 제공하는 모듈을 끄면(`modules.<id>.enabled: false`) 소비하는 쪽은 그 부분만 꺼진다.
<!-- /extdocs:facts -->
