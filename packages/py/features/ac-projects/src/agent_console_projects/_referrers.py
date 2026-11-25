"""거꾸로 참조(FU.13): 한 공간에서 정의 하나를 쓰는 다른 정의 찾기.

삭제 확인 창의 "이 구성을 쓰는 구성"처럼 정의 종류 이름을 모르는 쪽이 쓴다. 참조 추출
(`References`, X25 — 팀 구성 → 에이전트·리소스, 종류 기여의 `references` 등)을 주입받아 공간의
문서를 하나씩 보고, 대상 `(종류, id)`를 돌려주는 문서를 모은다. 종류마다 참조 필드를 알지 않는다.

순수 함수다. 저장소를 모르고 `((종류, id), 문서)` 목록만 받는다. 참조 추출이 없으면 문서를 읽지
않고(목록을 소비하지 않는다) "검사하지 못함"과 정보 이슈 `project.references_unavailable`을 낸다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from agent_console_contracts import Issue, KnownIssueCodes

from ._model import DefinitionId, References

__all__ = [
    "DEFAULT_REFERRER_MESSAGES",
    "REFERRERS_UNAVAILABLE_MESSAGE",
    "ReferrerScan",
    "find_referrers",
]

REFERRERS_UNAVAILABLE_MESSAGE: Final = "project.referrers_unavailable"
"""문구 표 키: 참조 추출이 없어 쓰는 곳을 찾지 못했을 때(이슈 코드는
`project.references_unavailable`). 기본 문구는 `DEFAULT_REFERRER_MESSAGES`, `messages=`로 바꾼다."""

DEFAULT_REFERRER_MESSAGES: Mapping[str, str] = {
    REFERRERS_UNAVAILABLE_MESSAGE: (
        "참조를 알 수 없어 이 항목을 쓰는 구성을 확인하지 못했습니다. 지우면 쓰던 구성이 "
        "실행 전에 막힐 수 있습니다."
    ),
}
"""거꾸로 참조 기본 문구(키 → 문구). 복사 문구 표와 같은 설정(`messages=`)으로 바꾼다."""


@dataclass(frozen=True, slots=True)
class ReferrerScan:
    """`find_referrers` 결과.

    Attributes:
        keys: 대상을 쓰는 정의의 `(종류, id)`(문서 순서, 중복·대상 자신 제외).
        checked: 참조 추출이 있어 검사했다. False면 `keys`가 비어도 "쓰는 곳 없음"이 아니다.
        warnings: 검사 이슈(참조 추출 없음 = info `project.references_unavailable`).
    """

    keys: tuple[DefinitionId, ...]
    checked: bool
    warnings: tuple[Issue, ...] = ()


def find_referrers(
    target: DefinitionId,
    documents: Iterable[tuple[DefinitionId, Mapping[str, Any]]],
    references: References | None,
    *,
    messages: Mapping[str, str] | None = None,
) -> ReferrerScan:
    """``target``을 참조하는 정의를 찾는다.

    Args:
        target: 찾을 정의 `(종류, id)`.
        documents: 같은 공간의 `((종류, id), 문서)`. 지연 목록이어도 된다(참조 추출이 없으면
            소비하지 않는다).
        references: 참조 추출(주입). None이면 검사하지 않는다.
        messages: 문구 바꾸기(키 `REFERRERS_UNAVAILABLE_MESSAGE`).

    Returns:
        `ReferrerScan`. 참조 추출이 한 문서에서 예외를 내면 그 문서만 건너뛴다.

    >>> docs = [(("graph", "t"), {"uses": ["a"]}), (("graph", "u"), {"uses": ["b"]}),
    ...         (("agent", "a"), {"uses": ["a"]})]
    >>> def refs(kind, doc):
    ...     return [("agent", x) for x in doc.get("uses", [])]
    >>> find_referrers(("agent", "a"), docs, refs).keys
    (('graph', 't'),)
    >>> scan = find_referrers(("agent", "a"), docs, None)
    >>> scan.checked, [w.code for w in scan.warnings]
    (False, ['project.references_unavailable'])
    """
    if references is None:
        text = (messages or {}).get(REFERRERS_UNAVAILABLE_MESSAGE) or DEFAULT_REFERRER_MESSAGES[
            REFERRERS_UNAVAILABLE_MESSAGE
        ]
        issue = Issue(
            severity="info",
            code=KnownIssueCodes.PROJECT_REFERENCES_UNAVAILABLE,
            message=text,
            details={"kind": target[0], "id": target[1]},
        )
        return ReferrerScan(keys=(), checked=False, warnings=(issue,))
    found: list[DefinitionId] = []
    seen: set[DefinitionId] = set()
    for raw, document in documents:
        key = (raw[0], raw[1])
        if key == target or key in seen:
            continue
        try:
            refs = list(references(key[0], document))
        except Exception:  # 문서 하나의 추출 실패가 검사 전체를 막지 않게
            continue
        if any((kind, ref_id) == target for kind, ref_id in refs):
            seen.add(key)
            found.append(key)
    return ReferrerScan(keys=tuple(found), checked=True)
