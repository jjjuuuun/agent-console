"""로그에서 비밀성 쿼리 값(WS `?token=` 등)을 가리는 필터.

uvicorn은 `access_log=False`여도 WS 연결 줄(`"WebSocket /ws?token=…" [accepted]`)을 `uvicorn.error`
로거에 쿼리째 남긴다. 이 필터를 uvicorn 로거에 걸어 메시지와 인자 양쪽에서 값을 가린다.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Sequence
from typing import Any

from agent_console_modkit._options import OPTIONS_MASK

SENSITIVE_QUERY_PARAMS: tuple[str, ...] = (
    "token",
    "access_token",
    "api_key",
    "apikey",
    "key",
    "secret",
    "password",
    "auth",
)
"""값을 가릴 쿼리 이름(대소문자 무시)."""

UVICORN_LOGGERS: tuple[str, ...] = ("uvicorn", "uvicorn.error", "uvicorn.access")
REDACTED = OPTIONS_MASK
"""가림 문자열(modkit 하나, 코어 ``OPTIONS_MASK``와 같은 값)."""


class QueryRedactingFilter(logging.Filter):
    """로그 메시지·인자에서 `?name=값`·`&name=값`의 값과 알려진 비밀 값을 `[REDACTED]`로 바꾼다.

    Args:
        params: 가릴 쿼리 이름.
        values: 문자열 그대로 가릴 값(예: 로컬 API 토큰). 빈 값은 무시한다.
    """

    def __init__(
        self, params: Iterable[str] = SENSITIVE_QUERY_PARAMS, values: Iterable[str] = ()
    ) -> None:
        super().__init__()
        names = "|".join(re.escape(p) for p in params)
        self._query = re.compile(rf"([?&](?:{names})=)[^&\s\"'#]*", re.IGNORECASE)
        self._values = sorted({v for v in values if v}, key=len, reverse=True)

    def redact(self, text: str) -> str:
        """`text`에서 비밀성 쿼리 값과 알려진 값을 가린 문자열."""
        out = self._query.sub(rf"\g<1>{REDACTED}", text)
        for value in self._values:
            out = out.replace(value, REDACTED)
        return out

    def _arg(self, value: Any) -> Any:
        return self.redact(value) if isinstance(value, str) else value

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(self._arg(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: self._arg(v) for k, v in record.args.items()}
        return True


def install_log_redaction(
    log_filter: logging.Filter, logger_names: Sequence[str] = UVICORN_LOGGERS
) -> None:
    """필터를 로거들에 건다(로거 필터는 그 로거에서 직접 남긴 기록에 적용된다)."""
    for name in logger_names:
        logger = logging.getLogger(name)
        if log_filter not in logger.filters:
            logger.addFilter(log_filter)


__all__ = [
    "REDACTED",
    "SENSITIVE_QUERY_PARAMS",
    "UVICORN_LOGGERS",
    "QueryRedactingFilter",
    "install_log_redaction",
]
