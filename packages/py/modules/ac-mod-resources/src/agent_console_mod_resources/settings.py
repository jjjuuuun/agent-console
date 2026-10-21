"""mod-resources 설정(설치자 값, ``modules.options.mod-resources``)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui

DEFAULT_CONTENT_FILES: dict[str, str] = {
    "text/markdown": "content.md",
    "text/html": "content.html",
    "application/json": "content.json",
}
"""본문 형식 → 처음 저장할 본문 파일 이름(데이터)."""

DEFAULT_RESERVED_FILE_NAMES: tuple[str, ...] = (".git", "_bundle")
"""여러 파일 본문 경로에 있으면 저장 때 경고하는 이름(데이터). ``.git``은 버전 관리 폴더로
오인될 수 있고, ``_bundle``은 실행 폴더에서 항목 트리 자리로 쓰는 기본 이름이다
(노드 패키지 기본값)."""


class ResourceModuleSettings(BaseModel):
    """리소스 경로 설정."""

    model_config = ConfigDict(extra="forbid")

    types_extension: str = Field(
        title="리소스 종류 묶음 이름",
        json_schema_extra=x_ui(tier="advanced"),
        default="resource_types",
        min_length=1,
        description="서버가 읽은 플러그인 중 리소스 종류가 들어 있는 묶음 이름.",
    )
    declarative_dir: str = Field(
        title="선언형 종류 폴더",
        json_schema_extra=x_ui(tier="advanced"),
        default="resource-types",
        min_length=1,
        description="단독 실행 때 선언형 리소스 종류(*.yaml)를 읽을 폴더(워크스페이스 기준).",
    )
    content_files: dict[str, str] = Field(
        title="본문 파일 이름",
        json_schema_extra=x_ui(tier="advanced"),
        default_factory=lambda: dict(DEFAULT_CONTENT_FILES),
        description="본문 형식 → 처음 저장할 본문 파일 이름.",
    )
    default_content_file: str = Field(
        title="기본 본문 파일 이름",
        json_schema_extra=x_ui(tier="advanced"),
        default="content.txt",
        min_length=1,
        description="표에 없는 형식의 본문 파일 이름.",
    )
    reserved_file_names: list[str] = Field(
        title="경고할 파일 이름",
        json_schema_extra=x_ui(tier="advanced"),
        default_factory=lambda: list(DEFAULT_RESERVED_FILE_NAMES),
        description=(
            "여러 파일 본문 안 폴더·파일 이름이 이것과 같으면 저장은 하되 경고한다. 빈 목록이면 "
            "경고 없음."
        ),
    )


__all__ = ["DEFAULT_CONTENT_FILES", "DEFAULT_RESERVED_FILE_NAMES", "ResourceModuleSettings"]
