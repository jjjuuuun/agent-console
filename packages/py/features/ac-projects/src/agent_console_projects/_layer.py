"""프로젝트 층 값(design §UX-P.3): 공통 바로 아래에 끼우는 `AgentSettings` 모양 dict."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from agent_console_contracts import AgentSettings, Project

__all__ = ["project_layer_value"]

_FIELDS = frozenset(AgentSettings.model_fields)


def project_layer_value(project: Project | Mapping[str, Any]) -> dict[str, Any]:
    """프로젝트 층 값: `settings`의 **지정한 필드만** + `working_directory`.

    - `settings`는 지정한 필드만 읽는다(모델 기본값은 층 값이 아니다, `ac-teams` 층 규칙과 같음).
      `AgentSettings`에 없는 키는 뺀다.
    - 프로젝트 `working_directory`가 있으면 `settings.working_directory`보다 우선한다
      (전용 필드가 화면의 "작업 폴더"다).
    - 아무것도 없으면 빈 dict(이 층은 아무것도 바꾸지 않는다).

    >>> project_layer_value({"id": "app", "name": "App", "working_directory": "/w/app",
    ...                      "settings": {"model": "m1"}})
    {'model': 'm1', 'working_directory': '/w/app'}
    """
    if isinstance(project, Project):
        settings: dict[str, Any] = (
            project.settings.model_dump(mode="json", exclude_unset=True)
            if project.settings is not None
            else {}
        )
        wd = project.working_directory
    else:
        raw = project.get("settings")
        settings = copy.deepcopy(dict(raw)) if isinstance(raw, Mapping) else {}
        raw_wd = project.get("working_directory")
        wd = raw_wd if isinstance(raw_wd, str) else None
    value = {k: v for k, v in settings.items() if k in _FIELDS}
    if wd:
        value["working_directory"] = wd
    return value
