"""리소스(정의 데이터), 첨부, 실행 묶음(design §R12).

리소스 종류(`Resource.type`)와 실행 묶음 칸 이름(`ResourceBundle.slots`의 키)은 문자열이다.
종류 목록·칸 목록은 계약에 없다(종류는 X14 디스크립터, 칸은 종류가 정한다).
"""

from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field

from ._base import (
    ContractModel,
    DefinitionModel,
    JsonObject,
    NonEmptyStr,
    OmitWhenUnsetModel,
    Slug,
)
from .common import UiHints, x_ui

type AttachmentMode = Literal["add", "replace", "remove"]
"""첨부 방식(design §R12.1). add = 더함, replace = 같은 슬롯 키의 위 층 첨부를 바꿈,
remove = 위 층의 같은 리소스 첨부를 뺌."""


class ResourceContentRef(ContractModel):
    """문서형 리소스의 본문 파일(정의 파일 옆 폴더 기준 상대 경로)."""

    model_config = ConfigDict(extra="allow", title="본문")

    file: NonEmptyStr = Field(
        title="본문 파일",
        description="리소스 폴더 안의 본문 파일 경로입니다.",
        json_schema_extra=x_ui(tier="advanced", example="content.md"),
    )
    media_type: str | None = Field(
        default=None,
        title="형식",
        description="본문의 파일 형식(MIME)입니다.",
        json_schema_extra=x_ui(tier="advanced", example="text/markdown"),
    )


class Resource(OmitWhenUnsetModel):
    """리소스입니다. 에이전트에 붙여 쓰는 지침·파일·MCP(외부 도구 서버) 등을 담습니다."""

    # 리소스 정의(`<workspace>/resources/<id>.yaml`).

    model_config = ConfigDict(title="리소스")

    kind: Literal["resource"] = "resource"
    id: Slug = Field(
        title="id",
        description="가리킬 때 쓰는 고유 이름입니다. 파일 이름으로도 쓰며 영문·숫자·-·_만 씁니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    schema_version: int = Field(
        default=1,
        title="형식 버전",
        description="파일 형식 번호입니다. 직접 바꾸지 않습니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    type: NonEmptyStr = Field(
        title="종류",
        description=(
            "지침·파일·MCP 서버(외부 도구 서버)처럼 리소스의 종류입니다. 종류마다 입력 항목이 "
            "다릅니다."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            when=("만들 때 한 번, 지침이면 instruction·외부 도구면 mcp-server처럼 고르세요."),
        ),
    )
    name: NonEmptyStr = Field(
        title="이름",
        description="리소스를 부르는 이름입니다. 에이전트에 붙일 때 이 이름으로 고릅니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="에이전트에 붙일 때 찾기 쉬운 이름으로 바꾸고 싶을 때 바꾸세요.",
            example="리뷰 규칙",
        ),
    )
    description: str = Field(
        default="",
        title="설명",
        description="이 리소스가 무엇인지 적습니다. 목록에 함께 보입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="목록에서 이 리소스가 무엇인지 알리고 싶을 때 적으세요.",
            example="팀 공통 코드 리뷰 기준",
        ),
    )
    labels: list[str] = Field(
        default_factory=list,
        title="라벨",
        description="찾기·거르기에 쓰는 꼬리표입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    config: JsonObject = Field(
        default_factory=dict,
        title="설정",
        description="종류가 정한 설정입니다(예: 외부 도구 서버를 띄울 명령).",
        json_schema_extra=x_ui(
            tier="basic", when="종류가 요구하는 값(예: 서버를 띄울 명령)을 넣거나 고칠 때 바꾸세요."
        ),
    )
    content: ResourceContentRef | None = Field(
        default=None,
        title="본문",
        description="지침·규칙 같은 문서형 종류의 본문입니다. 본문은 따로 저장됩니다.",
        json_schema_extra=x_ui(tier="basic", when="지침이나 규칙의 내용을 고칠 때 바꾸세요."),
    )
    attributes: JsonObject = Field(
        default_factory=dict,
        title="기타 속성",
        description="다른 도구가 읽는 자유 속성입니다. 보통은 비워 둡니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    # 0.8.0(design §UX-P.4). 생략 = 공용. 지정하지 않으면 직렬화하지 않는다(정의 해시 안정).
    project: Slug | None = Field(
        default=None,
        title="프로젝트",
        description="이 정의가 속한 프로젝트입니다. 비우면 공용이라 모든 프로젝트에서 보입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="이 리소스를 특정 프로젝트에서만 보이게 하고 싶을 때 고르세요.",
            example=None,
        ),
    )

    _OMIT_WHEN_UNSET: ClassVar[tuple[tuple[str, ...], ...]] = (("project",),)


