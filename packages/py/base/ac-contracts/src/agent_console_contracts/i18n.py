"""화면 문구 묶음(다국어) 계약(design §I18N.3·§I18N.7, 0.16.0에서 1.0.0, 0.16.1에서 1.1.0 —
`I18nInfo.source_language`, §I18N.13 I-18).

서버(`mod-i18n`)는 패키지 묶음(entry point `agent_console.message_catalogs`)과 사용자 폴더 묶음을
언어별로 병합해 준다. 서버는 요청 언어를 모르고 응답을 번역하지 않는다 — 웹이 서버 원문(T)·코드(C)를
이 묶음으로 바꿔 보인다(design §I18N.2 I-4). 언어 목록·언어 이름은 계약에 없다(데이터다).

REST: `GET /api/v1/i18n` → `I18nInfo`, `GET /api/v1/i18n/{lang}` → `MessageCatalog`(묶음이 없는
언어는 404 `i18n.unknown_language`).
"""

from pydantic import Field

from ._base import ContractModel, JsonObject, NonEmptyStr


class LanguageInfo(ContractModel):
    """묶음이 있는 언어 하나(`I18nInfo.languages` 항목)."""

    code: NonEmptyStr = Field(
        description="언어 코드(BCP 47, 서버가 정규화한 표기 — 예: `en`, `ko`, `zh-Hant-TW`)."
    )
    sources: list[str] = Field(
        description=(
            "이 언어에 기여한 묶음 출처 이름(병합 순서, 뒤가 이김). 패키지 묶음은 entry point "
            "이름, 사용자 폴더 묶음은 서버가 정한 폴더 출처 이름이다."
        )
    )
    complete: bool = Field(
        description=(
            "기준 언어(`I18nInfo.fallback_language`) 묶음의 키를 빈 값 없이 다 가진다. "
            "false면 빠진 문구는 대체 언어 → 서버 원문 순으로 보인다."
        )
    )
    missing: int | None = Field(
        default=None,
        ge=0,
        description=(
            "기준 언어 대비 빠졌거나 빈 문구 수(`text`·`codes` 항목과 `ns` 잎을 센다). "
            "null = 서버가 세지 않음(그때는 `complete`만 본다). `complete`가 true면 0이다."
        ),
    )


class I18nInfo(ContractModel):
    """`GET /i18n` 응답: 서버가 줄 수 있는 언어와 언어 해석 기본값."""

    languages: list[LanguageInfo] = Field(
        description="묶음이 하나라도 있는 언어(코드 순). 화면 선택지 = 화면이 가진 묶음과 이 목록."
    )
    default_language: NonEmptyStr = Field(
        description=(
            "설정값·브라우저 언어로 정하지 못했을 때 쓸 언어(설정 `mod-i18n.default_language`)."
        )
    )
    fallback_language: NonEmptyStr = Field(
        description=(
            "고른 언어 묶음에 없는 문구를 찾을 대체 언어(설정 `mod-i18n.fallback_language`). "
            "`LanguageInfo.complete`의 기준이다."
        )
    )
    source_language: str | None = Field(
        default=None,
        description=(
            "서버 원문 문구의 언어(설정 `mod-i18n.source_language`, 1.1.0). 화면은 원문 키 "
            "조회를 이 언어에서 멈춘다(그 언어 묶음까지 본다). null = 모름(옛 서버) — 대체 언어 "
            "사슬 전체를 본다."
        ),
    )


class MessageCatalog(ContractModel):
    """`GET /i18n/{lang}` 응답: 한 언어의 병합한 문구 묶음(§I18N.3 Python 묶음 형식 + 언어)."""

    language: NonEmptyStr = Field(
        description=(
            "묶음 언어 코드. 요청한 언어에 맞춘 값이다(예: `en-US`를 요청하고 `en` 묶음만 있으면 "
            "`en`)."
        )
    )
    text: dict[str, str] = Field(
        description="원문 키 → 번역(서버 고정 문구 — 스키마 제목·설명, 서술자 이름 등)."
    )
    codes: dict[str, str] = Field(
        description=(
            "오류·이슈 코드 → 문구 틀(`{name}` 자리표시자는 그 오류·이슈의 `details` 값으로 "
            "채운다)."
        )
    )
    ns: dict[str, JsonObject] = Field(
        description="웹 네임스페이스 → 중첩 문구 객체(잎 = 문자열). 웹 앱·라이브러리 묶음을 덮는다."
    )


__all__ = ["I18nInfo", "LanguageInfo", "MessageCatalog"]
