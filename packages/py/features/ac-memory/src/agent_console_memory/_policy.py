"""쓰기 정책: 한도(설치자)·비밀 검사(주입)·버전 보관 수. 저장소 구현이 모두 같은 검사를 거치게 한다.

`prepare_write`는 키 규칙 → 비밀 검사(키·태그·본문) → 크기 한도 순으로 보고, 저장할 본문·태그와
바이트 수·해시를 돌려준다. 저장소 구현(메모리·SQLite·사용자 구현)은 쓰기 전에 이것을 부른다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from agent_console_contracts.memory import MemorySecretField, MemorySecretPolicy
from agent_console_secret_rules import SecretRules, default_rules

from ._errors import SecretRejectedError, TooLargeError
from ._keys import check_key, check_tags


@dataclass(frozen=True, slots=True)
class MemoryLimits:
    """크기·개수 한도(설치자 설정 `modules.options.mod-memory.*`의 값, design §5.7R.8).

    Attributes:
        max_entry_bytes: 본문 하나의 최대 UTF-8 바이트(기본 64 KiB).
        max_entries_per_scope: 범위 하나의 최대 항목 수(지우지 않은 것, 기본 5,000).
        max_total_bytes: 저장소 전체 본문 바이트 합(지우지 않은 것, 기본 256 MiB).
        max_key_chars: 키 최대 글자 수(기본 256).
        max_tags: 항목당 태그 수(기본 32).
        max_tag_chars: 태그 최대 글자 수(기본 64).
        preview_chars: 목록 미리보기 글자 수(기본 200).
    """

    max_entry_bytes: int = 64 * 1024
    max_entries_per_scope: int = 5_000
    max_total_bytes: int = 256 * 1024 * 1024
    max_key_chars: int = 256
    max_tags: int = 32
    max_tag_chars: int = 64
    preview_chars: int = 200


@runtime_checkable
class SecretScanner(Protocol):
    """비밀 의심 판정기(주입). 값은 돌려주지 않는다."""

    def find(self, text: str) -> list[str]:
        """텍스트 안 비밀 의심이 있으면 맞은 규칙 id 목록(없으면 빈 목록)."""
        ...

    def redact(self, text: str) -> str:
        """의심 부분을 가린 텍스트."""
        ...


@dataclass(frozen=True, slots=True)
class SecretRulesScanner:
    """`ac-secret-rules` 규칙으로 판정한다(기본 규칙 + 사용자 규칙은 `SecretRules.with_extra`)."""

    rules: SecretRules = field(default_factory=default_rules)

    def find(self, text: str) -> list[str]:
        """맞은 판정 이유(`value_pattern`·`timeout` 등). 값은 싣지 않는다."""
        return sorted({finding.reason for finding in self.rules.find_suspected(text)})

    def redact(self, text: str) -> str:
        """의심 부분을 가림 문자열로 바꾼다."""
        return self.rules.redact_suspected(text)


@dataclass(frozen=True, slots=True)
class MemorySecretGuard:
    """쓰기 비밀 검사: 키·태그·본문을 본다. `reject`(기본)는 거부, `redact`는 본문·태그를 가린다.

    키에서 의심 값이 나오면 방식과 상관없이 거부한다(키는 항목의 이름이라 가리면 뜻이 바뀐다).
    `allow`(검사 끔)는 두지 않는다(design §5.7R.8).
    """

    scanner: SecretScanner = field(default_factory=SecretRulesScanner)
    mode: MemorySecretPolicy = "reject"

    def apply(self, key: str, content: str, tags: Sequence[str]) -> tuple[str, list[str]]:
        """검사한 뒤 저장할 (본문, 태그)를 돌려준다.

        Raises:
            SecretRejectedError: 거부할 때(필드·규칙 id만 담는다).
        """
        found = self.scanner.find(key)
        if found:
            raise SecretRejectedError("key", found)
        out_tags: list[str] = []
        for tag in tags:
            hits = self.scanner.find(tag)
            if hits and self.mode == "reject":
                raise SecretRejectedError("tags", hits)
            out_tags.append(self.scanner.redact(tag) if hits else tag)
        hits = self.scanner.find(content)
        if hits:
            if self.mode == "reject":
                raise SecretRejectedError("content", hits)
            content = self.scanner.redact(content)
        return content, out_tags

    def preview(self, text: str) -> str:
        """미리보기용 가림(목록 `preview`)."""
        return self.scanner.redact(text)


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    """저장소 쓰기 정책 묶음.

    Attributes:
        limits: 한도.
        secrets: 비밀 검사. 기본은 `ac-secret-rules` 기본 규칙 + `reject`.
        max_versions_per_entry: 항목당 버전 보관 수(사용자 설정, 기본 50). 넘으면 첫 버전을 남기고
            오래된 것부터 지운다.
    """

    limits: MemoryLimits = field(default_factory=MemoryLimits)
    secrets: MemorySecretGuard = field(default_factory=MemorySecretGuard)
    max_versions_per_entry: int = 50


@dataclass(frozen=True, slots=True)
class PreparedWrite:
    """검사를 통과한 쓰기 값."""

    content: str
    tags: list[str]
    bytes: int
    sha256: str


def content_digest(content: str) -> tuple[int, str]:
    """본문 (UTF-8 바이트 수, sha256 16진수).

    >>> content_digest("")[0]
    0
    """
    raw = content.encode("utf-8")
    return len(raw), hashlib.sha256(raw).hexdigest()


def prepare_write(
    policy: MemoryPolicy, key: str, content: str, tags: Sequence[str]
) -> PreparedWrite:
    """키 규칙 → 태그 규칙 → 비밀 검사 → 본문 크기 한도를 본다.

    Raises:
        InvalidKeyError: 키·태그 규칙 위반.
        SecretRejectedError: 비밀 의심(거부 방식이거나 키).
        TooLargeError: 본문이 `max_entry_bytes`를 넘음(가린 뒤 크기 기준).
    """
    limits = policy.limits
    check_key(key, max_chars=limits.max_key_chars)
    clean_tags = check_tags(tags, max_tags=limits.max_tags, max_chars=limits.max_tag_chars)
    content, clean_tags = policy.secrets.apply(key, content, clean_tags)
    size, digest = content_digest(content)
    if size > limits.max_entry_bytes:
        raise TooLargeError(
            f"본문이 {limits.max_entry_bytes}바이트를 넘는다",
            limit="max_entry_bytes",
            value=limits.max_entry_bytes,
        )
    return PreparedWrite(content=content, tags=clean_tags, bytes=size, sha256=digest)


def check_secret_field(guard: MemorySecretGuard, field_name: MemorySecretField, text: str) -> None:
    """한 필드만 거부 검사(옮기기의 새 키 등). 의심이면 `SecretRejectedError`."""
    hits = guard.scanner.find(text)
    if hits:
        raise SecretRejectedError(field_name, hits)