class ResourceAttachment(DefinitionModel):
    """리소스 붙이기 하나입니다. 공통 설정·팀·에이전트·노드마다 목록으로 둡니다."""

    model_config = ConfigDict(title="리소스 첨부")

    ref: Slug = Field(
        title="리소스",
        description="붙일 리소스입니다.",
        json_schema_extra=x_ui(tier="basic", when="다른 리소스를 붙이고 싶을 때 고르세요."),
    )
    mode: AttachmentMode = Field(
        default="add",
        title="방식",
        description=(
            "더하기(add), 공통·팀 설정에서 붙인 같은 자리 바꾸기(replace), 빼기(remove)입니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="공통·팀 설정에서 붙인 리소스를 여기서만 빼거나 바꾸고 싶을 때 바꾸세요.",
        ),
    )
    config_override: JsonObject | None = Field(
        default=None,
        title="설정 덮어쓰기",
        description="이 첨부에서만 바꿀 리소스 설정 값입니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="같은 리소스를 이 자리에서만 조금 다르게 쓰고 싶을 때 바꾸세요."
        ),
    )


class BundleSource(ContractModel):
    """실행 묶음 칸 하나에 기여한 첨부의 출처."""

    ref: NonEmptyStr = Field(description="리소스 id.")
    layer: str | None = Field(default=None, description="첨부가 들어온 설정 층 id.")
    mode: AttachmentMode = "add"
    resource_type: str | None = Field(default=None, description="리소스 종류 id.")


class ResourceBundle(ContractModel):
    """실행 묶음. 칸 이름 → 값. 칸 이름은 문자열이며 플러그인이 새 칸을 만들 수 있다.

    알려진 칸 이름은 `KnownResourceSlots`(문서 상수)에 있다. 백엔드는
    `BackendCapabilities.resource_slots`로 받을 칸을 선언한다.
    """

    slots: dict[str, Any] = Field(default_factory=dict)
    sources: dict[str, list[BundleSource]] = Field(default_factory=dict)


class ResourceFile(ContractModel):
    """여러 파일 본문(`ResourceContentSpec.multi_file`) 리소스의 파일 하나."""

    path: NonEmptyStr = Field(description="리소스 본문 폴더 기준 상대 경로(`/` 구분).")
    media_type: str | None = None
    size: int = Field(ge=0, description="바이트 수.")
    sha256: NonEmptyStr = Field(description="내용 해시(16진 소문자).")


class ResourceSummary(ContractModel):
    """`GET /resources` 목록 항목."""

    id: NonEmptyStr
    type: NonEmptyStr
    name: str
    description: str = ""
    labels: list[str] = Field(default_factory=list)
    version_hash: NonEmptyStr
    saved_at: float | None = None
    has_content: bool = False
    usage_count: int | None = Field(
        default=None, ge=0, description="붙어 있는 곳의 수(계산하지 않았으면 null)."
    )
    project: str | None = Field(
        default=None,
        description="정의의 프로젝트 id(0.8.0). null = 공용. 웹이 이 값으로 목록을 거른다.",
    )


# ---------------------------------------------------------------- 리소스 종류 디스크립터(X14)


class ResourceContentSpec(ContractModel):
    """문서형 리소스 종류의 본문 형식."""

    media_types: list[str] = Field(default_factory=list, description="허용 MIME 형식.")
    editor: str = Field(
        default="text", description="편집기 이름(예: text, markdown, html, json). 모르면 text."
    )
    multi_file: bool = Field(
        default=False,
        description="본문이 여러 파일(리소스 폴더 아래 상대 경로들)인지.",
    )


class ResourceTypeDescriptor(ContractModel):
    """리소스 종류 디스크립터. 플러그인 또는 선언형 데이터로 들어온다."""

    id: NonEmptyStr
    version: int = 1
    title: NonEmptyStr
    description: str = ""
    config_schema: JsonObject = Field(default_factory=dict)
    ui_schema: JsonObject = Field(default_factory=dict)
    content: ResourceContentSpec | None = Field(default=None, description="문서형이면 본문 형식.")
    slot_key: str | None = Field(
        default=None, description="첨부 방식 replace가 같은 자리를 판단하는 config 키."
    )
    combine: str = Field(
        default="append", description="같은 칸 여러 첨부의 합치기 전략 이름(병합 전략 표)."
    )
    contributes: list[str] = Field(default_factory=list, description="채우는 실행 묶음 칸 이름.")
    declarative: bool = Field(
        default=False, description="코드 없이 선언형 데이터로 등록된 종류인지."
    )
    ui_hints: UiHints | None = None


__all__ = [
    "AttachmentMode",
    "BundleSource",
    "Resource",
    "ResourceAttachment",
    "ResourceBundle",
    "ResourceContentRef",
    "ResourceContentSpec",
    "ResourceFile",
    "ResourceSummary",
    "ResourceTypeDescriptor",
]
