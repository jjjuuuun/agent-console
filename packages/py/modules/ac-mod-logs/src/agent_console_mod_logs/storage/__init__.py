"""mod-logs의 저장 계층: 마이그레이션 계보 `logs`와 색인 열기(design §4R.5·§3R.1.7).

- ``BRANCH``: 이 모듈의 마이그레이션 계보(``logs``, 패키지 데이터 ``migrations/versions``).
  버전 테이블은 ``alembic_version_logs``. 모듈이 켜질 때만 올라간다. ``MODULE_OWNED_TABLES``에는
  넣지 않는다(F-2): 이 테이블들은 처음부터 이 계보가 만든다.
- ``open_log_storage``: 호스트 DB 핸들(기본) 또는 별도 SQLite 파일(``index_path``)을 색인으로 연다.
  DB가 아예 없으면 메모리 색인이다(``kind == "memory"``, 모듈이 ``logs.storage_memory`` 경고).

색인 구현(``SqliteLogIndex``)과 테이블 정의는 ``agent_console_logs.sqlite``에 있다.
"""

from pathlib import Path

from agent_console_modkit import MigrationBranch

BRANCH = MigrationBranch("logs", Path(__file__).parent / "migrations" / "versions")
"""모듈 서술자 ``migrations``에 넣는 계보."""

from ._open import LogStorage, open_log_storage  # noqa: E402

__all__ = ["BRANCH", "LogStorage", "open_log_storage"]
