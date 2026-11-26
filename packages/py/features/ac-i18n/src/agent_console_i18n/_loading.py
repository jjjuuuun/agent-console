"""묶음 파일·폴더·entry point 불러오기(design §I18N.3·§I18N.8).

- 폴더 하나 = ``<lang>.json`` 파일들. ``.json``이 아닌 파일과 ``.``으로 시작하는 파일은 무시한다.
- entry point 그룹 ``agent_console.message_catalogs``: 이름 = 묶음 id, 값 = ``locales/`` 폴더를 가진
  모듈(``pkg.sub``). ``모듈:속성`` 꼴이면 모듈 부분만 쓴다.
- 실패한 파일·출처는 건너뛰고 문제(``CatalogIssue``)로 남긴다. 예외를 던지지 않는다.
"""

from __future__ import annotations

import importlib.metadata
import importlib.resources
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Final

from agent_console_i18n._model import Catalog, CatalogIssue, Origin, read_catalog

__all__ = [
    "LOCALES_DIR",
    "MESSAGE_CATALOGS_GROUP",
    "CatalogLoad",
    "folder_catalogs",
    "load_catalog_file",
    "load_catalog_folder",
    "package_catalogs",
]

MESSAGE_CATALOGS_GROUP: Final = "agent_console.message_catalogs"
"""문구 묶음 출처 entry point 그룹(확장 지점 message-catalog)."""

LOCALES_DIR: Final = "locales"
"""entry point 모듈 안에서 묶음 파일을 찾는 폴더 이름."""

_SUFFIX: Final = ".json"


@dataclass(frozen=True, slots=True)
class CatalogLoad:
    """불러온 묶음(출처 순서 그대로)과 건너뛴 문제."""

    catalogs: tuple[Catalog, ...] = ()
    issues: tuple[CatalogIssue, ...] = ()
    skipped_sources: tuple[str, ...] = field(default=())
    """설정으로 끈(``disabled``) entry point 이름."""

    def __add__(self, other: CatalogLoad) -> CatalogLoad:
        return CatalogLoad(
            self.catalogs + other.catalogs,
            self.issues + other.issues,
            self.skipped_sources + other.skipped_sources,
        )


def load_catalog_file(
    path: Path | Traversable,
    *,
    source: str = "",
    origin: Origin = "inline",
    language: str | None = None,
) -> tuple[Catalog | None, list[CatalogIssue]]:
    """``<lang>.json`` 파일 하나를 읽는다.

    Args:
        path: 파일(``Path`` 또는 ``importlib.resources`` 항목).
        source: 출처 이름.
        origin: 출처 종류.
        language: 언어 코드. 생략하면 파일 이름(확장자 뺀 것).

    Returns:
        (묶음 또는 None, 문제 목록). 읽기·JSON 오류는 ``i18n.catalog_unreadable``.
    """
    name = path.name
    lang = language if language is not None else name.removesuffix(_SUFFIX)
    where = str(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return None, [
            CatalogIssue(
                code="i18n.catalog_unreadable",
                message=f"cannot read catalog file ({type(exc).__name__}: {exc})",
                source=source or None,
                language=lang,
                path=where,
            )
        ]
    return read_catalog(data, language=lang, source=source, origin=origin, path=where)


def load_catalog_folder(
    folder: Path | Traversable, *, source: str = "", origin: Origin = "inline"
) -> CatalogLoad:
    """폴더 안 ``<lang>.json``을 이름 순으로 모두 읽는다. 폴더가 없으면 ``i18n.locales_missing``."""
    if not folder.is_dir():
        return CatalogLoad(
            issues=(
                CatalogIssue(
                    code="i18n.locales_missing",
                    message="catalog folder does not exist",
                    source=source or None,
                    path=str(folder),
                ),
            )
        )
    catalogs: list[Catalog] = []
    issues: list[CatalogIssue] = []
    entries = sorted(folder.iterdir(), key=lambda item: item.name)
    for entry in entries:
        if entry.name.startswith(".") or not entry.name.endswith(_SUFFIX) or not entry.is_file():
            continue
        catalog, problems = load_catalog_file(entry, source=source, origin=origin)
        issues.extend(problems)
        if catalog is not None:
            catalogs.append(catalog)
    return CatalogLoad(tuple(catalogs), tuple(issues))


def package_catalogs(
    *,
    entry_points: Iterable[importlib.metadata.EntryPoint] | None = None,
    disabled: Iterable[str] = (),
    group: str = MESSAGE_CATALOGS_GROUP,
) -> CatalogLoad:
    """Read the package catalogs registered through entry points, in name order.

    Args:
        entry_points: 테스트용 주입(그룹이 맞는 것만 쓴다). None이면 설치된 배포에서 찾는다.
        disabled: 끌 entry point 이름(읽지 않고 ``skipped_sources``에 적는다).
        group: entry point 그룹 이름.

    Returns:
        ``CatalogLoad``. 모듈을 못 불러오면 ``i18n.source_unavailable``(그 출처만 건너뜀).
    """
    found = (
        [ep for ep in entry_points if ep.group == group]
        if entry_points is not None
        else list(importlib.metadata.entry_points(group=group))
    )
    off = set(disabled)
    result = CatalogLoad()
    for ep in sorted(found, key=lambda item: (item.name, item.value)):
        if ep.name in off:
            result += CatalogLoad(skipped_sources=(ep.name,))
            continue
        try:
            root = importlib.resources.files(ep.module)
        except Exception as exc:  # 플러그인 import 실패는 그 출처만 건너뛴다
            result += CatalogLoad(
                issues=(
                    CatalogIssue(
                        code="i18n.source_unavailable",
                        message=f"cannot import module '{ep.module}' ({type(exc).__name__})",
                        source=ep.name,
                    ),
                )
            )
            continue
        result += load_catalog_folder(root / LOCALES_DIR, source=ep.name, origin="package")
    return result


def folder_catalogs(folders: Sequence[str | Path], *, base_dir: Path | None = None) -> CatalogLoad:
    """사용자 폴더 목록을 순서대로 읽는다. 출처 이름은 받은 경로 문자열 그대로다.

    Args:
        folders: 폴더 경로. 상대 경로는 ``base_dir`` 기준(없으면 그대로 — 현재 폴더 기준).
        base_dir: 상대 경로의 기준 폴더(보통 설정 파일 폴더).
    """
    result = CatalogLoad()
    for folder in folders:
        path = Path(folder).expanduser()
        if base_dir is not None and not path.is_absolute():
            path = base_dir / path
        result += load_catalog_folder(path, source=str(folder), origin="folder")
    return result
