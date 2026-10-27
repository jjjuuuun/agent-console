"""터미널 출력 해석: 제어 시퀀스 제거, 줄 단위 화면, 원문 흐름(외부 의존 없음).

전체 VT100 에뮬레이터가 아니다. 대화형 CLI(Ink 같은 TUI)를 줄 단위로 읽는 데 필요한 만큼만 한다.

- **화면**(``screen_lines``): 커서가 있는 줄 목록. ``\\r``은 줄 맨 앞으로 가서 덮어쓰고,
  ``\\n``은 다음 줄, ``\\b``는 한 칸 뒤로, ``\\t``는 8칸 단위. CSI 커서 이동
  (``A B C D E F G H f d``)과 지우기(``K``·``J``)를 따른다. 그 밖의 CSI(색·모드 등)는 버린다.
  줄바꿈(wrap)은 하지 않는다(줄 길이는 하위 프로세스가 받은 열 수로 정해진다).
  넓은 글자도 한 칸으로 센다.
- **원문 흐름**(``text_since``): 제어 시퀀스를 뺀 글자만 이어 붙인 문자열.
  ``\\r\\n``·``\\r`` → ``\\n``, 세로 커서 이동·화면 지우기 → ``\\n``,
  ``CSI n C``(앞으로 n칸) → 공백 n개. 규칙 매칭(``ExpectRules``)용이다.
- **OSC 8 링크**: 대상 URI를 ``links()``에 모으고, 원문 흐름에는 ``\\n<URI>\\n``으로 넣는다
  (화면 글자에 링크 주소가 안 보여도 규칙이 찾을 수 있게).
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_SCROLLBACK_LINES = 1000
"""화면이 기억하는 최대 줄 수. 넘으면 위에서부터 버린다."""

DEFAULT_MAX_TEXT_CHARS = 1_000_000
"""원문 흐름이 기억하는 최대 글자 수. 넘으면 앞에서부터 버린다(오프셋은 계속 늘어난다)."""

DEFAULT_MAX_LINE_CHARS = 4096
"""화면 한 줄 최대 글자 수(넘는 글자는 버린다)."""

_ESC = "\x1b"
_BEL = "\x07"
_TAB_WIDTH = 8

# 파서 상태
_GROUND = 0
_ESCAPE = 1
_CSI = 2
_OSC = 3
_OSC_ESC = 4  # OSC 안에서 ESC를 봤다(ST = ESC \ 기다림)
_STRING = 5  # DCS·SOS·PM·APC: ST까지 버림
_STRING_ESC = 6
_ESC_INTERMEDIATE = 7  # ESC ( B 같은 문자 집합 지정: 다음 한 글자 버림


@dataclass(frozen=True)
class TextChunk:
    """``text_since`` 결과.

    Attributes:
        text: 요청한 오프셋 뒤의 원문(버려진 앞부분은 빠진다).
        offset: 다음 호출에 넘길 오프셋(지금까지 쌓인 전체 길이).
        dropped: 요청한 오프셋이 이미 버려진 범위에 있어 잃은 글자 수.
    """

    text: str
    offset: int
    dropped: int = 0


class TerminalText:
    """터미널 출력 글자를 받아 화면 줄·원문 흐름·OSC 8 링크로 바꾼다(스레드 안전 아님).

    Args:
        scrollback_lines: 화면이 기억하는 최대 줄 수.
        max_text_chars: 원문 흐름이 기억하는 최대 글자 수.
        max_line_chars: 화면 한 줄 최대 글자 수.

    Example:
        >>> t = TerminalText()
        >>> t.feed("\\x1b[32mloading 10%\\rloading 99%\\r\\ndone\\r\\n")
        >>> t.screen_lines()
        ['loading 99%', 'done']
        >>> t.text_since(0).text
        'loading 10%\\nloading 99%\\ndone\\n'
    """

    def __init__(
        self,
        *,
        scrollback_lines: int = DEFAULT_SCROLLBACK_LINES,
        max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
        max_line_chars: int = DEFAULT_MAX_LINE_CHARS,
    ) -> None:
        if scrollback_lines < 1 or max_text_chars < 1 or max_line_chars < 1:
            raise ValueError("한도는 1 이상이어야 합니다")
        self._scrollback = scrollback_lines
        self._max_text = max_text_chars
        self._max_line = max_line_chars
        self._lines: list[list[str]] = [[]]
        self._row = 0
        self._col = 0
        self._state = _GROUND
        self._seq: list[str] = []
        self._text: list[str] = []
        self._text_len = 0  # 지금 기억하는 글자 수
        self._text_base = 0  # 버린 앞부분 길이
        self._pending_cr = False  # 원문 흐름: 직전 글자가 \r
        self._links: list[str] = []

    # ------------------------------------------------------------ 공개

    def feed(self, data: str) -> None:
        """출력 조각 하나를 해석한다. 시퀀스가 조각 경계에 걸쳐도 이어서 처리한다."""
        for ch in data:
            self._step(ch)

    def screen_lines(self, last: int | None = None) -> list[str]:
        """화면 줄(뒤쪽 공백 제거, 끝의 빈 줄 제거).

        Args:
            last: 마지막 몇 줄만(None = 기억하는 전부).
        """
        lines = ["".join(cells).rstrip() for cells in self._lines]
        while lines and not lines[-1]:
            lines.pop()
        if last is not None:
            lines = lines[-last:] if last > 0 else []
        return lines

    @property
    def text_offset(self) -> int:
        """지금까지 원문 흐름에 쌓인 전체 글자 수(버린 앞부분 포함)."""
        return self._text_base + self._text_len

    def text_since(self, offset: int = 0) -> TextChunk:
        """``offset`` 뒤의 원문 흐름."""
        self._compact_text()
        whole = self._text[0] if self._text else ""
        start = max(offset, self._text_base)
        dropped = max(0, self._text_base - offset)
        return TextChunk(whole[start - self._text_base :], self.text_offset, dropped)

    def links(self) -> list[str]:
        """지금까지 본 OSC 8 링크 대상(처음 본 순서, 중복 없음)."""
        return list(self._links)

    # ------------------------------------------------------------ 원문 흐름

    def _emit(self, text: str) -> None:
        if not text:
            return
        self._text.append(text)
        self._text_len += len(text)
        if self._text_len > self._max_text:
            self._compact_text()
            whole = self._text[0]
            cut = len(whole) - self._max_text
            self._text = [whole[cut:]]
            self._text_base += cut
            self._text_len -= cut

    def _compact_text(self) -> None:
        if len(self._text) > 1:
            self._text = ["".join(self._text)]

    def _emit_newline(self) -> None:
        self._pending_cr = False
        self._emit("\n")

    # ------------------------------------------------------------ 화면

    def _line(self) -> list[str]:
        return self._lines[self._row]

    def _move_to(self, row: int, col: int) -> None:
        row = max(0, row)
        while len(self._lines) <= row:
            self._lines.append([])
        overflow = len(self._lines) - self._scrollback
        if overflow > 0:
            del self._lines[:overflow]
            row = max(0, row - overflow)
        self._row = row
        self._col = max(0, min(col, self._max_line - 1))

    def _put(self, ch: str) -> None:
        line = self._line()
        if self._col >= self._max_line:
            return
        if self._col < len(line):
            line[self._col] = ch
        else:
            line.extend(" " * (self._col - len(line)))
            line.append(ch)
        self._col += 1

    def _newline(self) -> None:
        self._move_to(self._row + 1, self._col)

    def _erase_line(self, mode: int) -> None:
        line = self._line()
        if mode == 0:
            del line[self._col :]
        elif mode == 1:
            for i in range(min(self._col + 1, len(line))):
                line[i] = " "
        else:
            line.clear()

    def _erase_display(self, mode: int) -> None:
        if mode == 0:
            del self._line()[self._col :]
            del self._lines[self._row + 1 :]
        elif mode == 1:
            for i in range(self._row):
                self._lines[i] = []
            self._erase_line(1)
        else:
            self._lines = [[]]
            self._row = 0
            self._col = 0

    # ------------------------------------------------------------ 파서

    def _step(self, ch: str) -> None:
        state = self._state
        if state == _GROUND:
            self._ground(ch)
        elif state == _ESCAPE:
            self._escape(ch)
        elif state == _CSI:
            if "\x40" <= ch <= "\x7e":
                self._state = _GROUND
                self._csi("".join(self._seq), ch)
                self._seq.clear()
            elif ch == _ESC:
                self._seq.clear()
                self._state = _ESCAPE
            elif ch in "\x18\x1a":  # CAN·SUB: 시퀀스 취소
                self._seq.clear()
                self._state = _GROUND
            elif len(self._seq) < 64:
                self._seq.append(ch)
        elif state == _OSC:
            if ch == _BEL:
                self._osc_end()
            elif ch == _ESC:
                self._state = _OSC_ESC
            elif len(self._seq) < 8192:
                self._seq.append(ch)
        elif state == _OSC_ESC:
            if ch == "\\":
                self._osc_end()
            else:  # ST가 아닌 ESC: OSC를 버리고 새 시퀀스로
                self._seq.clear()
                self._state = _ESCAPE
                self._escape(ch)
        elif state == _STRING:
            if ch == _ESC:
                self._state = _STRING_ESC
            elif ch == _BEL:
                self._state = _GROUND
        elif state == _STRING_ESC:
            self._state = _GROUND if ch == "\\" else _STRING
        elif state == _ESC_INTERMEDIATE:
            self._state = _GROUND

    def _ground(self, ch: str) -> None:
        if ch == _ESC:
            self._state = _ESCAPE
            return
        if ch == "\r":
            self._col = 0
            self._pending_cr = True
            return
        if ch == "\n":
            self._newline()
            self._col = 0  # 출력 쪽 onlcr과 같은 효과(\n만 와도 줄 맨 앞)
            self._pending_cr = False
            self._emit("\n")
            return
        if self._pending_cr:  # 단독 \r 뒤 글자: 흐름에서는 줄을 나눈다
            self._pending_cr = False
            self._emit("\n")
        if ch == "\b":
            self._col = max(0, self._col - 1)
            return
        if ch == "\t":
            nxt = (self._col // _TAB_WIDTH + 1) * _TAB_WIDTH
            self._col = min(nxt, self._max_line - 1)
            self._emit("\t")
            return
        if ch < " " or ch == "\x7f" or "\x80" <= ch <= "\x9f":
            return  # 그 밖의 제어 문자는 버린다
        self._put(ch)
        self._emit(ch)

    def _escape(self, ch: str) -> None:
        if ch == "[":
            self._state = _CSI
            self._seq.clear()
        elif ch == "]":
            self._state = _OSC
            self._seq.clear()
        elif ch in "PX^_":
            self._state = _STRING
        elif ch in "()*+-./#%":
            self._state = _ESC_INTERMEDIATE
        elif ch == "c":  # RIS: 화면 초기화
            self._state = _GROUND
            self._erase_display(2)
            self._emit_newline()
        elif ch == "E":  # NEL
            self._state = _GROUND
            self._newline()
            self._col = 0
            self._emit_newline()
        elif ch == "M":  # RI: 한 줄 위
            self._state = _GROUND
            self._move_to(self._row - 1, self._col)
            self._emit_newline()
        else:  # 7·8(커서 저장·복원)·= 등은 버린다
            self._state = _GROUND

    def _csi(self, body: str, final: str) -> None:
        private = bool(body) and body[0] in "?<=>"
        if private or any(c in body for c in " !\"#$%&'*+,-./"):
            return  # 모드 설정 등: 화면 글자와 무관
        params = [int(p) if p.isdigit() else 0 for p in body.split(";")] if body else []

        def arg(i: int, default: int) -> int:
            if i < len(params) and params[i] > 0:
                return params[i]
            return default

        def raw(i: int) -> int:
            return params[i] if i < len(params) else 0

        if final == "A":
            self._move_to(self._row - arg(0, 1), self._col)
            self._emit_newline()
        elif final in "Be":
            self._move_to(self._row + arg(0, 1), self._col)
            self._emit_newline()
        elif final in "Ca":
            n = arg(0, 1)
            self._move_to(self._row, self._col + n)
            self._emit(" " * min(n, self._max_line))
        elif final == "D":
            self._move_to(self._row, self._col - arg(0, 1))
        elif final == "E":
            self._move_to(self._row + arg(0, 1), 0)
            self._emit_newline()
        elif final == "F":
            self._move_to(self._row - arg(0, 1), 0)
            self._emit_newline()
        elif final in "G`":
            self._move_to(self._row, arg(0, 1) - 1)
        elif final in "Hf":
            # 절대 위치: 화면 높이를 모르므로 지금 기억하는 줄의 맨 위를 1행으로 본다
            self._move_to(arg(0, 1) - 1, arg(1, 1) - 1)
            self._emit_newline()
        elif final == "d":
            self._move_to(arg(0, 1) - 1, self._col)
            self._emit_newline()
        elif final == "K":
            self._erase_line(raw(0))
        elif final == "J":
            self._erase_display(raw(0))
            self._emit_newline()
        # 그 밖(m 색, h·l 모드, r 영역, s·u 저장 등)은 화면 글자에 영향 없음으로 본다

    def _osc_end(self) -> None:
        body = "".join(self._seq)
        self._seq.clear()
        self._state = _GROUND
        if body.startswith("8;"):
            _, _, rest = body.partition(";")
            _params, _, uri = rest.partition(";")
            if uri:
                if uri not in self._links:
                    self._links.append(uri)
                self._pending_cr = False
                self._emit("\n" + uri + "\n")


def strip_ansi(text: str) -> str:
    """제어 시퀀스를 뺀 원문(``TerminalText``의 원문 흐름과 같은 규칙).

    Example:
        >>> strip_ansi("\\x1b[1mbold\\x1b[0m plain")
        'bold plain'
    """
    term = TerminalText(max_text_chars=max(1, len(text) * 2 + 16))
    term.feed(text)
    return term.text_since(0).text


__all__ = [
    "DEFAULT_MAX_LINE_CHARS",
    "DEFAULT_MAX_TEXT_CHARS",
    "DEFAULT_SCROLLBACK_LINES",
    "TerminalText",
    "TextChunk",
    "strip_ansi",
]
