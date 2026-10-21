# agent-console-presets

프리셋(데이터 묶음) 읽기·탐색·적용. 프리셋 = 폴더 하나 + `preset.yaml`(매니페스트) + 정의 YAML 항목.
적용은 항목을 **정의 저장소(`agent_console_store.DefinitionStore`)로 복사**하는 것이다. 시스템은 프리셋 존재를
가정하지 않는다(R0.1·R0.2). 설계: `specs/agent-console/design.md` §2.2(Preset).

## 설치

```bash
uv sync --all-packages                        # 워크스페이스 안
uv pip install ./packages/py/features/ac-presets       # 단독
```

런타임·노드 타입·서버는 모른다.

| 의존성 | 무엇을 | 왜 | 대안 |
| --- | --- | --- | --- |
| `agent-console-store` | 저장소 인터페이스(`DefinitionStore`)·`DefinitionKind`·예외 | 저장소 API를 거쳐 써야 모델 검증·버전 스냅샷·If-Match가 그대로 적용된다 | 자체 Protocol을 정의하고 파일을 직접 복사 — 검증·이력 규칙이 중복되고 우회된다 |
| `pydantic` | 매니페스트 모델(`PresetManifest` 등) | 계약·store와 같은 검증 라이브러리, JSON Schema 생성 가능 | dataclass + 수동 검증, 또는 `jsonschema`로 dict 검증 — 오류 메시지·타입 정보가 약해진다 |
| `ruamel-yaml` | 매니페스트·항목 YAML 읽기(safe 로더) | store와 같은 라이브러리라 의존이 늘지 않는다 | PyYAML(`safe_load`) — 기능은 충분하지만 의존이 하나 더 생긴다 |

## 매니페스트 (`preset.yaml`)

```yaml
kind: preset
id: my-preset                 # slug
schema_version: 1
name: 내 프리셋
description: ""
labels: []
attributes: {}
items:                        # 프리셋 폴더 기준 상대 경로. 첫 폴더 이름 = DefinitionKind.directory
  - agents/a.yaml
  - {file: extra/g.yaml, kind: graph}   # 종류를 직접 지정
default_entry: g              # 선택. 대표 그래프 id(예시 graph 생략 시 사용)
featured: 1                   # 선택. 화면 "바로 시작" 순서(작을수록 앞). 생략 = 바로 시작에 없음
start_graph: g                # 선택. 적용 뒤 대화를 열 팀 구성 id. 생략 = default_entry, null = 열지 않음
badges: [추천]                 # 선택. 카드 배지 글자(백엔드 배지는 서버 모듈이 계산해 덧붙인다)
samples:                      # 선택. 시연 입력(화면 "예시 입력", 자기 검사)
  - input: "..."              # 사용자 메시지(Run 입력 text)
    graph: null                 # 생략하면 default_entry
    description: ""
    # 모르는 필드는 보존한다. 번들 프리셋 자기 검사는 responses(열린 상호작용에 순서대로 줄 응답)를 쓴다.
```

- 단일 문서 종류(settings)는 항목이 될 수 없다 — 사용자 설정을 통째로 덮어쓰지 않기 위함.
  (적용 때 설정의 `default_entry`를 쓰던 `set_default_entry`는 콘솔과 함께 2R.20에서 삭제했다.)
- 항목 문서는 종류 모델로 **검증만** 하고 원본 그대로 쓴다(생략한 필드가 null로 채워지지 않는다 — "생략 = 상속").
- 본문이 있는 종류(`DefinitionKind.content_field`, 예: resource)는 저장소 배치와 같게 항목 파일 옆
  `<id>/<content.file>`에 본문을 둔다(예: `resources/team-guide.yaml` + `resources/team-guide/guide.md`).
  적용은 `create`/`save` 뒤 `write_content`로 본문을 쓴다. 본문 파일이 없으면 `PresetError`.
- 항목 경로는 폴더 밖(`..`, 절대 경로)을 가리킬 수 없다.
- 모르는 최상위 필드는 보존한다.
- `PresetManifest.start_graph_id()`는 위 `start_graph` 규칙을 적용한 값이다. `collect_values(load_items(preset), key)`는
  항목 문서 어디에서든 `key`의 문자열 값을 모은다(예: `"backend"` → 프리셋이 쓰는 실행 백엔드 이름, 쓰기 없음).

## 최소 사용 예

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_presets import apply_preset, discover_presets
>>> from agent_console_store import InMemoryDefinitionStore

```

예제 프리셋 폴더(실제로는 번들·사용자 프리셋 폴더). 매니페스트 `preset.yaml` + 항목 파일.

```python
>>> tmp = tempfile.TemporaryDirectory()
>>> presets_dir = Path(tmp.name)
>>> (presets_dir / "dev-team" / "agents").mkdir(parents=True)
>>> _ = (presets_dir / "dev-team" / "agents" / "pl.yaml").write_text(
...     "kind: agent\nid: pl\nname: PL\n", encoding="utf-8"
... )
>>> _ = (presets_dir / "dev-team" / "preset.yaml").write_text(
...     "kind: preset\nid: dev-team\nname: 개발 팀\nitems:\n  - agents/pl.yaml\n", encoding="utf-8"
... )

