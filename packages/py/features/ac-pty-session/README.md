# agent-console-pty-session

대화형 CLI(TTY가 있어야 입력을 받는 도구)를 PTY 하위 프로세스로 띄우고, 출력을 **줄 단위 화면**·**제어 시퀀스를 뺀
원문 흐름**·**규칙 신호**로 읽는 라이브러리. 입력(글자·이름 붙은 키)을 보내고, 끝낼 때는 정중한 종료 뒤 유예가
지나면 강제 종료한다. Agent Console에서는 Claude 구독 로그인(`claude auth login`) 중계에 쓴다(설계
`docs/design/ux-overhaul.md` §15.9). 사내 패키지에 의존하지 않는다.

- **`PtySession`**: `spawn(argv, env, cwd, cols, rows)` · `write` · `send_key("enter")` · `screen_lines()` ·
  `text_since(offset)` · `links()` · `wait_changed(version, timeout)` · `wait_exit(timeout)` · `terminate(grace)`.
  셸을 거치지 않는다. 출력은 읽기 스레드 하나가 메모리에 쌓고(한도 있음) 세션이 끝나면 버린다. 아무것도 로그에
  남기지 않는다(출력에 비밀이 섞일 수 있다).
- **`TerminalText`**: 화면 에뮬레이터가 아니라 줄 버퍼다. 색·모드 같은 CSI는 버리고, `\r` 덮어쓰기, 커서
  상하좌우·열 이동, 줄·화면 지우기(`K`·`J`)를 따른다(Ink 같은 TUI의 다시 그리기). 줄바꿈(wrap)은 하지 않는다 —
  긴 URL이 끊기지 않게 하려면 `cols`를 넓게 준다. 원문 흐름은 `\r`·세로 이동을 `\n`으로, `CSI n C`를 공백으로
  바꾼다. OSC 8 링크 대상은 `links()`에 모이고 원문 흐름에도 한 줄로 들어간다.
- **`ExpectRules`·`ExpectWatcher`**: 이름 → 정규식 규칙(데이터)을 줄마다 건다. 컴파일 함수를 주입한다(기본
  `re.compile`). 사용자가 고칠 수 있는 규칙은 안전 검사를 하는 컴파일 함수를 넘긴다. 아직 끝나지 않은 줄에서 줄
  끝에 닿은 맞음(다 오지 않은 URL)은 더 들어올 때까지 미룬다.
- **어댑터**: `PtySpawner`(→ `PtyHandle`) 프로토콜. POSIX `posix_spawner`(ptyprocess, 새 세션 → 종료 신호는
  프로세스 그룹 전체에), Windows `windows_spawner`(pywinpty, 선택 추가 기능 `windows`). `default_spawner()`가
  플랫폼에 맞는 것을 고르고, 쓸 수 없으면 `PtyUnavailableError`(`reason` = `missing_library`·
  `unsupported_platform`, `hint` = 설치 안내).
- **테스트용**: `FakePty`(대본: `output`·`exit_code`·`on_input`·`ignore_terminate`), `FakePtySpawner`(띄울
  때마다 새 가짜).

## 설치

```bash
pip install agent-console-pty-session            # POSIX(ptyprocess 포함)
pip install 'agent-console-pty-session[windows]' # Windows(pywinpty)
```

| 의존성 | 무엇을 | 왜 | 대안 |
| --- | --- | --- | --- |
| `ptyprocess`(ISC, POSIX) | 하위 프로세스를 PTY에 붙여 띄움 | pexpect의 하부라 오래 검증됨. 크기 지정·신호·종료 상태를 제공 | 표준 `pty`(크기 조절·종료 대기 직접 구현), `pexpect`(기대 문법이 필요 이상) |
| `pywinpty`(MIT, Windows, 선택 `windows`) | Windows ConPTY | ptyprocess와 같은 모양의 API | Windows에서 기능 끔 |

터미널 출력 해석은 직접 한다(`TerminalText`). LGPL인 `pyte`는 쓰지 않는다(2026-10-23 결정, 라이선스). 필요한
범위(줄 단위 화면, 덮어쓰기, 지우기, 커서 이동)가 작아 직접 구현이 간단하다.

## 최소 사용

가짜 PTY로 로그인 화면 같은 대화를 흉내 낸다(실제 프로세스 없음). 실제로는 `spawner`를 빼면 플랫폼 어댑터가
쓰인다.

```python
>>> import asyncio
>>> from agent_console_pty_session import ExpectRules, ExpectWatcher, FakePty, PtySession

>>> def script(pty: FakePty, text: str) -> None:
...     if text == "\r":
...         pty.emit("\x1b[2K\rLogin successful\r\n")
...         pty.exit(0)

>>> rules = ExpectRules({
...     "open_url": r"https://\S+/oauth/authorize\S*",
...     "needs_code": r"(?i)paste code",
... })

>>> async def main() -> tuple[list[str], list[str], int | None]:
...     fake = FakePty(
...         output="\x1b[1mOpen:\x1b[0m https://example.com/oauth/authorize?x=1\r\nPaste code > ",
...         on_input=script,
...     )
...     watcher = ExpectWatcher(rules)
...     async with await PtySession.spawn(["my-cli", "login"], cols=400, spawner=fake.spawn) as s:
...         await s.wait_changed(0, 1.0)
...         signals = [m.name for m in watcher.feed(s.text_since(0).text)]
...         s.write("THE-CODE")
...         s.send_key("enter")
...         code = await s.wait_exit(1.0)
...         return signals, s.screen_lines(), code

>>> asyncio.run(main())
(['open_url', 'needs_code'], ['Open: https://example.com/oauth/authorize?x=1', 'Login successful'], 0)

```

`\x1b[2K\r`가 `Paste code >` 줄을 지우고 그 자리에 성공 문구를 썼다. 가짜는 입력을 에코하지 않지만 실제 PTY는
에코하므로, 붙여 넣은 값이 화면·원문 흐름에 다시 나온다. 그 값을 보이면 안 되는 쪽(예: 로그인 코드)은 호출자가
가린다.

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함. POSIX는 실제 PTY + 파이썬 스텁, Windows 어댑터는 pywinpty가 있을 때만
```
