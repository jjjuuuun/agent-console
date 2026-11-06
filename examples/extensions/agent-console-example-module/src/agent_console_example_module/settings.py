"""설정 두 층: 설치자 옵션(``modules.options.mod-example-notes``)과 사용자 설정 섹션.

- 설치자 옵션 ``NotesModuleSettings``: 서버를 띄우는 사람이 정한다(경로·종류 이름·한도). 서버
  설정 파일 ``modules.options.mod-example-notes`` 또는 명령행 ``--example-notes-max``
  (``SETTINGS_COMPAT``).
  설정 화면은 이 스키마(제목·설명·``x-ui``)로 읽기 전용 표를 그린다.
- 사용자 설정 ``NotesUserSettings``: 앱 사용자가 워크스페이스 설정(``settings.yaml``)의 섹션
  (기본 이름 ``example_notes``)에 적는다. 서버를 다시 띄우지 않아도 다음 요청부터 반영된다. 형식이
  틀리면 기본값을 쓰고 서버 경고(``server.warnings``)로 알린다.

기본값은 패키지 데이터(``data/defaults.json``) 한 곳에 있다.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from functools import cache
from importlib import resources
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_console_contracts import Issue, x_ui
from agent_console_modkit import FlagSetting, SettingsCompat

DEFAULTS_RESOURCE = "data/defaults.json"
"""기본값 파일(패키지 데이터)."""

SETTINGS_INVALID = "example_notes.settings_invalid"
"""사용자 설정 섹션 형식 문제의 이슈 코드(이 모듈의 접두 — 계약을 고치지 않는다)."""


@cache
def _data() -> dict[str, Any]:
    text = (
        resources.files("agent_console_example_module")
        .joinpath(DEFAULTS_RESOURCE)
        .read_text(encoding="utf-8")
    )
    loaded: dict[str, Any] = json.loads(text)
    return loaded


def package_defaults() -> dict[str, Any]:
    """기본값 사본(패키지 데이터)."""
    return copy.deepcopy(_data())


_D = package_defaults()
_U = _D["user"]


class NotesModuleSettings(BaseModel):
    """노트 기능의 경로·이름·한도(설치자 값)."""

    model_config = ConfigDict(extra="forbid")

    route: str = Field(
        default=_D["route"],
        pattern=r"^/[a-z0-9][a-z0-9\-/]*$",
        title="노트 API 경로",
        description=(
            "노트 REST가 붙는 경로(API 접두 뒤). 바꾸면 이 경로를 쓰는 화면·스크립트도 바꿔야 한다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            example="/example-notes",
            when="다른 모듈의 경로와 겹칠 때만 바꾸세요.",
        ),
    )
    template_kind: str = Field(
        default=_D["template_kind"],
        min_length=1,
        title="노트 틀 정의 종류 이름",
        description="노트 틀을 저장하는 정의 종류의 이름. 바꾸면 이미 있는 틀을 찾지 못한다.",
        json_schema_extra=x_ui(
            tier="advanced",
            example="example-note-template",
            when="다른 기능의 정의 종류 이름과 겹칠 때만 바꾸세요.",
        ),
    )
    template_dir: str = Field(
        default=_D["template_dir"],
        min_length=1,
        title="노트 틀 폴더 이름",
        description="워크스페이스 안에서 노트 틀 파일을 두는 폴더.",
        json_schema_extra=x_ui(
            tier="advanced",
            example="example-note-templates",
            when="노트 틀 폴더 이름을 바꾸고 싶을 때 정하세요.",
        ),
    )
    user_section: str = Field(
        default=_D["user_section"],
        min_length=1,
        title="사용자 설정 섹션 이름",
        description="워크스페이스 설정에서 이 기능의 사용자 설정을 읽는 섹션 이름.",
        json_schema_extra=x_ui(
            tier="advanced",
            example="example_notes",
            when="다른 기능의 설정 섹션 이름과 겹칠 때만 바꾸세요.",
        ),
    )
    records_space_prefix: str = Field(
        default=_D["records_space_prefix"],
        min_length=1,
        title="프로젝트 기록 공간 접두",
        description="프로젝트 노트를 둘 기록 DB 공간 이름의 앞부분(뒤에 프로젝트 id가 붙는다).",
        json_schema_extra=x_ui(
            tier="advanced",
            example="project:",
            when="프로젝트 기록 연동이 다른 공간 이름을 쓸 때만 바꾸세요.",
        ),
    )
    max_notes: int = Field(
        default=_D["max_notes"],
        ge=1,
        title="남길 노트 수",
        description=(
            "공간(앱 또는 프로젝트)마다 남길 최대 노트 수. 넘으면 가장 오래된 노트부터 지운다."
        ),
        json_schema_extra=x_ui(
            tier="basic", unit="개", when="노트를 더 오래 남기고 싶을 때 늘리세요."
        ),
    )
    max_text_chars: int = Field(
        default=_D["max_text_chars"],
        ge=1,
        title="노트 길이 상한",
        description="노트 하나의 최대 글자 수. 넘으면 저장하지 않고 거부한다.",
        json_schema_extra=x_ui(tier="advanced", unit="자", when="긴 노트를 적어야 할 때 늘리세요."),
    )


class NotesUserSettings(BaseModel):
    """노트 목록을 보는 방식(사용자 값, 워크스페이스 설정 섹션)."""

    model_config = ConfigDict(extra="forbid")

    newest_first: bool = Field(
        default=_U["newest_first"],
        title="최신 노트 먼저",
        description="켜면 목록에서 최근에 적은 노트가 앞에 온다. 끄면 적은 순서대로 보인다.",
        json_schema_extra=x_ui(tier="basic", when="오래된 노트부터 읽고 싶을 때 끄세요."),
    )
    list_limit: int = Field(
        default=_U["list_limit"],
        ge=1,
        title="목록에 보일 노트 수",
        description="목록 요청 한 번에 돌려줄 최대 노트 수.",
        json_schema_extra=x_ui(
            tier="basic", unit="개", when="목록에서 더 많은 노트를 한 번에 보고 싶을 때 늘리세요."
        ),
    )


SETTINGS_COMPAT = SettingsCompat(
    flags=(
        FlagSetting(
            "example-notes-max",
            ("max_notes",),
            help="노트 예제: 공간마다 남길 최대 노트 수",
            metavar="N",
        ),
    ),
)
"""호스트 설정 호환 선언.

