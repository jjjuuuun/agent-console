"""테스트 도구: 묶음 파일·묶음 패키지·가짜 배포(entry point)를 임시 폴더에 만든다.

``package_catalogs``를 실제 설치 없이 시험할 때 쓴다. ``make_distribution``으로 만든 폴더를
``sys.path``에 넣으면 ``importlib.metadata``가 그 배포의 entry point를 찾는다.
"""

from __future__ import annotations

import importlib.metadata
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agent_console_i18n._loading import LOCALES_DIR, MESSAGE_CATALOGS_GROUP

__all__ = ["catalog_entry_point", "make_catalog_package", "make_distribution", "write_catalog"]


def write_catalog(
    folder: Path,
    language: str,
    *,
    text: Mapping[str, str] | None = None,
    codes: Mapping[str, str] | None = None,
    ns: Mapping[str, Any] | None = None,
) -> Path:
    """``<folder>/<language>.json``을 쓴다(넘긴 구역만).

    폴더가 없으면 만든다. 쓴 파일 경로를 돌려준다.
    """
    folder.mkdir(parents=True, exist_ok=True)
    body: dict[str, Any] = {}
    for name, value in (("text", text), ("codes", codes), ("ns", ns)):
        if value is not None:
            body[name] = dict(value)
    path = folder / f"{language}.json"
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def make_catalog_package(
    root: Path, module: str, catalogs: Mapping[str, Mapping[str, Any]]
) -> Path:
    """``root`` 아래에 import할 수 있는 패키지와 ``locales/<lang>.json``을 만든다.

    Args:
        root: ``sys.path``에 넣을 폴더.
        module: 패키지 이름(예: ``demo_pkg`` 또는 ``demo_pkg.sub``).
        catalogs: 언어 → 파일 내용(``{"text": …, "codes": …, "ns": …}``).

    Returns:
        ``locales`` 폴더 경로.
    """
    folder = root
    for part in module.split("."):
        folder = folder / part
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "__init__.py").touch()
    locales = folder / LOCALES_DIR
    locales.mkdir(exist_ok=True)
    for language, body in catalogs.items():
        (locales / f"{language}.json").write_text(
            json.dumps(dict(body), ensure_ascii=False), encoding="utf-8"
        )
    return locales


def make_distribution(
    root: Path,
    dist_name: str,
    entry_points: Mapping[str, str],
    *,
    version: str = "0.0.0",
    group: str = MESSAGE_CATALOGS_GROUP,
) -> Path:
    """``root``에 가짜 배포 메타데이터(``<이름>-<버전>.dist-info``)를 만든다.

    Args:
        root: ``sys.path``에 넣을 폴더(``make_catalog_package``와 같은 폴더면 된다).
        dist_name: 배포 이름.
        entry_points: entry point 이름 → 값(모듈).
        version: 배포 버전.
        group: entry point 그룹.

    Returns:
        ``dist-info`` 폴더 경로.
    """
    info = root / f"{dist_name.replace('-', '_')}-{version}.dist-info"
    info.mkdir(parents=True, exist_ok=True)
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {dist_name}\nVersion: {version}\n", encoding="utf-8"
    )
    lines = [f"[{group}]", *(f"{name} = {value}" for name, value in entry_points.items()), ""]
    (info / "entry_points.txt").write_text("\n".join(lines), encoding="utf-8")
    return info


def catalog_entry_point(
    name: str, module: str, *, group: str = MESSAGE_CATALOGS_GROUP
) -> importlib.metadata.EntryPoint:
    """``package_catalogs(entry_points=[...])``에 바로 넣을 entry point 하나."""
    return importlib.metadata.EntryPoint(name=name, value=module, group=group)
