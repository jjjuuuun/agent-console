"""이벤트 `raw` 정제: JSON화 → 비밀 가리기 → 크기 제한(R10.2).

엔진도 저장 전에 `SecretResolver.redact`를 적용하지만, 백엔드는 자기가 아는 비밀(설정 `env` 값 등)과
흔한 비밀 형식을 먼저 가린다.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from agent_console_runtime import REDACTED

DEFAULT_MAX_RAW_CHARS = 16_000
"""`raw` 하나의 최대 JSON 길이. 넘치면 잘라서 미리보기만 남긴다."""

DEFAULT_SECRET_KEY_PATTERN = (
    r"(?i)(secret|passw(?:or)?d|credential|private[_-]?key|api[_-]?key|authorization|"
    r"cookie|token$)"
)
"""값을 통째로 가릴 키 이름(대소문자 무시, 포함 검색). `token`은 접미만 본다 —
`GITHUB_TOKEN`·`access_token`은 가리고 `input_tokens`·`output_tokens` 같은 사용량 키는 보존한다."""

DEFAULT_SECRET_VALUE_PATTERNS: tuple[str, ...] = (
    r"sk-ant-[A-Za-z0-9_\-]{8,}",
    r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]{8,}=*",
    r"\bgh[pousr]_[A-Za-z0-9]{20,}",
    r"\bgithub_pat_[A-Za-z0-9_]{20,}",
    r"\bxox[abposr]-[A-Za-z0-9-]{10,}",
    r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
)
"""문자열 안에서 가릴 비밀 형식(Anthropic 키, Bearer, GitHub, Slack, AWS 액세스 키, PEM 개인 키)."""

_MIN_SECRET_CHARS = 4


class RawSanitizer:
    """공급자 원시 메시지를 저장 가능한 JSON 값으로 정제한다.

    Args:
        secrets: 문자열에서 찾아 가릴 값(설정 `env` 값 등). 4자 미만은 무시.
        redact: 추가 가리기 함수(예: `SecretResolver.redact`).
        max_chars: JSON 길이 상한.
        key_pattern: 값을 통째로 가릴 키 이름 정규식.
        value_patterns: 문자열 안에서 가릴 정규식들.
    """

    def __init__(
        self,
        *,
        secrets: Iterable[str] = (),
        redact: Callable[[Any], Any] | None = None,
        max_chars: int = DEFAULT_MAX_RAW_CHARS,
        key_pattern: str = DEFAULT_SECRET_KEY_PATTERN,
        value_patterns: Iterable[str] = DEFAULT_SECRET_VALUE_PATTERNS,
    ) -> None:
        self._secrets = sorted(
            {s for s in secrets if len(s) >= _MIN_SECRET_CHARS}, key=len, reverse=True
        )
        self._redact = redact
        self._max = max_chars
        self._key = re.compile(key_pattern)
        self._values = [re.compile(p) for p in value_patterns]

    def scrub(self, value: Any) -> Any:
        """JSON화 후 비밀을 가린 사본(크기 제한 없음). 페이로드 값에도 쓴다."""
        cleaned = self._mask(to_jsonable(value))
        return self._redact(cleaned) if self._redact is not None else cleaned

    def __call__(self, value: Any) -> Any:
        """`scrub` + 크기 제한. 넘치면 `{"truncated": true, "chars": n, "preview": …}`."""
        cleaned = self.scrub(value)
        text = json.dumps(cleaned, ensure_ascii=False, default=str)
        if len(text) <= self._max:
            return cleaned
        return {"truncated": True, "chars": len(text), "preview": text[: self._max]}

    def mask_text(self, text: str) -> str:
        """문자열 하나에서 비밀 값·형식을 가린다."""
        for secret in self._secrets:
            if secret in text:
                text = text.replace(secret, REDACTED)
        for pattern in self._values:
            text = pattern.sub(REDACTED, text)
        return text

    def _mask(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.mask_text(value)
        if isinstance(value, dict):
            return {
                k: (REDACTED if self._key.search(str(k)) and v not in (None, "") else self._mask(v))
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [self._mask(v) for v in value]
        return value


def to_jsonable(value: Any) -> Any:
    """dataclass·Mapping·시퀀스를 JSON 값으로 바꾼다.

    데이터클래스는 `_type`에 클래스 이름을 남긴다.
    """
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        out: dict[str, Any] = {"_type": type(value).__name__}
        for f in dataclasses.fields(value):
            out[f.name] = to_jsonable(getattr(value, f.name))
        return out
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [to_jsonable(v) for v in value]
    return repr(value)
