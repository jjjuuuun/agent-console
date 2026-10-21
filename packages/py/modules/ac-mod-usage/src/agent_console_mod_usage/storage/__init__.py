"""mod-usage의 저장소: `usage_observations`(design §3R.1.7).

- ``BRANCH``: 이 모듈의 마이그레이션 계보(``usage``, 패키지 데이터). 모듈이 켜질 때만 올라간다.
  테이블은 legacy 0002가 만들었다(변경 없음) — 계보의 첫 리비전은 기준점이다.
- ``SqliteUsageObservationRepository``: 호스트 ``DatabaseHandle.engine`` 위의 구현.
- ``InMemoryUsageObservationRepository``: 테스트용.
"""

from __future__ import annotations

from pathlib import Path

from agent_console_modkit import MigrationBranch

from .memory import InMemoryUsageObservationRepository
from .repository import SqliteUsageObservationRepository, UsageObservationRepository
from .schema import TABLE_NAME, metadata, usage_observations

BRANCH = MigrationBranch("usage", Path(__file__).parent / "migrations" / "versions")
"""모듈 서술자 ``migrations``에 넣는 계보."""

__all__ = [
    "BRANCH",
    "TABLE_NAME",
    "InMemoryUsageObservationRepository",
    "SqliteUsageObservationRepository",
    "UsageObservationRepository",
    "metadata",
    "usage_observations",
]
