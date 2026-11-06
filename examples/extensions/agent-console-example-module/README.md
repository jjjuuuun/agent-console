# agent-console-example-module

**새 기능 하나를 서버 모듈로 더하는** 예제이자 작성 가이드다. 서버·웹·다른 모듈 코드를 고치지 않는다. 설치하고
서버를 재시작하면 기능이 켜지고, 끄면(`modules.disabled`) 그 경로만 404가 되고 나머지는 그대로 동작한다.

모듈 `mod-example-notes`는 짧은 노트를 적고 읽는다. 작지만 서버 모듈이 갖출 수 있는 것을 모두 보인다.

| 무엇 | 이 예제에서 | 파일 |
| --- | --- | --- |
| 서술자 | id·제목·설명, 제공·선택 포트, 설정 스키마, 설정 호환 선언, 계보, 웹 역할 | `module.py` |
| REST | `GET·POST /api/v1/example-notes`, `GET /api/v1/example-notes/{id}` (경로는 설치자 옵션) | `routes.py` |
| 설치자 옵션 | `modules.options.mod-example-notes` — 제목·설명·`x-ui`(설정 화면이 읽기 전용 표로 보인다) | `settings.py` |
| 명령행 옵션 | `--example-notes-max N` → `max_notes` (`agent-console serve --help`에 보인다) | `settings.py` |
| 사용자 설정 섹션 | 워크스페이스 `settings.yaml`의 `example_notes` — 재시작 없이 다음 요청부터 반영 | `settings.py` |
| 정의 종류 기여 | 노트 틀(`example-note-template`) — 정의 모듈이 라이브러리 저장소에 등록 | `module.py` |
| 마이그레이션 계보 | `example_notes`, `scopes=("app", "project")` — 앱 DB와 프로젝트 기록 DB에 같은 표 | `storage.py`, `migrations/` |
| 포트 제공 | `example_notes.reader` — 다른 모듈(연동)이 노트를 읽는다 | `ports.py` |
| 선택 포트 | `workspace.settings`·`definitions.lookup`·`records.spaces` — 없으면 그 동작만 409 | `ports.py` |
| 단독 실행 | `python -m agent_console_example_module` (같은 호스트 코드·보안 규칙) | `standalone.py` |

의존: 계약(`agent-console-contracts`)·모듈 키트(`agent-console-modkit[host]`)·저장(`agent-console-store`)·
`fastapi`·`pydantic`·`sqlalchemy`. 다른 기능 모듈은 import하지 않는다(포트 이름으로만 잇는다). 이 패키지는
uv workspace 멤버가 아니다. 설치하지 않으면 아무 동작도 바꾸지 않는다.

## 모듈 만드는 법

모듈은 `descriptor`(데이터)와 `build(ctx) -> ModuleParts`(조립) 두 가지다.

```python
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts, PortKey

NOTES_READER: PortKey[object] = PortKey("example_notes.reader", "노트 읽기")
RECORDS_SPACES: PortKey[object] = PortKey("records.spaces", "프로젝트 기록 DB")  # 선택


class NotesModule:
    descriptor = ModuleDescriptor(
        id="mod-example-notes",
        version="0.1.0",
        kind="feature",
        title="노트(예제)",
        description="짧은 노트를 적고 읽는다",          # 앱 사용자가 읽는 문장
        provides=(NOTES_READER,),
        optional=(RECORDS_SPACES,),                     # 없으면 그 동작만 409
        settings_schema=NotesModuleSettings,            # modules.options.<id> 검증
        settings_compat=SETTINGS_COMPAT,                # 명령행 옵션
        migrations=(BRANCH,),                           # 켜질 때만 호스트가 올린다
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        options = ctx.settings or NotesModuleSettings()
        service = NotesService(options, NotesDeps(app_engine=lambda: ctx.database.engine, ...))
        ctx.provide(NOTES_READER, service)
        return ModuleParts(routers=[build_router(service, options.route)],
                           error_map={NoteNotFoundError: "not_found"})
```

규칙
1. **전역 상태 없음**: 서비스·저장소는 `build` 안에서 만들고 바깥 의존(DB·시계·다른 모듈)은 `ctx`에서 받는다.
   같은 모듈 객체로 여러 앱을 조립해도 섞이지 않는다.
2. **다른 모듈은 포트 이름으로만**: 다른 모듈 패키지를 import하지 않는다. 같은 이름의 `PortKey`를 자기
   `ports.py`에 선언한다. 필수 포트(`requires`)가 없으면 모듈 전체가 `unsatisfied`, 선택 포트(`optional`)가 없으면
   그 동작에서만 `raise ctx.unavailable(PORT)`(또는 `FeatureUnavailableError`) → 409 `feature_unavailable`.
