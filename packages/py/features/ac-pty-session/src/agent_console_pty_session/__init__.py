"""대화형 CLI를 PTY로 띄우고 화면 줄·원문 흐름·규칙 신호로 읽는 라이브러리.

공개 API:

- ``PtySession``: ``spawn(argv, env, cwd, cols, rows)``·``write``·``send_key``·``screen_lines``·
  ``text_since``·``links``·``wait_changed``·``wait_exit``·``terminate(grace)``.
- ``TerminalText``·``strip_ansi``: 제어 시퀀스 제거·``\\r`` 덮어쓰기·줄 단위 화면(외부 의존 없음).
- ``ExpectRules``·``ExpectRule``·``ExpectWatcher``·``ExpectMatch``: 정규식 규칙 → 이름 붙은 신호
  (컴파일 함수 주입).
- 어댑터: ``PtyHandle``·``PtySpawner`` 프로토콜, ``posix_spawner``(ptyprocess)·``windows_spawner``
  (pywinpty, 선택 추가 기능 ``windows``)·``default_spawner``·``pty_available``,
  ``PtyUnavailableError``.
- 테스트: ``FakePty``·``FakePtySpawner``·``FakeSpawn``.
"""

from __future__ import annotations

from ._adapters import (
    PosixPty,
    PtyHandle,
    PtySpawner,
    PtyUnavailableError,
    WindowsPty,
    default_spawner,
    posix_spawner,
    pty_available,
    windows_spawner,
)
from ._expect import (
    DEFAULT_MAX_PENDING_CHARS,
    Compiler,
    ExpectMatch,
    ExpectRule,
    ExpectRuleError,
    ExpectRules,
    ExpectWatcher,
)
from ._fake import FakePty, FakePtySpawner, FakeSpawn
from ._session import DEFAULT_TERMINATE_GRACE_S, KEYS, PtyClosedError, PtySession
from ._terminal import (
    DEFAULT_MAX_LINE_CHARS,
    DEFAULT_MAX_TEXT_CHARS,
    DEFAULT_SCROLLBACK_LINES,
    TerminalText,
    TextChunk,
    strip_ansi,
)

__all__ = [
    "DEFAULT_MAX_LINE_CHARS",
    "DEFAULT_MAX_PENDING_CHARS",
    "DEFAULT_MAX_TEXT_CHARS",
    "DEFAULT_SCROLLBACK_LINES",
    "DEFAULT_TERMINATE_GRACE_S",
    "KEYS",
    "Compiler",
    "ExpectMatch",
    "ExpectRule",
    "ExpectRuleError",
    "ExpectRules",
    "ExpectWatcher",
    "FakePty",
    "FakePtySpawner",
    "FakeSpawn",
    "PosixPty",
    "PtyClosedError",
    "PtyHandle",
    "PtySession",
    "PtySpawner",
    "PtyUnavailableError",
    "TerminalText",
    "TextChunk",
    "WindowsPty",
    "default_spawner",
    "posix_spawner",
    "pty_available",
    "strip_ansi",
    "windows_spawner",
]
