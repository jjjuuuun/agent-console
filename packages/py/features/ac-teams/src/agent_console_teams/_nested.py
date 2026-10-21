"""중첩 팀(design §5R.7)의 순수 도우미: 팀 구성 조회 함수 모양, 조회, 팀 층 덮어쓰기.

중첩 팀 노드는 다른 팀 구성을 **자식 Run**으로 실행한다. 이 모듈은 노드 타입 이름을 모른다
(노드가 팀 구성을 묶는지는 디스크립터 `binds.kind == TeamConventions.team_kind`로 정한다).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from agent_console_contracts import Graph, GraphSettings

__all__ = ["TeamLookup", "find_team", "merge_overrides", "with_team_settings"]

type TeamLookup = Callable[[str, str | None], Graph | None]
"""(팀 구성 id, 고정 버전 또는 None = 지금 최신) → 팀 구성. 없으면 None(`LookupError`도 "없음")."""


def find_team(lookup: TeamLookup, team_id: str, version: str | None = None) -> Graph | None:
    """`lookup`으로 팀 구성을 찾는다. 없거나 `LookupError`면 None."""
    try:
        return lookup(team_id, version)
    except LookupError:
        return None


def merge_overrides(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """`override`가 지정한 값으로 `base`를 덮어쓴 새 dict.

    둘 다 객체인 값은 재귀로 합치고, 그 밖의 값(목록 포함)은 `override` 값으로 바꾼다.
    """
    out = dict(base)
    for key, value in override.items():
        current = out.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            out[key] = merge_overrides(current, value)
        else:
            out[key] = value
    return out


def with_team_settings(graph: Graph, override: Mapping[str, Any] | None) -> Graph:
    """자식 팀 구성의 팀 층(`graph.settings`)을 `override`로 덮어쓴 사본(중첩 팀 노드의 `settings`).

    지정한 값만 바꾼다(`merge_overrides`). `override`가 비었으면 `graph`를 그대로 돌려준다.
    덮어쓴 그래프는 원래 버전 해시와 다르다(자식 Run의 `graph_version`은 덮어쓴 그래프 기준).

    Raises:
        pydantic.ValidationError: 합친 값이 팀 구성 층 설정(`GraphSettings`)에 맞지 않을 때.
    """
    if not override:
        return graph
    base = graph.settings.model_dump(exclude_unset=True) if graph.settings is not None else {}
    merged = GraphSettings.model_validate(merge_overrides(base, override))
    return graph.model_copy(update={"settings": merged})
