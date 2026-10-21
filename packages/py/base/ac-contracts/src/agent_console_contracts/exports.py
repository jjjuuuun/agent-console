"""내보내기(X8) 계약(design §2R.7).

내보내기 형식은 플러그인(`ExporterDescriptor.id`, 임의 문자열)이다. 계약은 형식 이름·옵션 키·산출물
경로 규칙을 모른다. 옵션은 형식 디스크립터의 `config_schema`가 정의한다.
"""

from typing import Literal

from pydantic import Field

from ._base import ContractModel, JsonObject, NonEmptyStr
from .definitions import Issue

type ExportFileAction = Literal["create", "overwrite", "skip", "conflict"]
"""계획된 파일 하나의 쓰기 동작. 동작 모드(종류 id가 아님)라 고정 어휘다."""

type ExportConflictPolicy = Literal["skip", "overwrite", "fail"]
"""폴더에 쓸 때 이미 있는 파일 처리."""


class ExporterDescriptor(ContractModel):
    """내보내기 형식 디스크립터(`GET /exporters`)."""

    id: NonEmptyStr = Field(description="내보내기 형식 id(레지스트리 키).")
    title: NonEmptyStr
    description: str = ""
    config_schema: JsonObject = Field(
        default_factory=dict, description="옵션(`ExportRequest.options`)의 JSON Schema."
    )
    kinds: list[str] = Field(
        default_factory=list, description="이 형식이 내보낼 수 있는 정의 종류 이름."
    )


class ExportSelection(ContractModel):
    """내보낼 정의 하나."""

    kind: NonEmptyStr = Field(description="정의 종류 이름.")
    id: NonEmptyStr


class ExportRequest(ContractModel):
    """`POST /exports/plan`(미리보기)·`POST /exports/archive`(보관 파일) 요청.

    미리보기에 `root`를 주면 그 폴더 목적지 기준으로 `ExportFile.action`(overwrite·conflict)을
    계산한다. 없으면 보관 파일 기준이라 모두 create다. 보관 파일 요청은 `root`·`subdir`를 무시한다.
    """

    exporter: NonEmptyStr = Field(description="내보내기 형식 id.")
    items: list[ExportSelection] = Field(default_factory=list)
    options: JsonObject = Field(
        default_factory=dict, description="형식의 `config_schema`로 검증되는 옵션."
    )
    root: str | None = Field(
        default=None, description="폴더 목적지 `ExportRootInfo.id`(미리보기 충돌 계산용)."
    )
    subdir: str = Field(default="", description="루트 기준 상대 폴더. 비우면 루트 바로 아래.")


class ExportFile(ContractModel):
    """내보낼 파일 하나(내용은 담지 않는다)."""

    path: NonEmptyStr = Field(description="내보내기 루트 기준 상대 경로(`/` 구분).")
    media_type: str | None = None
    size: int = Field(ge=0, description="바이트 수.")
    action: ExportFileAction = "create"


class ExportPlan(ContractModel):
    """내보내기 미리보기 결과."""

    files: list[ExportFile] = Field(default_factory=list)
    warnings: list[Issue] = Field(default_factory=list)


class ExportRootInfo(ContractModel):
    """폴더 쓰기를 허용한 루트 하나(`GET /exports/roots`, 설치자 설정 `exports.roots`)."""

    id: NonEmptyStr
    label: str = ""
    path: str = Field(description="절대 경로(표시용).")


class ExportWriteRequest(ExportRequest):
    """`POST /exports/write` 요청. 허용 루트 아래 `subdir`에만 쓴다."""

    root: NonEmptyStr = Field(description="`ExportRootInfo.id`(필수).")
    on_conflict: ExportConflictPolicy = "fail"


class ExportResult(ContractModel):
    """`POST /exports/write` 응답. `files[].action`은 실제로 한 동작이다."""

    files: list[ExportFile] = Field(default_factory=list)
    warnings: list[Issue] = Field(default_factory=list)


__all__ = [
    "ExportConflictPolicy",
    "ExportFile",
    "ExportFileAction",
    "ExportPlan",
    "ExportRequest",
    "ExportResult",
    "ExportRootInfo",
    "ExportSelection",
    "ExportWriteRequest",
    "ExporterDescriptor",
]
