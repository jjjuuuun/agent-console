"""선언형 종류의 안전 치환(design §5.4 `fill`과 같은 규칙).

구현은 기반 패키지 `agent_console_text_template`에 있다(6R.4에서 추출). 이 모듈은 옛 import 경로를
그대로 두기 위한 다시 내보내기다(공개 API·동작 불변).
"""

from __future__ import annotations

from agent_console_text_template import DEFAULT_MAX_RENDER_CHARS, fill_value, render_template

__all__ = ["DEFAULT_MAX_RENDER_CHARS", "fill_value", "render_template"]
