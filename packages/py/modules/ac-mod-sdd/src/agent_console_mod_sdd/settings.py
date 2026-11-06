"""mod-sdd 설치자 설정(``modules.options.mod-sdd``, design §6R.3·§6R.13·§6R.18 Q13).

작업 문법·비밀 검사·검증 출처는 사용자 데이터(워크스페이스 설정 ``sdd`` 섹션, 계약
``SddSettings``)라
여기 없다. 설치자 값은 정의 종류 이름·폴더 이름·단독 루트·라벨 접두·한도만 둔다. 기본값은 패키지
데이터(``data/defaults.json``)에 있다(숫자·이름을 코드 두 곳에 두지 않는다).
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

DEFAULTS_RESOURCE = "data/defaults.json"
"""설치자 옵션 기본값(패키지 데이터)."""
LABEL_DISPLAY_RESOURCE = "data/label_display.json"
"""실행 라벨 표시 규칙 기본값(패키지 데이터, 키는 접두 없는 이름)."""


@cache
def _data(name: str) -> Any:
    text = resources.files("agent_console_mod_sdd").joinpath(name).read_text(encoding="utf-8")
    return json.loads(text)


def package_defaults() -> dict[str, Any]:
    """설치자 옵션 기본값 사본(패키지 데이터)."""
    return dict(_data(DEFAULTS_RESOURCE))


def default_label_display() -> list[dict[str, Any]]:
    """실행 라벨 표시 규칙 기본값 사본(키·``id_from``은 접두 없는 이름)."""
    return [dict(item) for item in _data(LABEL_DISPLAY_RESOURCE)]


_D = package_defaults()


class SddModuleSettings(BaseModel):
    """스펙 기능의 저장 위치·이름·한도(설치자 값)."""

    model_config = ConfigDict(extra="forbid")

    spec_kind: str = Field(
        default=_D["spec_kind"],
        min_length=1,
        title="스펙 정의 종류 이름",
        description="스펙을 저장하는 정의 종류의 이름. 바꾸면 이미 있는 스펙을 찾지 못한다.",
        json_schema_extra=x_ui(
            tier="advanced",
            example="spec",
            when="다른 기능의 정의 종류 이름과 겹칠 때만 바꾸세요.",
        ),
    )
    template_kind: str = Field(
        default=_D["template_kind"],
        min_length=1,
        title="문서 틀 정의 종류 이름",
        description="문서 틀을 저장하는 정의 종류의 이름. 바꾸면 이미 있는 틀을 찾지 못한다.",
        json_schema_extra=x_ui(
            tier="advanced",
            example="spec-template",
            when="다른 기능의 정의 종류 이름과 겹칠 때만 바꾸세요.",
        ),
    )
    spec_dir: str = Field(
        default=_D["spec_dir"],
        min_length=1,
        title="스펙 폴더 이름",
        description="저장 공간(프로젝트 구성 폴더 또는 단독 루트) 안에서 스펙을 두는 폴더.",
        json_schema_extra=x_ui(
            tier="advanced", example="specs", when="스펙 폴더 이름을 바꾸고 싶을 때 정하세요."
        ),
    )
    template_dir: str = Field(
        default=_D["template_dir"],
        min_length=1,
        title="문서 틀 폴더 이름",
        description="저장 공간 안에서 문서 틀을 두는 폴더.",
        json_schema_extra=x_ui(
            tier="advanced",
            example="spec-templates",
            when="문서 틀 폴더 이름을 바꾸고 싶을 때 정하세요.",
        ),
    )
    standalone_root: Path | None = Field(
        default=None,
        title="단독 저장 폴더",
        description=(
            "프로젝트 연동이 없을 때 스펙을 두는 폴더. 비우면 워크스페이스 안 기본 폴더. 상대 "
            "경로는 설정 파일 폴더 기준."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            example="sdd",
            when="프로젝트 없이 스펙 기능만 쓸 때 저장 위치를 바꾸고 싶으면 정하세요.",
        ),
    )
    run_label_prefix: str = Field(
        default=_D["run_label_prefix"],
        title="실행 라벨 접두",
        description="작업 실행에 붙이는 라벨 키의 앞부분. 바꾸면 이전 실행과의 연결이 끊긴다.",
        json_schema_extra=x_ui(
            tier="advanced",
            example="sdd.",
            when="다른 기능의 실행 라벨과 겹칠 때만 바꾸세요.",
        ),
    )
    label_display: list[dict[str, Any]] | None = Field(
        default=None,
        title="실행 라벨 표시 규칙",
        description=(
            "실행 화면에 라벨을 칩으로 보이는 규칙(키는 접두를 뺀 이름). 비우면 기본 규칙, 빈 "
            "목록이면 칩을 보이지 않는다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            example=[{"key": "spec", "title": "스펙"}],
            when="실행 화면의 라벨 칩 이름이나 순서를 바꾸고 싶을 때 정하세요.",
        ),
    )
    max_bulk_start: int = Field(
        default=_D["max_bulk_start"],
        ge=1,
        title="한꺼번에 시작 상한",
        description="준비된 작업을 한 번에 시작할 수 있는 최대 개수.",
        json_schema_extra=x_ui(
            tier="advanced", unit="개", when="한 번에 더 많은 작업을 시작해야 할 때 늘리세요."
        ),
    )
    max_tasks: int = Field(
        default=_D["max_tasks"],
        ge=1,
        title="스펙 하나의 작업 수 상한",
        description="스펙 하나에서 읽을 최대 작업 수. 넘으면 나머지를 읽지 않고 알린다.",
        json_schema_extra=x_ui(
            tier="advanced", unit="개", when="아주 큰 작업 문서를 쓸 때 늘리세요."
        ),
    )
    parse_timeout_ms: int = Field(
        default=_D["parse_timeout_ms"],
        ge=1,
        title="문서 읽기 시간 상한",
        description="문서 하나의 작업을 읽는 최대 시간. 넘으면 그 문서의 작업만 빼고 알린다.",
        json_schema_extra=x_ui(
            tier="advanced", unit="밀리초", when="느린 컴퓨터에서 큰 문서가 잘릴 때 늘리세요."
        ),
    )
    parse_cache_entries: int = Field(
        default=_D["parse_cache_entries"],
        ge=0,
        title="읽은 결과 보관 수",
        description=(
            "문서가 바뀌지 않았으면 다시 읽지 않도록 보관할 스펙 수. 0이면 보관하지 않는다."
        ),
        json_schema_extra=x_ui(
            tier="advanced", unit="개", when="스펙이 아주 많아 메모리를 줄이고 싶을 때 줄이세요."
        ),
    )
    import_extensions: list[str] = Field(
        default_factory=lambda: list(_D["import_extensions"]),
        title="가져올 파일 확장자",
        description="폴더에서 가져오기 목록에 보일 파일 확장자(점 포함).",
        json_schema_extra=x_ui(
            tier="advanced",
            example=[".md", ".markdown"],
            when="다른 확장자의 문서도 가져오고 싶을 때 더하세요.",
        ),
    )
    import_limit: int = Field(
        default=_D["import_limit"],
        ge=1,
        title="가져오기 목록 상한",
        description="폴더에서 가져오기 목록에 한 번에 보일 최대 파일 수.",
        json_schema_extra=x_ui(tier="advanced", unit="개"),
    )
    server_host: str | None = Field(
        default=None,
        title="서버 바인딩 주소",
        description=(
            "서버가 묶인 주소(서버 설정 host를 이어받는다). 루프백이 아니면 폴더 파일 목록을 "
            "보이지 않는다. 비우면 루프백으로 본다."
        ),
        json_schema_extra=x_ui(tier="advanced", example="127.0.0.1"),
    )

    def label_rules(self) -> list[dict[str, Any]]:
        """접두를 붙인 실행 라벨 표시 규칙(``LabelDisplay`` 모양 dict, 계약 검증은 호출자)."""
        raw = self.label_display if self.label_display is not None else default_label_display()
        out: list[dict[str, Any]] = []
        for item in raw:
            rule = dict(item)
            key = rule.get("key")
            if not isinstance(key, str) or not key:
                continue
            rule["key"] = self.run_label_prefix + key
            target = rule.get("target")
            if isinstance(target, dict):
                target = dict(target)
                id_from = target.get("id_from")
                if isinstance(id_from, str) and id_from:
                    target["id_from"] = self.run_label_prefix + id_from
                rule["target"] = target
            out.append(rule)
        return out


SETTINGS_COMPAT = SettingsCompat(seeds=(SeedSetting("server_host", "host"),))
"""서버 바인딩 주소를 기본값으로 이어받는다(값이 없을 때만)."""

__all__ = [
    "DEFAULTS_RESOURCE",
    "LABEL_DISPLAY_RESOURCE",
    "SETTINGS_COMPAT",
    "SddModuleSettings",
    "default_label_display",
    "package_defaults",
]
