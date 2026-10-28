"""mod-memory 설치자 설정(``modules.options.mod-memory``, design §5.7R.6·§5.7R.8).

범위 종류·비밀 처리·버전 보관 수·정리 규칙은 사용자 데이터(워크스페이스 설정 ``memory`` 섹션, 계약
``MemorySettings``)라 여기 없다. 설치자 값은 저장 위치·정리 주기·크기 한도만 둔다. 한도 기본값은
``ac-memory``의 데이터클래스 기본값을 그대로 쓴다(숫자를 두 곳에 두지 않는다).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui
from agent_console_memory import MemoryLimits, MemoryTransferLimits

_LIMITS = MemoryLimits()
_TRANSFER = MemoryTransferLimits()


class MemoryModuleSettings(BaseModel):
    """메모리 저장 위치·정리 주기·한도(설치자 값)."""

    model_config = ConfigDict(extra="forbid")

    store_path: Path | None = Field(
        default=None,
        title="메모리 파일",
        description=(
            "메모리를 둘 별도 SQLite 파일. 비우면 서버 DB를 쓴다. 상대 경로는 설정 파일 폴더 기준."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            example="state/memory.db",
            when="메모리를 서버 DB와 따로 백업하거나 옮기고 싶을 때 정하세요.",
        ),
    )
    retention_interval_seconds: float = Field(
        default=3600,
        ge=0,
        title="정리 주기",
        description="저장된 정리 규칙을 자동으로 적용하는 간격. 0이면 자동 정리를 하지 않는다.",
        json_schema_extra=x_ui(
            tier="basic",
            unit="초",
            when="자동 정리를 끄거나 더 자주 돌리고 싶을 때 바꾸세요.",
        ),
    )
    full_text_search: bool = Field(
        default=True,
        title="전문 검색 사용",
        description=(
            "SQLite 전문 검색(FTS5 trigram)으로 찾는다. 끄거나 SQLite에 없으면 단순 포함 검색이다."
        ),
        json_schema_extra=x_ui(
            tier="advanced", when="전문 검색 색인이 너무 커서 파일 크기를 줄이고 싶을 때 끄세요."
        ),
    )
    busy_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        title="쓰기 대기 시간",
        description="다른 쓰기가 DB를 잡고 있을 때 다시 시도하며 기다리는 최대 시간.",
        json_schema_extra=x_ui(
            tier="advanced", unit="초", when="동시 쓰기가 많아 바쁨 오류가 날 때 늘리세요."
        ),
    )
    max_entry_bytes: int = Field(
        default=_LIMITS.max_entry_bytes,
        ge=1,
        title="기록 하나 최대 크기",
        description="기록 본문 하나의 최대 UTF-8 바이트. 넘으면 쓰기를 거부한다.",
        json_schema_extra=x_ui(
            tier="advanced",
            unit="바이트",
            group="limits",
            when="긴 문서를 메모리에 남겨야 할 때 늘리세요.",
        ),
    )
    max_entries_per_scope: int = Field(
        default=_LIMITS.max_entries_per_scope,
        ge=1,
        title="범위당 최대 기록 수",
        description="범위 하나에 둘 수 있는 기록 수(지운 것 제외). 넘으면 새 기록을 거부한다.",
        json_schema_extra=x_ui(
            tier="advanced",
            unit="개",
            group="limits",
            when="한 팀·프로젝트에 기록이 아주 많이 쌓일 때 늘리세요.",
        ),
    )
    max_total_bytes: int = Field(
        default=_LIMITS.max_total_bytes,
        ge=1,
        title="전체 최대 크기",
        description="저장소 전체 본문 바이트 합(지운 것 제외). 넘으면 쓰기를 거부한다.",
        json_schema_extra=x_ui(
            tier="advanced",
            unit="바이트",
            group="limits",
            when="디스크 사용량을 더 엄격하게 막거나 늘리고 싶을 때 바꾸세요.",
        ),
    )
    max_key_chars: int = Field(
        default=_LIMITS.max_key_chars,
        ge=1,
        title="키 최대 글자 수",
        description="기록 키(경로 모양 이름)의 최대 글자 수.",
        json_schema_extra=x_ui(tier="advanced", unit="자", group="limits"),
    )
    max_tags: int = Field(
        default=_LIMITS.max_tags,
        ge=0,
        title="기록당 최대 태그 수",
        description="기록 하나에 붙일 수 있는 태그 수.",
        json_schema_extra=x_ui(tier="advanced", unit="개", group="limits"),
    )
    max_tag_chars: int = Field(
        default=_LIMITS.max_tag_chars,
        ge=1,
        title="태그 최대 글자 수",
        description="태그 하나의 최대 글자 수.",
        json_schema_extra=x_ui(tier="advanced", unit="자", group="limits"),
    )
    preview_chars: int = Field(
        default=_LIMITS.preview_chars,
        ge=0,
        title="미리보기 글자 수",
        description="목록에 보이는 본문 앞부분 글자 수(비밀 의심 값은 가린 뒤 자른다).",
        json_schema_extra=x_ui(tier="advanced", unit="자", group="view"),
    )
    max_page_size: int = Field(
        default=200,
        ge=1,
        title="목록 한 쪽 최대 수",
        description="기록 목록 요청 한 번에 돌려주는 최대 기록 수(요청의 limit 상한).",
        json_schema_extra=x_ui(tier="advanced", unit="개", group="view"),
    )
    max_tag_list: int = Field(
        default=500,
        ge=1,
        title="태그 목록 최대 수",
        description="태그 목록 요청이 돌려주는 최대 태그 수. 넘으면 잘렸다고 알린다.",
        json_schema_extra=x_ui(tier="advanced", unit="개", group="view"),
    )
    max_search_results: int = Field(
        default=20,
        ge=1,
        title="에이전트 검색 결과 최대 수",
        description="에이전트 메모리 검색 도구 한 번이 돌려주는 최대 기록 수.",
        json_schema_extra=x_ui(
            tier="advanced",
            unit="개",
            group="tools",
            when="에이전트가 한 번에 더 많은 기록을 훑어야 할 때 늘리세요.",
        ),
    )
    max_import_archive_bytes: int = Field(
        default=_TRANSFER.max_archive_bytes,
        ge=1,
        title="가져오기 파일 최대 크기",
        description="가져올 zip 파일(압축된 크기)의 최대 바이트. 넘으면 아무것도 가져오지 않는다.",
        json_schema_extra=x_ui(tier="advanced", unit="바이트", group="transfer"),
    )
    max_import_files: int = Field(
        default=_TRANSFER.max_files,
        ge=1,
        title="가져오기 최대 항목 수",
        description="가져올 zip 안 항목(폴더 포함) 수 상한. 넘으면 아무것도 가져오지 않는다.",
        json_schema_extra=x_ui(tier="advanced", unit="개", group="transfer"),
    )
    max_import_file_bytes: int = Field(
        default=_TRANSFER.max_file_bytes,
        ge=1,
        title="가져오기 항목 최대 크기",
        description=(
            "zip 안 파일 하나의 풀린 최대 바이트(머리 포함). "
            "넘는 항목이 있으면 묶음 전체를 거부한다."
        ),
        json_schema_extra=x_ui(tier="advanced", unit="바이트", group="transfer"),
    )
    max_import_total_bytes: int = Field(
        default=_TRANSFER.max_total_bytes,
        ge=1,
        title="가져오기 풀린 크기 합",
        description="zip을 풀었을 때 크기 합의 상한. 넘으면 아무것도 가져오지 않는다.",
        json_schema_extra=x_ui(tier="advanced", unit="바이트", group="transfer"),
    )

    def limits(self) -> MemoryLimits:
        """저장소 쓰기 한도(``MemoryLimits``)."""
        return MemoryLimits(
            max_entry_bytes=self.max_entry_bytes,
            max_entries_per_scope=self.max_entries_per_scope,
            max_total_bytes=self.max_total_bytes,
            max_key_chars=self.max_key_chars,
            max_tags=self.max_tags,
            max_tag_chars=self.max_tag_chars,
            preview_chars=self.preview_chars,
        )

    def transfer_limits(self) -> MemoryTransferLimits:
        """가져오기 상한(``MemoryTransferLimits``)."""
        return MemoryTransferLimits(
            max_archive_bytes=self.max_import_archive_bytes,
            max_files=self.max_import_files,
            max_file_bytes=self.max_import_file_bytes,
            max_total_bytes=self.max_import_total_bytes,
        )


__all__ = ["MemoryModuleSettings"]
