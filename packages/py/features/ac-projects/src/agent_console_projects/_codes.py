"""이 패키지 규칙이 내는 프로젝트 이슈 코드(계약 문서 상수의 별칭, 다시 정의하지 않는다)."""

from __future__ import annotations

from typing import Final

from agent_console_contracts import KnownIssueCodes

__all__ = ["CODE_REFERENCES_UNAVAILABLE", "CODE_UNKNOWN"]

CODE_UNKNOWN: Final = KnownIssueCodes.PROJECT_UNKNOWN
"""없는 프로젝트를 가리킨다(`project.unknown`). 예: 실행의 프로젝트 층이 등록되지 않은 id."""

CODE_REFERENCES_UNAVAILABLE: Final = KnownIssueCodes.PROJECT_REFERENCES_UNAVAILABLE
"""참조 추출이 주입되지 않아 참조를 보지 못했다(info, `project.references_unavailable`). 예: 정의
모듈이 꺼짐 — 복사 계획의 참조 닫힘·거꾸로 참조."""
