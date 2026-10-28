# agent-console-project-space

프로젝트 폴더 하나의 `<폴더>/.agent-console/`를 **구성 사본 공간**으로 연다.
정의(에이전트·팀 구성·리소스 등)는 workspace 정의 YAML과 같은 형식(종류별 폴더, `ac-store`의
`FileDefinitionStore`)으로 저장하고, 폴더 매니페스트 `project.yaml`을 읽고 쓴다.
서버·DB·웹 없이 폴더 하나만으로 동작한다.

- 등록 시점(`init_space`)에 `project.yaml`과 `.gitignore`를 **없을 때만** 만든다. 있으면 채택하고 고치지 않는다.
  깨진 매니페스트 폴더에는 아무것도 쓰지 않는다. 쓸 수 없는 폴더는 `config_writable=False`로 알린다.
- 비밀처럼 보이는 값은 저장하지 않는다(`SecretRejected`, 값 없이 위치만). 정의에는 `secret://<이름>` 참조만 둔다.
- 충돌 감지는 정의 저장소와 같은 If-Match(`expected_version`)다. 매니페스트도 같다.
- 종류 이름·폴더 이름·파일 이름은 코드에 없다. 종류는 `DefinitionKind`(`portable`인 것만 공간에 들어간다),
  이름은 `config_dir`·`SpaceLayout` 인자다. `.gitignore` 틀은 패키지 데이터 `data/gitignore.template`이다.
- 파일 시스템은 `SpaceFiles`로 주입한다(기본 `LocalFiles`). 정의 저장소 자체는 `FileDefinitionStore`라서
  그 root는 로컬 경로다.
- 기록 DB(`records.sqlite3`)·메모리 DB 경로만 알려 준다(`records_db_path`·`memory_db_path`). 파일은 만들지 않는다.

## 설치

```bash
pip install agent-console-project-space
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-project-space
```

의존(무엇을 / 왜 / 대안): `agent-console-store`(정의 저장소·YAML 형식 재사용 / 새 저장 형식을 만들지 않으려고),
`agent-console-secret-rules`(비밀 의심 규칙 재사용 / 규칙을 복사하지 않으려고, 대안: 검사 함수 주입만 받기 -- 단독
사용에서 검사가 빠질 수 있어 택하지 않음), `agent-console-contracts`(`ProjectManifest`).

## 최소 사용

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_contracts import ProjectManifest
>>> from agent_console_project_space import init_space, open_space, read_manifest

>>> folder = Path(tempfile.mkdtemp())
>>> result = init_space(folder, manifest=ProjectManifest(id="payments", name="결제 서비스"))
>>> result.manifest_state, result.gitignore_state, result.config_writable
('created', 'created', True)
>>> sorted(p.name for p in (folder / ".agent-console").iterdir())
['.gitignore', 'project.yaml']

>>> space = open_space(folder)
>>> _ = space.definitions.create("agent", {"id": "dev", "name": "개발자"})
>>> space.definitions.list_ids("agent")
['dev']
>>> read_manifest(space).manifest.name
'결제 서비스'

>>> from agent_console_project_space import SecretRejected
>>> try:
...     space.definitions.create("agent", {"id": "bad", "name": "x", "attributes": {"api_key": "abcd1234efgh5678"}})
... except SecretRejected as error:
...     print([f.path for f in error.findings])
['/attributes/api_key']

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 공개 API

| 이름 | 하는 일 |
| --- | --- |
| `open_space(folder, *, kinds, versions, config_dir, files, layout, secret_rules, scan_bodies, ...)` | 공간을 연다(쓰기 없음). `ProjectSpace{folder, root, definitions, manifest_path, gitignore_path, memory_db_path, records_db_path, sessions_dir, state_dir, portable_kinds, config_writable}` |
| `init_space(folder, *, manifest, gitignore_template, **open 인자)` | `project.yaml`·`.gitignore`를 없을 때만 만든다 -> `InitResult{space, manifest, manifest_state, manifest_issue, gitignore_state}` |
| `read_manifest(space)` / `write_manifest(space, manifest, *, expected_version)` | 매니페스트 읽기(없으면 None) / If-Match 쓰기(모르는 키·주석 보존) |
| `reset_manifest(space, manifest, *, now)` | 옛 `project.yaml`을 `<state_dir>/backups/project-<UTC>.yaml`로 보관하고 새로 씀 |
| `portable_kinds(kinds)` | 공간에 들어가는 종류(`DefinitionKind.is_portable`) |
| `scan_secrets(rules, document)` | 평문 비밀 의심 위치(값 없음) |
| `default_gitignore_template()` | 패키지 데이터 `.gitignore` 틀 |
| `SpaceFiles`·`LocalFiles` | 파일 시스템 주입점 / 기본 구현 |
| 예외 | `SpaceError` 하위: `FolderMissing`·`ConfigReadonly`·`UnsafeConfigDir`·`ManifestInvalid`(`reason`), `SecretRejected`(`StoreError`, `findings`). `code`는 계약 `ErrorCodes` |

`.gitignore` 틀의 줄은 구성 폴더 바로 아래만 가리키도록 `/`로 시작한다(리소스 이름이 `claude`·`sessions`여도
커밋에서 빠지지 않게). 버전 기록은 호출자가 `versions=`로 넘긴다(보통 그 폴더 기록 DB). 생략하면 메모리다.
테스트 도구는 `agent_console_project_space.testing`(`ReadOnlyFiles` 등)이다.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
