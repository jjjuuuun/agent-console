"""계약 세션 참조 → 엔진 세션 참조 변환(대화 턴의 세션 이어 쓰기, R4.6)."""

from __future__ import annotations

from collections.abc import Mapping

from agent_console_contracts import SessionRef as ContractSessionRef

from ._interfaces import SessionRef

__all__ = ["session_refs"]


def session_refs(mapping: Mapping[str, ContractSessionRef]) -> dict[str, SessionRef]:
    """노드 id → 계약 `SessionRef`(대화 저장본)를 노드 id → 엔진 `SessionRef`로 바꾼다.

    결과는 노드 서비스 `SESSIONS`(ac-nodes-core) 값으로 넘긴다.
    `data`는 복사한다(원본과 공유 안 함).
    """
    return {
        node_id: SessionRef(backend=ref.backend, session_id=ref.session_id, data=dict(ref.data))
        for node_id, ref in mapping.items()
    }