명령행 ``--example-notes-max N`` → ``modules.options.mod-example-notes.max_notes``.
``agent-console serve --help``에 이 옵션이 보인다(서버는 모듈 이름을 모르고 선언을 모아 붙인다).
"""


def section_of(document: Any, key: str) -> Any:
    """워크스페이스 설정(계약 모델 또는 매핑)에서 섹션 원문을 꺼낸다. 없으면 None.

    계약 ``WorkspaceSettings``는 모르는 최상위 키를 ``model_extra``에 보존한다.
    """
    if document is None:
        return None
    if isinstance(document, Mapping):
        return document.get(key)
    extra = getattr(document, "model_extra", None)
    if isinstance(extra, Mapping) and key in extra:
        return extra[key]
    return getattr(document, key, None)


def parse_user_settings(raw: Any, *, section: str) -> tuple[NotesUserSettings, list[Issue]]:
    """사용자 설정 섹션 원문 → (값, 형식 문제). 틀리면 기본값과 이슈를 돌려준다(예외 없음).

    >>> parse_user_settings({"list_limit": 3}, section="example_notes")[0].list_limit
    3
    >>> value, issues = parse_user_settings({"list_limit": 0}, section="example_notes")
    >>> value.list_limit == NotesUserSettings().list_limit, issues[0].path
    (True, '/example_notes/list_limit')
    """
    if raw is None:
        return NotesUserSettings(), []
    try:
        return NotesUserSettings.model_validate(raw), []
    except ValidationError as exc:
        issues = []
        for error in exc.errors():
            loc = "/".join(str(p) for p in error.get("loc", ()))
            issues.append(
                Issue(
                    severity="warning",
                    code=SETTINGS_INVALID,
                    message=(
                        f"사용자 설정 {section} 섹션을 읽지 못해 기본값을 씁니다: {error['msg']}"
                    ),
                    path=f"/{section}/{loc}" if loc else f"/{section}",
                )
            )
        return NotesUserSettings(), issues


__all__ = [
    "SETTINGS_COMPAT",
    "SETTINGS_INVALID",
    "NotesModuleSettings",
    "NotesUserSettings",
    "package_defaults",
    "parse_user_settings",
    "section_of",
]
