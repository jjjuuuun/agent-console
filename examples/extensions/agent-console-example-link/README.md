# agent-console-example-link

**두 기능을 잇는 연동 모듈(link)** 예제이자 작성 가이드다. 노트 모듈(`mod-example-notes`, 예제
`agent-console-example-module`)과 실행 모듈(`mod-runs`)을 이어, 실행 중인 에이전트가 노트를 읽게 한다. 서버·웹·두
기능 모듈의 코드를 고치지 않는다.

| 무엇 | 이 예제에서 | 파일 |
| --- | --- | --- |
| 연동 서술자 | `kind="link"`, 필수 포트 둘(`example_notes.reader`·`runs.reader`), 제공 포트 `runs.scopes` | `module.py` |
| 실행 범위(`run-scope`) | `runs.scopes` 항목 — Run마다 노드 서비스 `TOOL_PROVIDERS`에 공급자 하나를 더한다 | `scope.py` |
| 도구 공급자(`agent-tool-provider`) | 노트 칸이 있는 에이전트에게 도구 `read_notes` + 지침, 호출마다 이벤트 `example_notes.read` | `provider.py` |
| 리소스 종류 | `example-notes`(칸 `example_notes`) — 붙인 에이전트만 도구를 받는다 | `resource_type.py`, `data/resource_type.json` |
| 설치자 옵션 | `modules.options.link-example-notes-runs` — 한 번에 읽는 수 상한·도구 이름 | `settings.py` |
| 문구·기본값 | 도구 이름·설명·결과 줄 틀·지침·이벤트 type | `data/defaults.json` |
| 테스트 대역 | 노트 모듈 없이 `example_notes.reader`를 주는 작은 모듈 | `testing.py` |

의존: 계약·모듈 키트·노드 종류(`agent-console-nodes-core`, 도구 공급자 프로토콜)·리소스·런타임·`pydantic`. **두 기능 모듈
패키지는 import하지 않는다** — 포트 이름과 쓰는 부분의 모양만 자기 `ports.py`에 다시 선언한다. 이 패키지는 uv
workspace 멤버가 아니다.

## 연동 만드는 법

연동은 서버 모듈과 같은 모양(`descriptor` + `build`)이고, 서술자 `kind="link"`와 **필수 포트**가 다르다. 필수 포트가
하나라도 없으면 이 연동만 `unsatisfied`로 꺼지고 서버와 다른 모듈은 그대로 시작한다.

```python
class NotesRunsLink:
    descriptor = ModuleDescriptor(
        id="link-example-notes-runs", version="0.1.0", kind="link",
        title="노트·실행 연동(예제)",
        provides=(RUN_SCOPES,),                    # runs.scopes(여러 제공자)
        requires=(NOTES_READER, RUNS_READER),      # 둘 중 하나라도 없으면 unsatisfied
        settings_schema=NotesRunsSettings,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings if isinstance(ctx.settings, NotesRunsSettings) else NotesRunsSettings()
        ctx.provide(RUN_SCOPES, NotesRunScope(lambda: ctx.port(NOTES_READER), slot=..., text=cfg.text(), ...))
        return ModuleParts()
```

실행 범위 항목은 `scope_run(graph, services, *, project_id) -> 결과 | None` 하나다. 결과의 `services`가 그 Run의 노드
서비스에 더해진다. 여기서는 이미 있는 공급자 목록 뒤에 자기 공급자를 붙인다(덮어쓰지 않는다).

```python
def scope_run(self, graph, services, *, project_id):
    provider = NotesToolProvider(
        self._reader, slot=self.slot, text=self.text, id=..., project_id=project_id
    )
    existing = services.get(TOOL_PROVIDERS) or ()
    return RunScopeResult(services={TOOL_PROVIDERS: (*existing, provider)})
```

도구 공급자는 `id`와 `provide(ctx) -> ToolProvision` 하나다. agent 노드가 노드마다 부른다.

규칙
1. **opt-in**: 묶음에 자기 칸(리소스 종류의 `contributes`)이 없으면 빈 `ToolProvision()`. 리소스를 붙이지 않은 에이전트는
   도구도 지침도 받지 않는다.
2. **칸 소비**: 처리한 칸은 `consumed_slots`에 넣는다. 그래야 백엔드로 넘어가 "적용하지 못한 칸" 경고가 나지 않는다.
   받을 포트가 없으면 칸을 소비하지 않는다(그 경고가 사용자에게 알린다).
3. **실행 공간만**: 프로젝트 Run이면 그 프로젝트 공간만 읽는다. 열 수 없으면 도구 결과를 오류로 돌리고 다른 공간으로
   대신하지 않는다. 실행은 계속된다.
4. **이벤트는 자기 접두로, 본문 없이**: 호출마다 `example_notes.read`(`status`·`count`·`tool_use_id`)만 낸다. 노트 본문·
   예외 메시지는 싣지 않는다.
5. **문구는 데이터**: 도구 이름·설명·지침은 `data/defaults.json`, 바꿀 값은 설치자 옵션.

서버 없이 조립해 쓰기(테스트 호스트 + 노트 대역):