>>> found = discover_presets([presets_dir])  # 경로 목록은 앱 설정에서(없는 경로는 무시)
>>> [p.id for p in found.presets], found.problems
(['dev-team'], [])
>>> store = InMemoryDefinitionStore()  # 실제로는 FileDefinitionStore(workspace_dir)
>>> for policy in ["skip", "skip", "rename"]:  # skip | overwrite | rename
...     for item in apply_preset(found.get("dev-team"), store, on_conflict=policy).items:
...         print(item.kind, item.id, "->", item.target_id, item.action, item.error)
agent pl -> pl created None
agent pl -> pl skipped None
agent pl -> pl-2 renamed None
>>> tmp.cleanup()

```

| API | 설명 |
| --- | --- |
| `load_preset(dir, *, manifest_file="preset.yaml") -> Preset` | 폴더 하나 읽기(`PresetError`) |
| `discover_presets(paths, *, manifest_file) -> PresetDiscovery` | 각 경로 바로 아래 폴더를 찾음. 없는 경로 무시, 같은 id는 앞 경로 우선, 문제는 `problems` |
| `load_items(preset, *, kinds=DEFAULT_KINDS) -> list[PresetItem]` | 항목 읽기·모델 검증(쓰기 없음) |
| `apply_preset(preset, store, *, kinds, on_conflict="skip", rewrite_references=None, validate_item=None, dependencies=None, message=None, stamp=None) -> ApplyReport` | 먼저 전부 검증(형식 오류면 아무것도 쓰지 않고 `PresetError`) → (의존 순서로 정렬) → 저장소 `create`/`save(expected_version)` |
| `order_items(items, dependencies, *, warnings=None) -> list[PresetItem]` | 쓰는 정의가 먼저 오게 늘어놓기(프리셋 안 항목만, 순환은 끊음) |

- 충돌 정책: `skip`(기본, 사용자 정의 보존) / `overwrite`(현재 버전 해시로 If-Match 저장) / `rename`(`<id>-2`, `<id>-3`…).
- `rename`으로 바뀐 id를 가리키는 참조(예: agent 노드의 `agent_ref`)는 형식을 아는 쪽이 고친다 —
  `rewrite_references(kind, document, renames)`를 주입한다. 주지 않으면 `ApplyReport.warnings`에 남는다.
- 모델 검증 밖의 규칙(예: 리소스 종류 검사의 평문 비밀 금지)은 `validate_item(kind, document) -> 오류 목록`
  (`ItemValidator`)으로 주입한다. 쓰기 직전(참조를 고친 뒤) 건너뛰지 않는 항목마다 부르고, 오류가 있으면 그
  항목은 저장하지 않고 `failed`(`error = "validation_failed: ..."`, 접두어 `ITEM_INVALID`)로 남긴 채 나머지를
  계속한다. 오류 문자열은 보고서·로그로 나가므로 값을 넣지 않는다. 이 패키지는 리소스 종류를 모른다.
- 적용 순서: `dependencies(kind, document) -> [(kind, id), ...]`(`ItemDependencies`)를 주면 항목이 쓰는 정의(같은
  프리셋 안의 것)를 먼저 쓴다 — 예: 에이전트 → 자식 팀 구성 → 그 팀 구성을 넣은 팀 구성. 무엇이 무엇을 쓰는지는
  노드 타입이 정하므로 앱이 주입한다(서버는 `ac-teams.graph_dependencies`). 없으면 매니페스트 순서. 의존 함수가
  예외를 내면 그 항목만 순서를 포기하고 `warnings`에 종류·id를 남긴다.
- 찍기: `stamp={"project": "app"}`(`Stamp`)를 주면 쓰는 항목(만듦·덮어씀·이름 바꿈)의 최상위 필드에 그 값을
  찍는다(값 `None` = 필드 빼기). 종류 모델이 선언하지 않은 필드는 찍지 않고 `warnings`에 남긴다. 찍은 뒤
  `validate_item`이 본다. 필드의 뜻(예: 프로젝트 범위)은 이 패키지가 모른다(`stamp_fields`·`apply_stamp`).
- `ApplyReport.items[]` = `AppliedItem(source, kind, id, target_id, action, error)`,
  `action` ∈ created·overwritten·renamed·skipped·failed. `ok`는 failed가 없을 때 참.

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-presets`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
uv run pytest packages/py/features/ac-presets/tests
```

- `test_..._apply.py`: 매니페스트·탐색·충돌 정책·기본 진입점·오류(즉석 프리셋).
- 프리셋 없이 동작하는지(빈 프리셋 경로 + 빈 workspace)는 저장소 `tests/integration/test_integration_presets_empty.py`가 본다.
  또 프리셋 없이(빈 경로·빈 workspace) 레지스트리 로드 → 코드로 그래프 생성 → 검증 → 실행이 되는지 확인한다.
  테스트 전용 의존(runtime·graph·routing·nodes-core·backend-fake)은 `[dependency-groups] dev`에 적었다.
