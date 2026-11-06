"""mod-wiki 설치자 설정(``modules.options.mod-wiki``, design §7R.3).

위키 문법·비밀 검사·기록 보관 수·검색 방식·쓰기 검사는 사용자 데이터(워크스페이스 설정 ``wiki``
섹션, 계약 ``WikiSettings``)라 여기 없다. 설치자 값은 정의 종류 이름·폴더 이름·단독 루트·한도·검색
기본값·zip 상한만 둔다. 기본값은 패키지 데이터(``data/defaults.json``)에 있다(숫자·이름을 코드 두
곳에 두지 않는다).
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui
from agent_console_modkit import SeedSetting, SettingsCompat
from agent_console_safe_zip import ZipLimits
from agent_console_wiki import WikiRepositoryLimits

DEFAULTS_RESOURCE = "data/defaults.json"
"""설치자 옵션 기본값(패키지 데이터)."""


@cache
def _data(name: str) -> Any:
    text = resources.files("agent_console_mod_wiki").joinpath(name).read_text(encoding="utf-8")
    return json.loads(text)


def package_defaults() -> dict[str, Any]:
    """설치자 옵션 기본값 사본(패키지 데이터)."""
    return json.loads(json.dumps(_data(DEFAULTS_RESOURCE)))  # type: ignore[no-any-return]


_D = package_defaults()


class WikiSearchOptions(BaseModel):
    """검색 색인 기본값입니다. 사용자 설정에서 검색 방식을 고르면 그쪽이 먼저입니다."""

    # X48: 쓸 색인 = 사용자 wiki.search_backend → backend → fallback.

    model_config = ConfigDict(extra="forbid")

    backend: str = Field(
        default=_D["search"]["backend"],
        min_length=1,
        title="기본 검색 방식",
        description="설치된 검색 방식 중 기본으로 쓸 이름. 없는 이름이면 대체 방식을 쓰고 알린다.",
        json_schema_extra=x_ui(
            tier="advanced",
            example="sqlite-fts",
            when="검색 플러그인을 설치해 기본으로 쓰고 싶을 때 바꾸세요.",
        ),
    )
    fallback: str | None = Field(
        default=_D["search"]["fallback"],
        title="대체 검색 방식",
        description="기본 검색 방식을 쓸 수 없을 때 쓸 방식. 비우면 검색 색인 없이 동작한다.",
        json_schema_extra=x_ui(
            tier="advanced", example="scan", when="대체 방식을 바꾸거나 끄고 싶을 때 정하세요."
        ),
    )
    tokenizer: str = Field(
        default=_D["search"]["tokenizer"],
        min_length=1,
        title="낱말 나누기 방식",
        description="검색 색인이 낱말을 나누는 방식(색인 구현이 읽는 값).",
        json_schema_extra=x_ui(
            tier="advanced",
            example="trigram",
            when="검색 구현이 다른 나누기 방식을 받을 때만 바꾸세요.",
        ),
    )


class WikiExportLimits(BaseModel):
    """위키 zip 가져오기 상한입니다(디스크에 풀지 않고 읽습니다)."""

    model_config = ConfigDict(extra="forbid")

    max_archive_bytes: int = Field(
        default=_D["export_limits"]["max_archive_bytes"],
        ge=1,
        title="zip 파일 크기 상한",
        description="가져올 zip 파일 자체의 최대 크기.",
        json_schema_extra=x_ui(tier="advanced", unit="바이트", when="큰 위키를 옮길 때 늘리세요."),
    )
    max_files: int = Field(
        default=_D["export_limits"]["max_files"],
        ge=1,
        title="zip 항목 수 상한",
        description="zip 하나에 든 파일·폴더의 최대 개수.",
        json_schema_extra=x_ui(tier="advanced", unit="개", when="페이지가 아주 많을 때 늘리세요."),
    )
    max_file_bytes: int = Field(
        default=_D["export_limits"]["max_file_bytes"],
        ge=1,
        title="항목 하나 크기 상한",
        description="zip 안 파일 하나를 풀었을 때의 최대 크기.",
        json_schema_extra=x_ui(
            tier="advanced", unit="바이트", when="페이지 크기 상한을 늘렸을 때 함께 늘리세요."
        ),
    )
    max_total_bytes: int = Field(
        default=_D["export_limits"]["max_total_bytes"],
        ge=1,
        title="풀린 크기 합 상한",
        description="zip 안 파일을 모두 풀었을 때의 최대 크기 합.",
        json_schema_extra=x_ui(tier="advanced", unit="바이트", when="큰 위키를 옮길 때 늘리세요."),
    )

    def zip_limits(self) -> ZipLimits:
        """``agent_console_safe_zip.ZipLimits``로."""
        return ZipLimits(
            max_archive_bytes=self.max_archive_bytes,
            max_files=self.max_files,
            max_file_bytes=self.max_file_bytes,
            max_total_bytes=self.max_total_bytes,
        )


class WikiModuleSettings(BaseModel):
    """위키 기능의 저장 위치·이름·한도(설치자 값)."""

    model_config = ConfigDict(extra="forbid")

    wiki_kind: str = Field(
        default=_D["wiki_kind"],
        min_length=1,
        title="위키 정의 종류 이름",
        description="위키 정의를 저장하는 정의 종류의 이름. 바꾸면 이미 있는 위키를 찾지 못한다.",
        json_schema_extra=x_ui(
            tier="advanced",
            example="wiki",
            when="다른 기능의 정의 종류 이름과 겹칠 때만 바꾸세요.",
        ),
    )
    rules_kind: str = Field(
        default=_D["rules_kind"],
        min_length=1,
        title="위키 규칙 정의 종류 이름",
        description="위키 규칙을 저장하는 정의 종류의 이름. 바꾸면 이미 있는 규칙을 찾지 못한다.",
        json_schema_extra=x_ui(
            tier="advanced",
            example="wiki-rules",
            when="다른 기능의 정의 종류 이름과 겹칠 때만 바꾸세요.",
        ),
    )
    wiki_dir: str = Field(
        default=_D["wiki_dir"],
        min_length=1,
        title="위키 정의 폴더 이름",
        description="저장 공간(프로젝트 구성 폴더 또는 단독 루트) 안에서 위키 정의를 두는 폴더.",
        json_schema_extra=x_ui(
            tier="advanced", example="wikis", when="폴더 이름을 바꾸고 싶을 때 정하세요."
        ),
    )
    rules_dir: str = Field(
        default=_D["rules_dir"],
        min_length=1,
        title="위키 규칙 폴더 이름",
        description="저장 공간 안에서 위키 규칙을 두는 폴더.",
        json_schema_extra=x_ui(
            tier="advanced", example="wiki-rules", when="폴더 이름을 바꾸고 싶을 때 정하세요."
        ),
    )
    pages_dir: str = Field(
        default=_D["pages_dir"],
        min_length=1,
        title="페이지 폴더 이름",
        description="저장 공간 안에서 위키 페이지를 두는 폴더(그 아래 위키마다 폴더 하나).",
        json_schema_extra=x_ui(
            tier="advanced", example="wiki-pages", when="폴더 이름을 바꾸고 싶을 때 정하세요."
        ),
    )
    standalone_root: Path | None = Field(
        default=None,
        title="단독 저장 폴더",
        description=(
            "프로젝트 연동이 없을 때 위키를 두는 폴더. 비우면 워크스페이스 안 기본 폴더. 상대 "
            "경로는 설정 파일 폴더 기준."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            example="wiki",
            when="프로젝트 없이 위키만 쓸 때 저장 위치를 바꾸고 싶으면 정하세요.",
        ),
    )
    records_space_prefix: str = Field(
        default=_D["records_space_prefix"],
        title="기록 공간 이름 접두",
        description=(
            "프로젝트 기록 DB 공간 이름 = 이 접두 + 프로젝트 id(기록 연동 설정 space_prefix를 "
            "이어받는다)."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            example="project:",
            when="기록 연동의 공간 이름 접두를 바꿨을 때만 맞추세요.",
        ),
    )
    max_page_bytes: int = Field(
        default=_D["max_page_bytes"],
        ge=1,
        title="페이지 크기 상한",
        description="페이지 하나 본문의 최대 크기. 넘는 쓰기는 거부하고 색인에서 뺀다.",
        json_schema_extra=x_ui(
            tier="advanced", unit="바이트", when="아주 긴 페이지를 써야 할 때 늘리세요."
        ),
    )
    max_pages: int = Field(
        default=_D["max_pages"],
        ge=1,
        title="위키 하나의 페이지 수 상한",
        description="위키 하나에 둘 수 있는 최대 페이지 수. 넘으면 나머지는 색인하지 않고 알린다.",
        json_schema_extra=x_ui(tier="advanced", unit="개", when="아주 큰 위키를 쓸 때 늘리세요."),
    )
    parse_timeout_ms: int = Field(
        default=_D["parse_timeout_ms"],
        ge=1,
        title="페이지 읽기 시간 상한",
        description="페이지 하나의 링크를 찾는 최대 시간. 넘으면 그 페이지의 링크만 빼고 알린다.",
        json_schema_extra=x_ui(
            tier="advanced", unit="밀리초", when="느린 컴퓨터에서 큰 페이지가 잘릴 때 늘리세요."
        ),
    )
    parse_cache_entries: int = Field(
        default=_D["parse_cache_entries"],
        ge=0,
        title="읽은 페이지 보관 수",
        description="바뀌지 않은 페이지를 다시 읽지 않도록 위키마다 보관할 페이지 수. 0이면 끈다.",
        json_schema_extra=x_ui(
            tier="advanced", unit="개", when="메모리를 줄이고 싶을 때 줄이세요."
        ),
    )
    summary_cache_entries: int = Field(
        default=_D["summary_cache_entries"],
        ge=0,
        title="위키 요약 보관 수",
        description=(
            "위키 목록 카드 값(페이지·끊긴 링크·점검 수)을 다시 계산하지 않도록 보관할 위키 수. "
            "페이지 파일이 바뀌면 다시 계산한다."
        ),
        json_schema_extra=x_ui(tier="advanced", unit="개", when="위키가 아주 많을 때 늘리세요."),
    )
    graph_max_nodes: int = Field(
        default=_D["graph_max_nodes"],
        ge=1,
        title="그래프 칸 수 상한",
        description="링크 그래프 한 번에 보이는 최대 칸 수.",
        json_schema_extra=x_ui(
            tier="advanced", unit="개", when="큰 위키의 전체 그래프를 보고 싶을 때 늘리세요."
        ),
    )
    max_search_results: int = Field(
        default=_D["max_search_results"],
        ge=1,
        title="검색 결과 수 상한",
        description="검색 한 번에 돌려줄 최대 결과 수.",
        json_schema_extra=x_ui(tier="advanced", unit="개"),
    )
    max_changes_page: int = Field(
        default=_D["max_changes_page"],
        ge=1,
        title="최근 변경 한 쪽 상한",
        description="최근 변경 목록 한 번에 돌려줄 최대 줄 수.",
        json_schema_extra=x_ui(tier="advanced", unit="개"),
    )
    scan_interval_seconds: float = Field(
        default=_D["scan_interval_seconds"],
        ge=0,
        title="외부 변경 확인 주기",
        description=(
            "열어 본 위키의 페이지 파일을 이 주기마다 다시 읽어 앱 밖 변경을 기록한다. 0이면 "
            "읽을 때와 [다시 읽기]에서만 확인한다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            unit="초",
            when="다른 편집기로 자주 고쳐 기록을 바로 남기고 싶을 때 정하세요.",
        ),
    )
    search: WikiSearchOptions = Field(
        default_factory=WikiSearchOptions,
        title="검색 색인",
        description="검색 색인 기본값.",
        json_schema_extra=x_ui(tier="advanced", when="검색 플러그인을 설치했을 때 바꾸세요."),
    )
    export_limits: WikiExportLimits = Field(
        default_factory=WikiExportLimits,
        title="zip 상한",
        description="위키 zip 가져오기 상한.",
        json_schema_extra=x_ui(tier="advanced", when="큰 위키를 옮겨야 할 때 늘리세요."),
    )

    def limits(self, *, max_versions_per_page: int) -> WikiRepositoryLimits:
        """저장소 한도(기록 보관 수는 사용자 설정에서)."""
        return WikiRepositoryLimits(
            max_page_bytes=self.max_page_bytes,
            max_pages=self.max_pages,
            parse_timeout_ms=float(self.parse_timeout_ms),
            graph_max_nodes=self.graph_max_nodes,
            max_versions_per_page=max_versions_per_page,
        )


SETTINGS_COMPAT = SettingsCompat(
    seeds=(
        SeedSetting("records_space_prefix", "modules.options.link-projects-records.space_prefix"),
    ),
)
"""기록 연동의 ``space_prefix``를 기록 공간 이름 접두의 기본값으로 이어받는다(값이 없을 때만)."""

__all__ = [
    "DEFAULTS_RESOURCE",
    "SETTINGS_COMPAT",
    "WikiExportLimits",
    "WikiModuleSettings",
    "WikiSearchOptions",
    "package_defaults",
]
