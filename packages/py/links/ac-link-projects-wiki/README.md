# agent-console-link-projects-wiki

프로젝트 폴더를 위키 모듈의 **위키 공간**으로 주는 연동 모듈이다(design §7R.3·§7R.4·§7R.13, R15.2·R15.6·
R15.11·R9.1). 프로젝트 모듈(`mod-projects`)과 위키 모듈(`mod-wiki`)은 서로를 모르고, 이 연동이 둘을 잇는다.

- 필수 포트 `projects.spaces`(등록 id → 프로젝트 공간). 없으면 이 연동은 꺼진다.
- 제공 포트 `wiki.spaces`(`ProjectWikiSpaces`): `open(등록 id) -> ProjectWikiSpace{store, folder,
  config_writable, config_dir, pages_dir, pages_root, index_dir}`. 위키·위키 규칙 정의는 그 폴더의 정의
  저장소(`<폴더>/.agent-console/`), 페이지는 `<폴더>/.agent-console/<pages_dir>/<위키 id>/`, 검색 색인은
  상태 폴더(`<구성 폴더>/.state/<index_dir>/`, 다시 만들 수 있는 캐시)에 들어간다. 같은 폴더를 다른 앱(다른
  workspace)에 등록해도 위키·페이지·규칙이 그대로이고, 기록 연동(`link-projects-records`)을 함께 켜면
  페이지 기록도 그 폴더의 기록 DB에 남아 그대로다.
- **경로 지킴**(§PI.5): `ac-projects`의 `FolderGuard`(`link-projects-sdd`와 같은 규칙). 페이지 폴더가 구성
  폴더의 예약 폴더(상태·세션 폴더, 정의 종류 폴더, 설정 `reserved_dirs`)와 겹치거나, 링크를 푼 페이지
  폴더·위키 폴더가 프로젝트 폴더 밖이면 열지 않는다(422 `folders.invalid_path`, 절대 경로는 싣지 않음).
  위키 폴더 안 페이지 경로는 `ac-wiki` `LocalWikiPages`가 지킨다.
- 쓸 수 없는 폴더는 `config_writable=false` — 보기·검색만 되고 쓰기는 409 `project.config_readonly`
  (`mod-wiki`가 낸다). 검색 색인은 메모리에 둔다.
- 공간을 열 때 매니페스트(`project.yaml`)가 깨졌으면 409 `project.manifest_invalid`, 폴더가 없으면 409
  `project.folder_missing`. 열기만으로는 아무것도 만들지 않는다.
- **이 연동이 꺼지면** `mod-wiki`가 `?project=` 요청에 409 `wiki.spaces_unavailable`을 낸다. 위키를 앱
  workspace(단독 루트)에 대신 만들지 않는다.

## 설치

```bash
pip install agent-console-link-projects-wiki
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-projects-wiki
```

## 의존성 (무엇을 / 왜 / 대안)

새 외부 의존은 없다(`agent-console-project-space`(공간·매니페스트)·`agent-console-projects`(경로 지킴
`FolderGuard`)·`agent-console-store`(경로 문자열 검사)·`agent-console-modkit`·`agent-console-contracts`는 사내
패키지). 위키 모듈(`agent-console-mod-wiki`)은 개발 의존(시험)일 뿐이고 포트 이름으로만 잇는다.

## 최소 사용

서버 없이 폴더 하나를 위키 공간으로 연다.

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_link_projects_wiki import ProjectWikiSpaces, UnsafePagesRoot
>>> from agent_console_link_projects_wiki.testing import FolderSpaces
>>> folder = Path(tempfile.mkdtemp())
>>> spaces = ProjectWikiSpaces(lambda: FolderSpaces({"app": folder}))  # projects.spaces 자리
>>> space = spaces.open("app")
>>> space.config_dir, space.pages_dir, space.config_writable
('.agent-console', '.agent-console/wiki-pages', True)
>>> space.pages_root == folder / ".agent-console" / "wiki-pages"
True
>>> try:
...     ProjectWikiSpaces(lambda: FolderSpaces({"app": folder}), pages_dir=".state").open("app")
... except UnsafePagesRoot as exc:
...     exc.reason
'reserved'

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 설정 (`modules.options.link-projects-wiki`)

| 키 | 기본 | 뜻 |
| --- | --- | --- |
| `pages_dir` | `wiki-pages`(패키지 데이터) | 구성 폴더 안 페이지 폴더. 적지 않으면 `modules.options.mod-wiki.pages_dir`를 이어받는다(`SeedSetting`) |
| `index_dir` | `wiki-index`(패키지 데이터) | 상태 폴더 안 검색 색인 폴더 |
| `reserved_dirs` | `[]` | 페이지 폴더와 겹치면 안 되는 폴더(프로젝트 폴더 기준). 상태·세션·정의 종류 폴더는 늘 막는다 |

구성 폴더 이름은 `mod-projects.config_dir`를 따른다(`pages_root` = `<config_dir>/<pages_dir>`).

## 단독 실행

```bash
python -m agent_console_link_projects_wiki --check                        # 빈 폴더 목록 모듈과 조립 확인
python -m agent_console_link_projects_wiki --with mod-projects --with mod-wiki
```

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
