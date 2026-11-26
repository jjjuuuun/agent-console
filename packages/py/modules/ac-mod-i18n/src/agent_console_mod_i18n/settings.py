"""mod-i18n settings (installer values, ``modules.options.mod-i18n``, design §I18N.8).

The schema titles and descriptions are server original text, so they are Korean (design §I18N.2
I-7). The web shows them through the catalogs (this package ships ``locales/en.json``).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_console_contracts import x_ui
from agent_console_i18n import normalize_language

DEFAULT_LANGUAGE = "en"
"""Default of ``default_language`` and ``fallback_language`` (design §I18N.8)."""


class I18nModuleSettings(BaseModel):
    """화면 문구 묶음을 어디서 모으고 어떤 언어를 기본으로 볼지(설치자 값)."""

    model_config = ConfigDict(extra="forbid")

    default_language: str = Field(
        title="기본 언어",
        default=DEFAULT_LANGUAGE,
        description=(
            "화면 설정값과 브라우저 언어로 언어를 정하지 못했을 때 쓸 언어 코드"
            "(BCP 47, 예: en, ko)."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            example="ko",
            when="브라우저 언어와 상관없이 처음 화면을 다른 언어로 보이고 싶을 때 바꾸세요.",
        ),
    )
    fallback_language: str = Field(
        title="대체 언어",
        default=DEFAULT_LANGUAGE,
        description=(
            "고른 언어의 묶음에 없는 문구를 찾을 언어 코드. "
            "언어 목록의 완성 여부도 이 언어 묶음을 기준으로 센다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            example="en",
            when="일부만 번역한 언어의 빈 곳을 영어가 아닌 다른 언어로 채우고 싶을 때 바꾸세요.",
        ),
    )
    catalog_dirs: list[Path] = Field(
        title="사용자 문구 폴더",
        default_factory=list,
        description=(
            "언어별 문구 묶음 파일(<언어 코드>.json)을 둔 폴더 목록. 상대 경로는 설정 파일 폴더 "
            "기준이고, 패키지 묶음 위에 목록 순서대로 덮는다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            example=["./locales"],
            when=(
                "새 언어를 더하거나 기본 문구 몇 개를 바꾸고 싶을 때 폴더를 적으세요. "
                "파일을 고치면 다음 요청부터 반영됩니다."
            ),
        ),
    )
    disabled_catalogs: list[str] = Field(
        title="끌 문구 묶음",
        default_factory=list,
        description=(
            "읽지 않을 패키지 문구 묶음 이름(entry point 이름). 설정 plugins.disabled에 적은 "
            "이름도 빠진다. 뺀 묶음의 문구는 대체 언어나 원문으로 보인다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            example=["my-plugin"],
            when="어떤 플러그인의 번역이 마음에 들지 않아 원문으로 보고 싶을 때 이름을 적으세요.",
        ),
    )

    @field_validator("default_language", "fallback_language")
    @classmethod
    def _language(cls, value: str) -> str:
        return normalize_language(value)


__all__ = ["DEFAULT_LANGUAGE", "I18nModuleSettings"]
