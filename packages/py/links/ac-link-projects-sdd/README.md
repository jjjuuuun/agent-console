# agent-console-link-projects-sdd

프로젝트 폴더를 SDD 모듈의 **스펙 공간**으로 주는 연동 모듈이다(design §6R.3·§6R.4, R15.2·R15.6). 프로젝트
모듈(`mod-projects`)과 SDD 모듈(`mod-sdd`)은 서로를 모르고, 이 연동이 둘을 잇는다.

- 필수 포트 `projects.spaces`(등록 id → 프로젝트 공간). 없으면 이 연동은 꺼진다.
- 제공 포트 `sdd.spaces`(`ProjectSddSpaces`): `open(등록 id) -> ProjectSddSpace{store, folder,
  config_writable, files, config_dir}`. 스펙·문서 틀은 그 폴더의 정의 저장소(`<폴더>/.agent-console/`)에
  들어가므로, 같은 폴더를 다른 앱(다른 workspace)에 등록해도 스펙·규칙이 그대로다.
- `files`(`ProjectSpecFiles`)는 그 폴더 안만 읽고 쓴다. `..`·절대 경로·링크(실제 경로가 폴더 밖)는
  거부(422 `folders.invalid_path`), 앱 구성 폴더(`.agent-console`, 설정에 따라 바뀜)는 읽기·쓰기·목록 모두
  거부, 쓸 수 없는 폴더는 409 `project.config_readonly`.
- 공간을 열 때 폴더 매니페스트(`project.yaml`)가 깨졌으면 409 `project.manifest_invalid`, 폴더가 없으면
  409 `project.folder_missing`. 열기만으로는 아무것도 만들지 않는다.
- **이 연동이 꺼지면** `mod-sdd`가 `?project=` 요청에 409 `sdd.spaces_unavailable`을 낸다. 스펙을 앱
  workspace에 대신 만들지 않는다.

## 설치

```bash
pip install agent-console-link-projects-sdd
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-projects-sdd
```

## 의존성 (무엇을 / 왜 / 대안)

새 외부 의존은 없다(`agent-console-project-space`(공간·매니페스트)·`agent-console-projects`(경로 비교
`folder_within`)·`agent-console-sdd`(`SpecFiles`·경로 검사)·`agent-console-store`·`agent-console-modkit`은 사내
패키지).

## 최소 사용

서버 없이 폴더 하나를 스펙 공간으로 연다.

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_link_projects_sdd import ProjectSddSpaces
>>> from agent_console_link_projects_sdd.testing import FolderSpaces
>>> folder = Path(tempfile.mkdtemp())
>>> spaces = ProjectSddSpaces(lambda: FolderSpaces({"app": folder}))  # projects.spaces 자리
>>> space = spaces.open("app")
>>> space.config_dir, space.config_writable
('.agent-console', True)
>>> space.files.write("docs/plan.md", b"# plan\n")
>>> [e.name for e in space.files.list("docs")]
['plan.md']
>>> from agent_console_sdd import SpecPathError
>>> try:
...     space.files.write(".agent-console/x.md", b"x")
... except SpecPathError as exc:
...     exc.details["reason"]
'reserved'

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 설정 (`modules.options.link-projects-sdd`)

`reserved_dirs`(기본 `[]`): 앱 구성 폴더 말고도 가져오기·내보내기·파일 목록에서 손대지 않을 폴더(프로젝트
폴더 기준 상대 경로, 예: `.git`). 구성 폴더 이름은 `mod-projects.config_dir`, 스펙 폴더는 `mod-sdd.spec_dir`을
따른다(`SddInfo.spec_root` = `<config_dir>/<spec_dir>`).

## 단독 실행

```bash
python -m agent_console_link_projects_sdd --check                       # 빈 폴더 목록 모듈과 조립 확인
python -m agent_console_link_projects_sdd --with mod-projects --with mod-sdd
```

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
