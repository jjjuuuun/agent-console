"""link-projects-wiki 설정(설치자 값, ``modules.options.link-projects-wiki``).

기본값은 패키지 데이터(``data/defaults.json``)에 있다. 페이지 폴더 이름(``pages_dir``)은
위키 모듈 설정 ``modules.options.mod-wiki.pages_dir``을 ``SeedSetting``으로 이어받는다
(이 연동에 값을 적지 않았을 때만). 그래서 단독 공간과 프로젝트 공간의 폴더 이름이 함께
바뀐다.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_console_contracts import x_ui
from agent_console_modkit import SeedSetting, SettingsCompat
from agent_console_store import InvalidContentPath, check_content_path

DEFAULTS_RESOURCE = "data/defaults.json"
"""설치자 옵션 기본값(패키지 데이터)."""


@cache
def _data(name: str) -> Any:
    text = (
        resources.files("agent_console_link_projects_wiki")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )
    return json.loads(text)


def package_defaults() -> dict[str, Any]:
    """설치자 옵션 기본값 사본(패키지 데이터)."""
    return json.loads(json.dumps(_data(DEFAULTS_RESOURCE)))  # type: ignore[no-any-return]


_D = package_defaults()


def check_relative_dir(value: str) -> str:
    """폴더 안 상대 경로(POSIX)인지 검사하고 끝 ``/``를 뺀 값을 돌려준다.

    >>> check_relative_dir("docs/wiki-pages/")
    'docs/wiki-pages'

    Raises:
        ValueError: 비었거나 ``..``·절대 경로·역슬래시·Windows 금지 문자가 있다.
    """
    norm = value.strip().rstrip("/")
    try:
        return check_content_path(norm)
    except InvalidContentPath as exc:
        raise ValueError(str(exc)) from None


class ProjectsWikiSettings(BaseModel):
    """프로젝트 위키 연동 설정."""

    model_config = ConfigDict(extra="forbid")

    pages_dir: str = Field(
        default=_D["pages_dir"],
        min_length=1,
        title="페이지 폴더 이름",
        description=(
            "프로젝트 구성 폴더 안에서 위키 페이지를 두는 폴더(그 아래 위키마다 폴더 하나). 적지 "
            "않으면 위키 모듈 설정의 페이지 폴더 이름을 이어받는다."
        ),
        json_schema_extra=x_ui(
            tier="advanced", example="wiki-pages", when="폴더 이름을 바꾸고 싶을 때 정하세요."
        ),
    )
    index_dir: str = Field(
        default=_D["index_dir"],
        min_length=1,
        title="검색 색인 폴더 이름",
        description=(
            "프로젝트 구성 폴더의 상태 폴더(커밋하지 않는 캐시) 안에서 위키 검색 색인 파일을 두는 "
            "폴더. 지워도 다시 만든다."
        ),
        json_schema_extra=x_ui(
            tier="advanced", example="wiki-index", when="폴더 이름을 바꾸고 싶을 때 정하세요."
        ),
    )
    reserved_dirs: list[str] = Field(
        default_factory=list,
        title="페이지 폴더 금지 경로",
        description=(
            "프로젝트 폴더 기준 상대 경로. 페이지 폴더가 이 경로와 겹치면 위키를 열지 않는다. 구성 "
            "폴더의 상태·세션 폴더와 정의 종류 폴더는 적지 않아도 늘 막는다."
        ),
        json_schema_extra=x_ui(tier="advanced"),
    )

    @field_validator("pages_dir", "index_dir")
    @classmethod
    def _relative(cls, value: str) -> str:
        return check_relative_dir(value)


SETTINGS_COMPAT = SettingsCompat(
    seeds=(SeedSetting("pages_dir", "modules.options.mod-wiki.pages_dir"),),
)
"""위키 모듈의 ``pages_dir``을 이 연동 ``pages_dir``의 기본값으로 이어받는다(값이 없을 때만)."""

__all__ = [
    "DEFAULTS_RESOURCE",
    "SETTINGS_COMPAT",
    "ProjectsWikiSettings",
    "check_relative_dir",
    "package_defaults",
]
