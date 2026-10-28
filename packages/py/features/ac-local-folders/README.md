# agent-console-local-folders

로컬 폴더 고르기 순수 규칙: **경로 정규화**, **폴더 확인**(있음·폴더·권한·숨김·링크·만들 수 있는가·
가장 가까운 상위), 하위 **폴더 이름만** 나열(숨김 기본 숨김·링크·잠금·개수·시간 상한·
탐색 범위 제한), **폴더 만들기**, **기본 시작 위치**, **네이티브 폴더 선택 창**(명령 표 데이터 +
공통 실행기). 서버·웹·다른 사내 패키지 없이 쓴다(표준 라이브러리만).

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

## 네이티브 폴더 선택 창(X35)

서버가 OS의 폴더 선택 창을 띄워 사용자가 고른 **절대 경로**를 얻는다. OS별 명령은 코드가 아니라
**데이터**(`data/folder_dialogs.json`)이고, 공통 실행기 하나가 표를 실행한다.

| 기본 항목 id | 플랫폼(`sys.platform` 접두) | 실행 파일 | 환경 조건 | 취소 판정 |
| --- | --- | --- | --- | --- |
| `windows-powershell` | `win32` | `powershell` | — | 빈 출력(`FolderBrowserDialog`, 맨 위 창, 값은 환경변수로 넘김) |
| `macos-osascript` | `darwin` | `osascript` | — | 빈 출력(`choose folder`, 값은 `on run argv` 인자) |
| `zenity` | `linux`·`freebsd` | `zenity` | `DISPLAY`·`WAYLAND_DISPLAY` 중 하나 | 종료 코드 1 |
| `kdialog` | `linux`·`freebsd` | `kdialog` | `DISPLAY`·`WAYLAND_DISPLAY` 중 하나 | 종료 코드 1 |

- 항목 형식: `{id, label?, platforms, requires, env_requires?, argv, env?, cancel_exit_codes, encoding}`.
  `argv`·`env` 안의 `{initial}`·`{title}`만 값으로 바뀐다(`str.format`이 아니라 스크립트의 중괄호는
  그대로). `argv` 항목은 문자열 또는 `{"when": "initial"|"title", "args": [...]}`(값이 있을 때만 넣음).
  사용자 값을 스크립트 문자열 안에 끼우지 말고 별도 인자나 `env`로 넘긴다(셸·스크립트 주입 방지).
- `load_dialog_specs(extra, include_defaults=True)`: 설치자 항목을 합친다. 같은 id면 그 자리를 바꾸고,
  `"enabled": false`면 뺀다. 새 id는 기본 항목 **앞**(설치자 항목 우선).
- `probe_dialogs(specs, platform=, which=, environ=)` → `DialogAvailability{selected, probes, reason}`:
  명령을 실행하지 않고 플랫폼·실행 파일·환경변수만 본다. `reason`: `no_provider`·`missing_command`·
  `missing_env`. `select_dialog`는 `selected`만 돌려준다.
- `run_dialog(spec, runner=, initial=, title=, timeout=300, cancel=, fs=, environ=)` → `DialogResult{status,
  path, check, provider, exit_code, detail, message}`. 셸 없이 실행, 표준 출력 첫 줄을 경로로 읽어
  `check_folder`로 정규화한다. `status`: `picked`·`cancelled`(취소 코드·빈 출력·`cancel` 신호)·
  `unavailable`(실행 파일 없음)·`timeout`(실행기가 프로세스를 끝냄)·`failed`(`detail`: `exit_code`·
  `bad_encoding`·`invalid_path`·`os_error`). `initial`이 없는 폴더면 가장 가까운 상위 폴더에서 연다.
- 명령 실행은 `CommandRunner` 프로토콜로 주입한다. 실제는 `SubprocessRunner`(`shell=False`, 표준 입력
  없음, 시간 상한·중단 신호(`threading.Event`) 때 `kill`, Windows에서 콘솔 창 없음).
- 특정 실행 환경 전용 규칙은 없다. 서버 프로세스의 플랫폼·실행 파일·환경변수만 본다. 다른 도구가
  필요하면 데이터 항목을 더한다.
- **전제: 루프백 서버에서만 쓴다.** 창은 서버 프로세스가 도는 컴퓨터의 화면에 뜬다. 이 패키지는 서버
  바인딩을 모르므로, 원격 바인딩에서 막는 일(그리고 한 번에 하나만 여는 일)은 부르는 쪽이 한다.

```python
>>> from agent_console_local_folders import (
...     CommandOutcome, MemoryFileSystem, load_dialog_specs, probe_dialogs, run_dialog)
>>> specs = load_dialog_specs()
>>> avail = probe_dialogs(specs, platform="linux",
...                       which=lambda name: "/usr/bin/zenity" if name == "zenity" else None,
...                       environ={"DISPLAY": ":0"})
>>> avail.selected.id
'zenity'
>>> def fake_runner(argv, *, env, timeout, cancel=None):   # 실제는 SubprocessRunner()
...     return CommandOutcome(exit_code=0, stdout=b"/home/me/work/\n")
>>> fs = MemoryFileSystem().add_dir("/home/me/work")
>>> result = run_dialog(avail.selected, runner=fake_runner, title="Project folder", fs=fs)
>>> result.status, result.path
('picked', '/home/me/work')
>>> probe_dialogs(specs, platform="linux", which=lambda name: None, environ={}).reason
'missing_command'

```

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
