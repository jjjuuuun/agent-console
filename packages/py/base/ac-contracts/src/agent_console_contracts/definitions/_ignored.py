"""공통 설정(`settings.yaml`)을 읽을 때 무시하는 옛 키(Python 전용, 스키마 밖).

옛 키는 읽기를 막지 않는다. 문서 모델(`DefinitionModel`)이 모르는 키로 보존하고, 읽는 쪽(모듈)은
`ignored_settings_keys`로 찾아 정보 이슈 `settings.ignored_key`(`details.key` = 키 경로)를 낸다.
필드가 아직 모델에 있는 계약과 필드를 지운 계약에서 같은 답을 낸다(속성 접근 대신 이 함수를 쓴다).
"""

from collections.abc import Mapping
from typing import Any, Final

from pydantic import BaseModel

IGNORED_SETTINGS_KEYS: Final = ("projects", "logs.projects")
"""공통 설정에서 읽고 무시하는 옛 키 경로(점으로 구분). `projects` = 옛 새 정의 범위
(`new_definition_scope`·`fallback`), `logs.projects` = 옛 로그 프로젝트 묶기(`groups`·`ungrouped`·
`git_worktrees`). 1.x 동안 읽기는 실패하지 않는다."""


def _child(node: Any, key: str) -> Any:
    """`node`의 `key` 값(없거나 null이면 None). 매핑·선언 필드·모르는 키를 모두 본다."""
    if isinstance(node, Mapping):
        return node.get(key)
    if isinstance(node, BaseModel):
        if key in type(node).model_fields:
            # 선언된 필드는 입력에 있었을 때만 센다(기본값은 "없음").
            return getattr(node, key) if key in node.model_fields_set else None
        return (node.model_extra or {}).get(key)
    return None


def ignored_settings_keys(settings: Any, *, section: str | None = None) -> list[str]:
    """공통 설정 `settings`에 들어 있는, 읽고 무시하는 옛 키 경로(`IGNORED_SETTINGS_KEYS` 순서).

    값이 null인 키는 없는 것으로 본다. 모델의 필드가 있든(모델이 읽은 값) 없든(모르는 키로 보존된
    값) 같은 답을 낸다.

    Args:
        settings: 공통 설정 문서(`WorkspaceSettings`·dict). `section`을 주면 그 섹션 값
            (예: `section="logs"`이면 `LogSettings`·dict).
        section: 이 섹션 아래 키만 본다(`settings`는 그 섹션 값). 돌려주는 경로는 늘 전체 경로다.

    Returns:
        들어 있는 옛 키 경로 목록. 없거나 `settings`가 매핑·모델이 아니면 빈 목록.

    >>> ignored_settings_keys({"projects": {"fallback": "shared"}, "logs": {}})
    ['projects']
    >>> ignored_settings_keys({"projects": {"groups": []}}, section="logs")
    ['logs.projects']
    >>> ignored_settings_keys({"logs": {"projects": None}}), ignored_settings_keys("x")
    ([], [])
    """
    prefix = f"{section}." if section else ""
    out: list[str] = []
    for path in IGNORED_SETTINGS_KEYS:
        if not path.startswith(prefix):
            continue
        node: Any = settings
        for key in path[len(prefix) :].split("."):
            node = _child(node, key)
            if node is None:
                break
        if node is not None:
            out.append(path)
    return out


__all__ = ["IGNORED_SETTINGS_KEYS", "ignored_settings_keys"]