3. **계약을 고치지 않는다**: 자기 API 모양은 자기 패키지(`models.py`)에, 오류는 계약의 알려진 코드
   (`not_found`·`validation_failed`)로, 자기 이슈 코드는 자기 접두(`example_notes.`)로 쓴다.
4. **보안 코드를 두지 않는다**: 토큰·Host·Origin 검사와 요청 크기 제한은 호스트가 한다.
5. **값은 설정·데이터로**: 경로·종류 이름·한도는 설치자 옵션, 보는 방식은 사용자 설정 섹션, 기본값은 패키지
   데이터(`data/defaults.json`)에 둔다. 설치자 옵션 필드마다 `title`·`description`·`x-ui`(`tier`·`when`)를 단다
   (설정 화면 도움말 린트가 검사한다).
6. **표는 계보로**: 표 모양은 리비전 파일(`migrations/versions/`)이 정한다. `scopes`에 `"project"`를 넣으면
   프로젝트 기록 DB를 여는 연동이 같은 계보를 그 파일에도 올린다(코드에 계보 이름 목록이 없다).

서버 없이 조립해 쓰기(테스트 호스트 = 모듈 키트의 `assemble`):

```python
>>> from agent_console_modkit import ModulesConfig, assemble
>>> from agent_console_example_module import NOTES_READER, NoteCreate, module
>>> assembly = assemble([module], ModulesConfig(options={"mod-example-notes": {"max_notes": 2}}))
>>> [(r.id, r.state.value) for r in assembly.report]
[('mod-example-notes', 'active')]
>>> notes = assembly.port(NOTES_READER)
>>> for text in ("하나", "둘", "셋"):
...     _ = notes.add(NoteCreate(text=text))
>>> [n.text for n in notes.list_notes()]
['셋', '둘']
>>> notes.list_notes("p1")
Traceback (most recent call last):
  ...
agent_console_modkit._errors.FeatureUnavailableError: 프로젝트 기록 연동이 꺼져 있어 프로젝트 노트를 쓸 수 없습니다

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

DB가 없는 호스트에서는 앱 노트를 메모리 SQLite에 둔다(같은 계보를 올린다, 서버 경고 `example_notes.storage_memory`).

## 등록과 설정

`pyproject.toml`의 entry point 하나. 그룹 = `agent_console_modkit.MODULES_GROUP`(`agent_console.server_modules`),
이름 = 모듈 id.

```toml
[project.entry-points."agent_console.server_modules"]
mod-example-notes = "agent_console_example_module.module:module"
```

서버 설정 파일(`agent-console.yaml`)의 설치자 옵션. 생략하면 패키지 데이터 기본값이다.

```yaml
modules:
  options:
    mod-example-notes:
      route: /example-notes                  # REST 경로(API 접두 뒤)
      template_kind: example-note-template   # 기여하는 정의 종류 이름
      template_dir: example-note-templates   # 워크스페이스 안 노트 틀 폴더
      user_section: example_notes            # 사용자 설정 섹션 이름
      records_space_prefix: "project:"       # 프로젝트 기록 공간 이름 접두
      max_notes: 200                         # 공간마다 남길 노트 수(넘으면 오래된 것부터 지움)
      max_text_chars: 4000                   # 노트 하나 최대 글자 수
  # disabled: [mod-example-notes]            # 끄기 — 경로 404, 다른 모듈은 그대로
```

명령행: `agent-console serve --example-notes-max 50`(설정 파일보다 우선). `--disable-module mod-example-notes`로 끈다.

사용자 설정(워크스페이스 `settings.yaml`, 앱 사용자가 고친다):

```yaml
example_notes:
  newest_first: true   # false = 적은 순서
  list_limit: 50       # 목록 한 번에 보일 수
