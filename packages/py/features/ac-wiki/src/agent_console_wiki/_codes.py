"""ac-wiki가 내는 이슈·사유 코드의 짧은 이름(계약 `KnownIssueCodes`의 별칭).

FU.14에서 계약 후보로 두었던 코드가 계약 0.14.11(`common` 1.16.0)에 들어갔다. 값은 계약 상수
그대로이고(`wiki.*`, 바뀌지 않음), 이 이름은 이미 쓰던 코드가 깨지지 않게 남긴다.
"""

from __future__ import annotations

from typing import Final

from agent_console_contracts.constants import KnownIssueCodes

__all__ = ["WikiIssueCodes"]


class WikiIssueCodes:
    """ac-wiki 이슈·사유 코드 — 계약 `KnownIssueCodes`의 별칭이다(문서 상수)."""

    UNKNOWN_TITLE_SOURCE: Final = KnownIssueCodes.WIKI_UNKNOWN_TITLE_SOURCE
    """= `KnownIssueCodes.WIKI_UNKNOWN_TITLE_SOURCE`(`wiki.unknown_title_source`). 문법
    `title_sources`에 모르는 값이 있어 그 값만 건너뛰었다(warning, 문법 컴파일·규칙 검사).
    `Issue.path` = `/title_sources/<i>`, `details.value`."""
    REDACTED_CONTENT: Final = KnownIssueCodes.WIKI_REDACTED_CONTENT
    """= `KnownIssueCodes.WIKI_REDACTED_CONTENT`(`wiki.redacted_content`). 쓸 본문에 읽을 때 가린
    비밀 자리 표시가 새로 들어 있어 쓰지 않았다(도구·`compose_write` 사유 코드, 쓰면 실제 비밀이
    가린 표시로 바뀐다). 도구 이벤트 상태는 `secret_rejected`. `details.lines`(새 본문 줄 번호,
    값 없음)."""
