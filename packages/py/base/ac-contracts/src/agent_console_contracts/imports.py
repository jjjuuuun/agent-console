"""외부 설정(`~/.claude`, 프로젝트 `.claude/` 등)에서 정의를 **복사해** 가져오기(design §R11).

REST: design §R9.5.

원본은 읽기만 한다. 흐름: 출처 목록 → 후보 스캔(미리보기) → 고른 항목 가져오기.
출처 id는 문자열이며 목록은 서버가 준다(계약에 고정 목록 없음).
"""

from pydantic import Field

from ._base import ContractModel, NonEmptyStr, Slug
from .definitions import AppliedItemInfo, ConflictPolicy


class ImportSourceDescriptor(ContractModel):
    """`GET /resources/import/sources` 항목: 가져올 수 있는 출처 디스크립터 하나."""

    id: NonEmptyStr = Field(description="출처 id(서버가 정함).")
    title: NonEmptyStr
    description: str = ""
    path: str | None = Field(default=None, description="원본 위치(표시용).")
    available: bool = Field(default=True, description="지금 읽을 수 있는지.")


class ImportPreviewRequest(ContractModel):
    """`POST /resources/import/preview` 요청. 원본을 읽기만 하고 아무것도 쓰지 않는다."""

    source: NonEmptyStr


class ImportWarning(ContractModel):
    """후보 하나의 경고(예: 비밀 의심). 값은 싣지 않고 위치만 싣는다."""

    code: NonEmptyStr
    message: str
    keys: list[str] = Field(default_factory=list, description="문제가 된 키·경로(값 아님).")


class ImportCandidate(ContractModel):
    """가져올 수 있는 항목 하나."""

    id: NonEmptyStr = Field(description="이 미리보기 안의 후보 키(가져오기 요청에 쓴다).")
    path: str = Field(description="원본 경로(표시용).")
    kind: NonEmptyStr = Field(description="만들 정의 종류 이름(저장소 kind).")
    resource_type: str | None = Field(default=None, description="리소스면 리소스 종류 id.")
    name: str
    suggested_id: NonEmptyStr = Field(description="워크스페이스에 쓸 제안 id.")
    size: int | None = Field(default=None, ge=0, description="바이트.")
    content_hash: str | None = None
    conflict: bool = Field(default=False, description="같은 id의 정의가 이미 있음.")
    warnings: list[ImportWarning] = Field(default_factory=list)


class ImportPreview(ContractModel):
    """`POST /resources/import/preview` 응답."""

    source: NonEmptyStr
    root: str | None = Field(default=None, description="스캔한 원본 위치(표시용).")
    candidates: list[ImportCandidate] = Field(default_factory=list)
    warnings: list[ImportWarning] = Field(
        default_factory=list,
        description="후보가 되지 못한 항목의 경고(예: 링크라서 건너뜀 `import.skipped_link`, "
        "keys = 원본 경로). 가져오기를 막지 않는다.",
    )


class ImportSelection(ContractModel):
    """가져올 후보 하나와 충돌 처리."""

    candidate_id: NonEmptyStr
    target_id: str | None = Field(default=None, description="쓸 id. 비우면 제안 id.")
    on_conflict: ConflictPolicy = "rename"


class ImportRequest(ContractModel):
    """`POST /resources/import` 요청. 후보는 서버가 다시 스캔해 확인한다."""

    source: NonEmptyStr
    items: list[ImportSelection] = Field(default_factory=list)
    project: Slug | None = Field(
        default=None,
        description="만든 정의에 찍을 프로젝트 id(0.8.0). 생략 = 공용(지금과 같음).",
    )


class ImportResult(ContractModel):
    """`POST /resources/import` 응답."""

    source: NonEmptyStr
    items: list[AppliedItemInfo] = Field(default_factory=list)


__all__ = [
    "ImportCandidate",
    "ImportPreview",
    "ImportPreviewRequest",
    "ImportRequest",
    "ImportResult",
    "ImportSelection",
    "ImportSourceDescriptor",
    "ImportWarning",
]
