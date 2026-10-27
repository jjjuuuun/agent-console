"""메모리 연산 오류. 모든 오류는 계약 코드(`code`)를 갖고, 본문·찾은 비밀 값을 싣지 않는다.

REST 층은 `code`로 상태 코드를 고르고(`ErrorCodes`·`ERROR_STATUS`), 도구 묶음은 `code`를 도구 결과
사유 코드와 이벤트 `status`로 옮긴다.
"""

from __future__ import annotations

from collections.abc import Sequence

from agent_console_contracts.constants import ErrorCodes, KnownIssueCodes
from agent_console_contracts.memory import MemorySecretField, MemorySecretRejectedDetails


class MemoryStoreError(Exception):
    """메모리 연산 오류의 공통 부모.

    Attributes:
        code: 계약 오류·사유 코드(예: `memory.not_found`).
    """

    code: str = ErrorCodes.BAD_REQUEST

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidKeyError(MemoryStoreError, ValueError):
    """키·태그·범위가 글자 규칙에 맞지 않다(`memory.invalid_key`)."""

    code = ErrorCodes.MEMORY_INVALID_KEY


class EntryNotFoundError(MemoryStoreError, LookupError):
    """항목·버전이 없다(`memory.not_found`)."""

    code = KnownIssueCodes.MEMORY_NOT_FOUND


class EntryExistsError(MemoryStoreError):
    """만들기·옮기기 대상 범위에 같은 키의 항목이 이미 있다(`already_exists`, REST 409).

    Attributes:
        entry_id: 이미 있는 항목 id.
    """

    code = ErrorCodes.ALREADY_EXISTS

    def __init__(self, message: str, *, entry_id: str) -> None:
        super().__init__(message)
        self.entry_id = entry_id


class VersionConflictError(MemoryStoreError):
    """`if_version`이 현재 버전과 다르다(`memory.conflict`, REST 412).

    Attributes:
        current_version: 지금 버전(도구 결과로 알린다).
        entry_id: 항목 id.
    """

    code = KnownIssueCodes.MEMORY_CONFLICT

    def __init__(self, message: str, *, entry_id: str, current_version: int) -> None:
        super().__init__(message)
        self.entry_id = entry_id
        self.current_version = current_version


class TooLargeError(MemoryStoreError):
    """크기·개수 한도를 넘었다(`memory.too_large`).

    Attributes:
        limit: 넘은 한도 이름(`MemoryLimits` 필드 이름, 예 `max_entry_bytes`).
        value: 한도 값.
    """

    code = ErrorCodes.MEMORY_TOO_LARGE

    def __init__(self, message: str, *, limit: str, value: int) -> None:
        super().__init__(message)
        self.limit = limit
        self.value = value


class SecretRejectedError(MemoryStoreError):
    """비밀 의심 값이 있어 쓰기를 거부했다(`memory.secret_rejected`). 찾은 값은 싣지 않는다.

    Attributes:
        field: 의심 값이 나온 필드(`content`·`key`·`tags`).
        rules: 맞은 규칙 id(값 없음).
    """

    code = ErrorCodes.MEMORY_SECRET_REJECTED

    def __init__(self, field: MemorySecretField, rules: Sequence[str]) -> None:
        super().__init__(f"비밀로 보이는 값이 있어 쓰지 않았다(필드 {field})")
        self.field: MemorySecretField = field
        self.rules = list(rules)

    def details(self) -> MemorySecretRejectedDetails:
        """REST 오류 `details`(값·조각 없음)."""
        return MemorySecretRejectedDetails(field=self.field, rules=self.rules)
