# agent-console-pty-session

A library that starts an interactive CLI (a tool that needs a TTY to take input) as a PTY child process and reads its output as a **line-based screen**, an **original stream with
control sequences removed**, and **rule signals**. It sends input (characters and named keys), and to stop it sends a polite termination and forcibly kills it after a grace
period. Agent Console uses it to relay the Claude subscription sign-in (`claude auth login`).
It does not depend on any internal package.

- **`PtySession`**: `spawn(argv, env, cwd, cols, rows)` · `write` · `send_key("enter")` · `screen_lines()` ·
  `text_since(offset)` · `links()` · `wait_changed(version, timeout)` · `wait_exit(timeout)` · `terminate(grace)`.
  It does not go through a shell. Output is collected in memory by one reader thread (with a limit) and discarded when the session ends. Nothing is
  logged (secrets can appear in the output).
- **`TerminalText`**: a line buffer, not a screen emulator. It drops CSI such as colors and modes, and follows `\r` overwrites, cursor
  up, down, left, right, and column moves, and line and screen erasing (`K`, `J`) (the redraws of TUIs such as Ink). It does not wrap lines;
  pass a wide `cols` so long URLs are not broken. The original stream turns `\r` and vertical moves into `
` and `CSI n C` into spaces.
  OSC 8 link targets are collected in `links()` and also go into the original stream as one line.
- **`ExpectRules`, `ExpectWatcher`**: apply name → regex rules (data) to each line. The compile function is injected (default
  `re.compile`). For rules users can edit, pass a compile function that does safety checks. A match on an unfinished line that reaches the end of
  the line (a URL that has not fully arrived) is deferred until more input arrives.
- **Adapters**: the `PtySpawner` (→ `PtyHandle`) protocol. POSIX `posix_spawner` (ptyprocess, new session, so termination signals go to
  the whole process group), Windows `windows_spawner` (pywinpty, optional extra `windows`). `default_spawner()` picks the one that fits
  the platform, and raises `PtyUnavailableError` when none is usable (`reason` = `missing_library` or
  `unsupported_platform`, `hint` = install instructions).
- **For tests**: `FakePty` (a script: `output`, `exit_code`, `on_input`, `ignore_terminate`), `FakePtySpawner` (a new fake
  each time it spawns).

## Installation

```bash
pip install agent-console-pty-session            # POSIX (includes ptyprocess)
pip install 'agent-console-pty-session[windows]' # Windows(pywinpty)
```

| Dependency | What | Why | Alternatives |
| --- | --- | --- | --- |
| `ptyprocess` (ISC, POSIX) | Starts a child process attached to a PTY | Long proven as the base of pexpect. Provides size settings, signals, and exit status | Standard `pty` (size changes and exit waits written by hand), `pexpect` (more expect syntax than needed) |
| `pywinpty` (MIT, Windows, optional `windows`) | Windows ConPTY | An API shaped like ptyprocess | Turn the feature off on Windows |

Terminal output is interpreted in-house (`TerminalText`). `pyte`, which is LGPL, is not used (decided 2026-10-23, for licensing). The needed
scope (line-based screen, overwrites, erasing, cursor moves) is small, so implementing it directly is simple.

## Minimal usage

A fake PTY imitates a sign-in-screen-like conversation (no real process). In real use, leave out `spawner` and the platform adapter
is used.

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

`\x1b[2K\r` erased the `Paste code >` line and wrote the success message in its place. The fake does not echo input, but a real PTY
does, so pasted values appear again on the screen and in the original stream. A caller that must not show those values (for example, a sign-in code)
masks them.

<!-- doctest: keep a blank line after the expected output (so the closing ``` line is not read as output). -->

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes development dependencies (dev group)
uv run ruff check .
uv run mypy
uv run pytest          # includes the README.md doctests. POSIX uses a real PTY + a Python stub; the Windows adapter only when pywinpty is installed
```
