"""옛 프로젝트 전용 정의 해석(design §PI.8 K33-9): 라이브러리 정의의 `project` 필드.

파일은 그대로 두고 **읽을 때** "옛 프로젝트 전용 구성 N개"로 보인다. [정리]는 복사 계획(원본 =
라이브러리, 대상 = 그 프로젝트, 항목 = `legacy_items`)을 `copy_plan`에 넘겨 만든다(같은 함수를
해석·계획에 함께 써서 둘이 갈라지지 않게, design §PI.13 위험 3). 원본을 남길 때는
`without_scope_field`로 `project` 필드만 지운다.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from typing import Any, Final

from agent_console_contracts import DefinitionKey

from ._model import ScopedDefinition

__all__ = ["LEGACY_SCOPE_FIELD", "legacy_counts", "legacy_items", "without_scope_field"]

LEGACY_SCOPE_FIELD: Final = "project"
"""옛 정의 범위 필드 이름(계약 0.8 `Agent`·`Graph`·`Resource.project`)."""


def legacy_items(defs: Iterable[ScopedDefinition], project_id: str) -> list[DefinitionKey]:
    """`project` 값이 `project_id`인 옛 프로젝트 전용 정의(입력 순서, 종류 이름을 모름).

    >>> defs = [ScopedDefinition("agent", "a", project="app"), ScopedDefinition("graph", "g"),
    ...         ScopedDefinition("resource", "r", project="web")]
    >>> [(k.kind, k.id) for k in legacy_items(defs, "app")]
    [('agent', 'a')]
    """
    return [d.to_key() for d in defs if d.project == project_id]


def legacy_counts(defs: Iterable[ScopedDefinition]) -> dict[str, int]:
    """프로젝트 id → 옛 전용 정의 개수(공용 제외). 없는 프로젝트를 가리키는 것도 센다.

    >>> legacy_counts([ScopedDefinition("agent", "a", project="app"),
    ...                ScopedDefinition("graph", "g", project="app"),
    ...                ScopedDefinition("agent", "b")])
    {'app': 2}
    """
    out: dict[str, int] = {}
    for d in defs:
        if d.project is not None:
            out[d.project] = out.get(d.project, 0) + 1
    return out


def without_scope_field(document: Mapping[str, Any]) -> dict[str, Any]:
    """`project` 필드를 뺀 새 문서(입력은 바꾸지 않음). [정리]에서 원본을 남길 때 쓴다.

    >>> without_scope_field({"id": "a", "project": "app", "name": "A"})
    {'id': 'a', 'name': 'A'}
    """
    doc = copy.deepcopy(dict(document))
    doc.pop(LEGACY_SCOPE_FIELD, None)
    return doc
