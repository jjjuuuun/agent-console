"""커밋된 TS 계약 생성물(`packages/ts/lib/contracts/schema`)이 지금 계약과 같은지(저장소 통합 검사).

3R.3에서 ac-contracts 테스트에서 옮겼다(패키지는 저장소의 다른 폴더를 보지 않는다, P5).
"""

from __future__ import annotations

from pathlib import Path

from agent_console_contracts import check_schemas

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_committed_schema_is_current() -> None:
    committed = REPO_ROOT / "packages" / "ts" / "lib" / "contracts" / "schema"
    assert check_schemas(committed) == [], "uv run poe contracts 로 다시 생성하세요"