```

틀린 값은 기본값으로 바꿔 쓰고 `GET /api/v1/server-info`의 경고(`example_notes.settings_invalid`)로 알린다.

노트 틀(정의 종류 기여): 워크스페이스 `example-note-templates/<id>.yaml`.

```yaml
kind: example-note-template
id: standup
name: 아침 회의
category: 회의
text: "어제 한 일 / 오늘 할 일 / 막힌 것"
tags: [회의]
```

`POST /api/v1/example-notes {"template": "standup"}`은 틀의 본문·태그로 노트를 만든다. 정의 모듈이 꺼져 있으면
이 요청만 409다. `?project=<프로젝트 id>`를 붙이면 그 프로젝트 폴더의 기록 DB에 쓰고 읽는다(프로젝트 기록 연동이
꺼져 있으면 409 — 앱 DB에 대신 쓰지 않는다).

## 설치·제거

저장소 루트에서 실행한다. 서버와 같은 Python 환경에 설치한다. 서버를 다른 가상환경에서 돌리면
`--python <그 가상환경 경로>`를 붙인다(예: `UV_PROJECT_ENVIRONMENT`로 정했다면 `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
uv pip install -e examples/extensions/agent-console-example-module   # 설치
uv pip uninstall agent-console-example-module                        # 제거
```

entry point는 서버 시작 때 읽으므로 설치·제거 뒤 **서버를 재시작**한다.
- 설치: `GET /api/v1/modules`에 `mod-example-notes`(`active`), `agent-console serve --help`에 `--example-notes-max`.
- 끄기(설치한 채): 설정 `modules.disabled` 또는 `--disable-module` — 경로 404, 계보를 올리지 않는다.
- 제거: 모듈·경로가 사라진다. **데이터는 남는다** — 앱 DB와 프로젝트 기록 DB의 `example_notes` 표, 워크스페이스의
  노트 틀 파일, 설정 섹션. 표까지 지우려면 제거 전에 계보를 내린다(`SqliteDatabase.downgrade_branch(BRANCH)`).
  설정 파일에 `modules.options.mod-example-notes`가 남아 있어도 서버는 시작한다(모르는 모듈의 옵션은 경고).

단독 실행(통합 서버 없이, 개발·재사용):

```bash
python -m agent_console_example_module --config standalone.yaml --port 0          # 띄우기
python -m agent_console_example_module --config standalone.yaml --port 0 --check  # /health 200 확인 후 종료
```

`standalone.yaml`은 호스트 설정(`workspace`·`state`·`security`·`modules`)이다. 앱 노트는 `<state>/example-notes.sqlite3`,
사용자 설정은 `<workspace>/settings.yaml`. 정의·프로젝트 기능이 없으므로 노트 틀·프로젝트 노트는 409다.

주의: `uv sync`는 lock에 없는 패키지를 지운다. 예제를 설치한 채 동기화하려면 `uv sync --all-packages --inexact`.

## 테스트

설치 없이 실행한다(pytest 설정 `pythonpath = ["src"]`). 루트 `uv run poe examples`가 이 폴더 설정으로 mypy·pytest를
돌린다. 저장소 밖에서는 이 폴더만 복사해 `uv sync --find-links <wheelhouse>`(저장소에서 `uv run poe wheels`) 뒤
`uv run pytest`.

```bash
cd examples/extensions/agent-console-example-module
uv run --project ../../.. python -m pytest
```

- `tests/test_service.py`: 서비스(적기·순서·보관 수·길이·빈 본문), 사용자 설정 섹션(순서·수, 틀린 값 → 기본값 +
  경고, 섹션 이름은 설치자 옵션), 노트 틀(포트 없음 → 409, 본문·태그 채움, 없는 틀), 프로젝트 노트(포트 없음 →
  409, 기록 DB가 없으면 빈 목록, 앱과 분리), 계보 올리기·내리기·다시 올리기, 리비전과 표 정의 일치, 설정 스키마
  도움말(설명·`x-ui`).
- `tests/test_module.py`: 모듈 혼자 조립(REST·404·422·409·토큰 없음 401, 켜질 때 계보 올림, 종류 기여·포트),
  DB 없음 → 메모리 + 경고, 경로 옵션, 끄면 404·계보 안 올림·나머지 정상, 틀린 옵션은 이 모듈만 실패,
  단독 실행 `main`(로컬 설정 모듈·SQLite 파일), `python -m … --check`(실제 소켓, `/health` 200).
- `tests/test_server.py`: 통합 서버(기본 모듈 전부) + 이 모듈 — `--example-notes-max`가 옵션 보기에 반영, 정의
  모듈이 기여 종류를 등록해 노트 틀 사용, 사용자 설정 섹션, 프로젝트 등록 → 프로젝트 기록 DB에 `example_notes`
  표·노트, 끄면 404·다른 경로 정상, `serve --help`에 옵션.

자기 모듈을 만들 때도 같은 방식으로 테스트한다: 단위는 서비스에 `NotesDeps` 같은 함수 묶음을 주고, 조립은
`agent_console_modkit.assemble` + `agent_console_modkit.host.create_host_app`, 통합은
`agent_console_server.create_app(modules=[*installed_modules(), module])`.