```python
>>> from agent_console_modkit import ModulesConfig, assemble
>>> from agent_console_example_link import MODULE_ID, RUN_SCOPES, module
>>> from agent_console_example_link.testing import StaticNote, StaticNotesModule, StaticNotesReader
>>> notes = StaticNotesModule(StaticNotesReader({None: [StaticNote("n1", "배포는 금요일")]}))
>>> assembly = assemble([notes, module], ModulesConfig())
>>> assembly.status(MODULE_ID).state.value, assembly.status(MODULE_ID).missing
('unsatisfied', ('runs.reader',))
>>> assembly = assemble([module], ModulesConfig())  # 노트 모듈도 없으면 둘 다 빠졌다고 알린다
>>> sorted(assembly.status(MODULE_ID).missing)
['example_notes.reader', 'runs.reader']
>>> assembly.ports(RUN_SCOPES)
[]

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

실행 모듈까지 넣은 조립은 `tests/test_assembly.py`, 공급자를 엔진에 직접 넣는 방법은 `tests/test_engine.py`에 있다.

## 등록과 설정

`pyproject.toml`의 entry point 둘. 연동 모듈(그룹 `agent_console.server_modules`, 이름 = 모듈 id)과 리소스 종류(그룹
`agent_console.resource_types`, 이름 = 디스크립터 id).

```toml
[project.entry-points."agent_console.server_modules"]
link-example-notes-runs = "agent_console_example_link.module:module"

[project.entry-points."agent_console.resource_types"]
example-notes = "agent_console_example_link.resource_type:NotesResourceType"
```

설치자 옵션(서버 설정 파일, 생략하면 패키지 데이터 기본값):

```yaml
modules:
  options:
    link-example-notes-runs:
      max_notes_per_call: 20   # 한 번에 줄 노트 수 상한(비우면 노트 모듈 한도)
      tool_name: read_notes    # 에이전트에게 보이는 도구 이름(비우면 기본 이름)
  # disabled: [link-example-notes-runs]   # 이 연동만 끄기
```

에이전트에게 주려면 워크스페이스에 리소스를 만들고 에이전트(또는 팀·노드)에 붙인다. 설정은 모두 선택이다.

```yaml
# resources/team-notes.yaml
id: team-notes
type: example-notes
name: 팀 노트
config:
  limit: 10     # 도구 입력에 개수가 없을 때
  tag: 회의      # 이 태그가 붙은 노트만
```

여러 층(공통·팀·에이전트·노드)에 붙이면 키마다 가까운 층 값을 쓴다.

## 설치·제거

노트 모듈 예제를 함께 설치한다(없으면 이 연동은 `unsatisfied`). WSL(`/mnt/c`)에서는 환경변수를 붙인다.

```bash
export UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=$HOME/.cache/agent-console-wsl-venv   # WSL만
uv pip install --python "$UV_PROJECT_ENVIRONMENT" -e examples/extensions/agent-console-example-module \
                                                  -e examples/extensions/agent-console-example-link   # 설치
uv pip uninstall --python "$UV_PROJECT_ENVIRONMENT" agent-console-example-link                         # 제거
```

entry point는 서버 시작 때 읽으므로 설치·제거 뒤 **서버를 재시작**한다.
- 설치: `GET /api/v1/modules`에 `link-example-notes-runs`(`active`), `GET /api/v1/resource-types`에 `example-notes`.
- 노트 모듈이나 실행 모듈이 없거나 꺼짐: 서버는 시작하고 이 연동만 `unsatisfied`(`missing`에 빠진 포트). 노트 리소스를
  붙인 에이전트의 실행은 정상으로 끝나고 "적용하지 못한 칸" 경고가 한 번 난다.
- 제거: 연동과 리소스 종류가 사라진다. **남는 것** — 워크스페이스의 `example-notes` 리소스 파일(모르는 종류로 경고),
  지난 실행의 `example_notes.read` 이벤트, 설정 `modules.options.link-example-notes-runs`(서버는 시작하고 경고).

설치하지 않고 리소스 종류만 쓰려면 설정 `plugins.modules`에 `agent_console_example_link.resource_type:register`를 넣는다.

## 테스트

설치 없이 실행한다(pytest 설정 `pythonpath = ["src", "tests", "../agent-console-example-module/src"]`). 루트
`uv run poe examples`가 이 폴더 설정으로 mypy·pytest를 돌린다. 저장소 밖에 이 폴더만 복사하면 이웃 노트 모듈이 없어
진짜 노트 모듈을 쓰는 통합 서버 시험 둘만 건너뛴다.

```bash
cd examples/extensions/agent-console-example-link
uv run --project ../../.. python -m pytest
```

- `tests/test_unit.py`: 설정 스키마 도움말, 기본 데이터·도구 이름 바꾸기, 서술자 포트, 리소스 종류(스키마·검사·
  `register`), 층 합치기, 범위가 기존 공급자 뒤에 붙고 포트가 없으면 None.
- `tests/test_engine.py`(fake 백엔드 엔진): 리소스를 붙인 에이전트가 도구·지침을 받고 칸이 소비됨, 리소스 태그·개수와
  설치자 상한, 리소스 없음 → 도구·지침 없음, 포트 없음 → 칸 경고 1건, 프로젝트 Run은 그 공간만, 없는 공간 → 도구
  오류·실행 계속, 이벤트에 본문 없음.
- `tests/test_assembly.py`(테스트 호스트 + 대역): 모두 켜짐 → 읽기, 노트 모듈 끔·실행 모듈 끔 → 이 연동만 `unsatisfied`.
- `tests/test_server.py`(통합 서버 + 진짜 노트 모듈): REST로 쓴 노트를 에이전트가 읽음, 노트 모듈 없는 서버·실행
  모듈 없는 서버가 시작하고 이 연동만 `unsatisfied`.
