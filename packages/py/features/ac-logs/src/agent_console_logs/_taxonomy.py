"""분류 체계: 패키지 데이터 기본값 읽기와 설정 덮어쓰기 병합(design §4R.2)."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from ruamel.yaml import YAML

from agent_console_contracts.logs import LogCategory, LogTaxonomy

__all__ = [
    "DEFAULT_TAXONOMY_RESOURCE",
    "error_categories",
    "hidden_categories",
    "load_default_taxonomy",
    "load_taxonomy",
    "merge_taxonomy",
]

DEFAULT_TAXONOMY_RESOURCE = "data/default_taxonomy.yaml"
"""패키지 안 기본 분류 체계 파일(프리셋 데이터)."""

DANGER_TONE = "danger"


def load_taxonomy(text: str) -> LogTaxonomy:
    """YAML 문자열 → `LogTaxonomy`(빈 문서 = 빈 분류 체계)."""
    data = YAML(typ="safe").load(text) if text.strip() else None
    return LogTaxonomy.model_validate(data or {})


def load_default_taxonomy(path: Path | None = None) -> LogTaxonomy:
    """기본 분류 체계를 읽는다.

    Args:
        path: 다른 파일을 기본값으로 쓸 때(설치자 설정 등). 없으면 패키지 데이터.

    Returns:
        분류 체계. 파일이 없으면 빈 분류 체계(지워도 동작한다).
    """
    try:
        if path is not None:
            text = path.read_text(encoding="utf-8")
        else:
            text = (
                resources.files("agent_console_logs")
                .joinpath(DEFAULT_TAXONOMY_RESOURCE)
                .read_text(encoding="utf-8")
            )
    except (FileNotFoundError, NotADirectoryError):
        return LogTaxonomy()
    return load_taxonomy(text)


def merge_taxonomy(base: LogTaxonomy | None, override: LogTaxonomy | None) -> LogTaxonomy:
    """기본 분류 체계 위에 덮어쓰기를 범주·필드 단위로 얹는다.

    - 덮어쓰기 범주에서 **설정된 필드만**(`model_fields_set`, None이 아닌 값) 기본값을 바꾼다.
    - 기본에 없는 범주는 그대로 더한다. `order`는 덮어쓰기에 있으면 그것을 쓴다.
    - 둘 다 없으면 빈 분류 체계.
    """
    merged: dict[str, LogCategory] = {}
    for source in (base, override):
        if source is None:
            continue
        for cid, cat in source.categories.items():
            prev = merged.get(cid)
            patch = {
                k: getattr(cat, k)
                for k in cat.model_fields_set
                if k in LogCategory.model_fields and getattr(cat, k) is not None
            }
            merged[cid] = prev.model_copy(update=patch) if prev is not None else cat.model_copy()
    order = None
    if override is not None and override.order is not None:
        order = list(override.order)
    elif base is not None and base.order is not None:
        order = list(base.order)
    return LogTaxonomy(categories=merged, order=order)


def error_categories(taxonomy: LogTaxonomy) -> frozenset[str]:
    """오류로 셀 범주 id(`tone == "danger"`, F-25). 범주 이름으로 추측하지 않는다."""
    return frozenset(cid for cid, cat in taxonomy.categories.items() if cat.tone == DANGER_TONE)


def hidden_categories(taxonomy: LogTaxonomy) -> frozenset[str]:
    """기본으로 숨길 범주 id(`visible is False`)."""
    return frozenset(cid for cid, cat in taxonomy.categories.items() if cat.visible is False)
