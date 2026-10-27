"""받은 실행 묶음(`ResourceBundle`)의 짧은 요약 — E2E에서 리소스 전달을 확인하는 용도.

칸 값 자체는 싣지 않는다(칸 이름·항목 수·출처 ref만). 그래도 `secret://` 참조 모양이 섞이면 가린다.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from typing import Any

from agent_console_contracts import ResourceBundle

EMPTY_BUNDLE = "bundle: -"
"""묶음이 없거나 비었을 때의 요약."""

_SECRET_REF = re.compile(r"secret://[^\s,;\[\]()]*")
_SECRET_MASK = "secret://***"


def mask_secret_refs(text: str) -> str:
    """`secret://…` 참조를 `secret://***`로 가린다."""
    return _SECRET_REF.sub(_SECRET_MASK, text)


def bundle_summary(bundle: ResourceBundle | None, accepted: Collection[str]) -> str:
    """묶음 요약 한 줄.

    형식: ``bundle: <칸>=<항목 수> [<출처 ref>, …]; …; ignored=[<칸>, …]``. 칸은 이름순이고,
    `accepted`(백엔드가 받는 칸)에 없는 칸은 `ignored`에 이름만 적는다.

    Args:
        bundle: 요청의 실행 묶음(없으면 `EMPTY_BUNDLE`).
        accepted: 받는 칸 이름(`capabilities.resource_slots`).

    Returns:
        비밀 참조를 가린 요약 문자열.
    """
    if bundle is None or not bundle.slots:
        return EMPTY_BUNDLE
    parts: list[str] = []
    ignored: list[str] = []
    for slot in sorted(bundle.slots):
        if slot not in accepted:
            ignored.append(slot)
            continue
        refs = list(dict.fromkeys(src.ref for src in bundle.sources.get(slot, [])))
        part = f"{slot}={_count(bundle.slots[slot])}"
        if refs:
            part += f" [{', '.join(refs)}]"
        parts.append(part)
    text = "bundle: " + ("; ".join(parts) if parts else "-")
    if ignored:
        text += f"; ignored=[{', '.join(ignored)}]"
    return mask_secret_refs(text)


def _count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, list | tuple | dict | set):
        return len(value)
    return 1
