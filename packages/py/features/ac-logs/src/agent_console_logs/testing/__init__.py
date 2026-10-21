"""테스트 지원: 메모리 색인, 색인 계약 테스트 묶음, 원본 읽기 전용 확인 도구.

- `MemoryLogIndex`: 질의 의미의 기준 구현(DB 없는 실행에도 쓴다).
- `LogIndexContractTests`: 다른 색인 구현(SQLite 등)이 상속해 같은 의미를 확인한다.
- `RecordingOpen`·`no_writes_under`·`tree_digest`: 출처 테스트에서 쓰기 감시·해시 비교.
"""

from ._contract import LogIndexContractTests, make_record
from ._guard import RecordingOpen, WriteAttempt, no_writes_under, tree_digest
from ._memory import MemoryLogIndex

__all__ = [
    "LogIndexContractTests",
    "MemoryLogIndex",
    "RecordingOpen",
    "WriteAttempt",
    "make_record",
    "no_writes_under",
    "tree_digest",
]
