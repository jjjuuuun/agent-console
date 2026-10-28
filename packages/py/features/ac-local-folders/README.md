# agent-console-local-folders

로컬 폴더 고르기 순수 규칙: **경로 정규화**, **폴더 확인**(있음·폴더·권한·숨김·링크·만들 수 있는가·
가장 가까운 상위), 하위 **폴더 이름만** 나열(숨김 기본 숨김·링크·잠금·개수·시간 상한·
탐색 범위 제한), **폴더 만들기**, **기본 시작 위치**. 서버·웹·다른 사내 패키지 없이 쓴다(표준 라이브러리만).

- **파일 시스템은 주입한다**(`FileSystem` 프로토콜): 실제 `LocalFileSystem`, 테스트·예제용
  `MemoryFileSystem`(호스트와 무관하게 `posix`/`windows` 경로, 숨김 속성, 링크, 권한 없음을 흉내).
- 폴더 내용은 돌려주지 않는다. `list_dirs`는 하위 폴더 이름·경로와 표시(`hidden`·`link`·`locked`)만,
  `check_folder`는 목록을 읽지 않는다.
- POSIX 경로(`/home/…`)와 Windows 경로(`C:\…`, UNC, 드라이브 대소문자 무시)를 다룬다. 서버 방식과 다른
  경로를 넣으면 `problem="foreign_path"`(쓸 수 없음)이다. 다른 OS 경로로 바꿔 주지 않는다.
- 숨김은 점 이름과 OS 숨김 속성(Windows)으로 판정한다. 그 밖에 이름으로 숨길 폴더와 시작 위치는
  데이터다(확장 지점 X34, `data/browse_defaults.json`, 기본 `hidden_names`는 빈 목록).
  `load_browse_defaults(dict)`로 바꿔 넘긴다.
- 프로젝트 등록부를 모른다. 이미 등록됨·겹침·자기 자신 제외(`exclude_project_id`)·이전 경로와 같음은
  `check.path`를 받아 `ac-projects`/`ac-mod-projects`가 판단한다.

| 함수 | 하는 일 |
| --- | --- |
| `normalize_lexical(raw, *, flavor, environ)` | 입력 → 정규화한 절대 경로(디스크 안 읽음). 따옴표·`~`·`..`·끝 구분자·드라이브 대문자. 실패는 `FolderError` |
| `normalize(raw, *, fs, environ, real=True)` | 위 + 링크를 푼 실제 경로(등록·저장용) |
| `check_folder(raw, *, fs, environ, defaults, roots)` | `FolderCheck`(필드 + `status`: `ok`·`ok_readonly`·`missing`·`missing_parent`·`not_directory`·`no_access`·`invalid`). 입력 때문에 예외를 내지 않음 |
| `list_dirs(path, *, fs, show_hidden, limit=2000, timeout=3.0, roots, defaults, clock)` | `FolderListing(path, parent, entries, truncated, timed_out, hidden_count)` |
| `make_folder(path, *, fs, name=None, roots)` | 폴더 하나 만들기(상위는 안 만듦). `name`을 주면 `path` 아래에 이름 검사 후 |
| `default_roots(environ, *, fs, defaults)` | 홈·루트·macOS `/Volumes/*`·Windows 드라이브 중 있는 것 |
| `nearest_existing(path, *, fs)` | 그 자신(폴더면) 또는 가장 가까운 존재하는 상위 폴더 |
| `path_key`·`is_within`·`validate_folder_name`·`home_dir` | 비교 키(Windows 대소문자 무시), 범위 안인가, 새 폴더 이름 검사, 환경변수의 홈 |

오류 코드(`FolderErrorCode`, `FolderError.code`·`FolderCheck.problem`): `empty`·`invalid_path`·`relative`·
`foreign_path`·`no_home`·`outside_roots`·`not_found`·`not_directory`·`no_access`·`invalid_name`·`exists`·
`missing_parent`·`io_error`. `FolderError.message`는 기본 한국어 문구다(화면은 코드로 자기 문구를 고른다).

시간 상한은 항목 사이에서 확인한다. OS 호출 하나가 멈추는 느린 마운트(네트워크 드라이브 등)는 끊을 수
없으므로, 서버는 이 함수들을 스레드에서 부르고 바깥에서 시간 상한을 건다.

## 의존성: 무엇을 / 왜 / 대안

- 없음(표준 라이브러리만: `ntpath`·`posixpath`로 호스트와 무관하게 두 경로 방식을 다룬다). 대안:
  `pathlib.PureWindowsPath` — `~`·따옴표·드라이브 대문자 정규화를 따로 해야 하고 문자열 비교 키가 필요해
  결국 같은 코드가 된다.

## 설치

```bash
pip install agent-console-local-folders
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-local-folders
```

## 최소 사용

```python
>>> from agent_console_local_folders import (
...     MemoryFileSystem, check_folder, list_dirs, make_folder, default_roots)
>>> fs = (MemoryFileSystem()                     # 실제 디스크는 LocalFileSystem()
...       .add_dir("/home/me/work/app").add_dir("/home/me/.cache")
...       .add_file("/home/me/notes.txt"))
>>> env = {"HOME": "/home/me"}
>>> check = check_folder("~/work/app/", fs=fs, environ=env)
>>> check.status, check.path
('ok', '/home/me/work/app')
>>> check_folder("/home/me/new", fs=fs).status
'missing'
>>> foreign = check_folder("C:\\Work\\me", fs=fs)    # POSIX 서버에 Windows 경로
>>> foreign.status, foreign.problem
('invalid', 'foreign_path')
>>> listing = list_dirs("/home/me", fs=fs)        # 폴더 이름만, 숨김은 기본 숨김
>>> [e.name for e in listing.entries], listing.hidden_count, listing.parent
(['work'], 1, '/home')
>>> make_folder("/home/me/work", name="new", fs=fs).path
'/home/me/work/new'
>>> [(r.kind, r.label) for r in default_roots(env, fs=fs)]
[('home', '~'), ('root', '/')]

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
