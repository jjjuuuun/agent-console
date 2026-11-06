"""DB 핸들 프로토콜과 마이그레이션 계보 선언(design §3R.1.7, modularity §3.4).

modkit은 DB 라이브러리를 모른다. 호스트가 구현(예: ``agent_console_store.SqliteDatabase``)을
``BaseServices.database``로 주입하고, 모듈은 ``ModuleDescriptor.migrations``로 자기 계보를 선언한다.
``assemble``이 켜진 모듈의 계보만 ``database.upgrade``로 올린다.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class MigrationBranch:
    """모듈이 소유한 마이그레이션 계보(패키지 데이터 폴더).

    Args:
        name: 계보 이름(보통 모듈 짧은 이름, 예: ``"usage"``). 식별자여야 하고 ``legacy``는 못 쓴다.
        versions: 리비전 스크립트 폴더. 패키지 데이터로 배포되는 경로
            (``Path(__file__).parent / "migrations" / "versions"``)를 준다.
        scopes: 이 계보를 올릴 DB 범위(열린 문자열 목록, X39). 기본 ``("app",)`` = 앱 DB에만.
            호스트는 ``"app"``이 든 계보만 앱 DB에 올리고, ``"project"`` 같은 다른 범위는 그 범위의
            DB를 여는 쪽(예: 프로젝트 기록 DB 연동 모듈)이 ``ModuleContext.active_migrations``로
            읽어 올린다. 코드에 계보 이름 목록은 없다.
    """

    name: str
    versions: Path
    scopes: tuple[str, ...] = ("app",)

    def __post_init__(self) -> None:
        if not self.scopes or any(not s for s in self.scopes):
            raise ValueError("scopes는 비어 있지 않은 이름의 목록이어야 합니다")


@runtime_checkable
class DatabaseHandle(Protocol):
    """공용 DB 핸들(호스트가 만들어 모듈에 준다). 모듈은 엔진을 직접 만들지 않는다."""

    @property
    def engine(self) -> Any:
        """SQLAlchemy ``Engine``(모듈 저장소가 쓴다)."""
        ...

    def upgrade(self, branches: Iterable[MigrationBranch] = ()) -> None:
        """기반(legacy)을 올린 뒤 ``branches``를 각자 최신까지 올린다(멱등)."""
        ...

    def close(self) -> None:
        """연결을 모두 닫는다."""
        ...


__all__ = ["DatabaseHandle", "MigrationBranch"]
