"""대시보드 템플릿 읽기(``GET /logs/dashboard-templates``, design §4R.2·§4R.9).

템플릿은 프리셋 데이터다. 기본은 패키지 데이터 ``data/dashboard_templates``이고 설치자 옵션
``dashboard_templates_dir``로 다른 폴더를 쓴다. 파일 하나(``*.yaml``·``*.yml``·``*.json``)가
``LogDashboard`` 하나다. 폴더가 없거나 비어도 동작한다(빈 목록). 형식이 틀린 파일은 건너뛰고
경고 로그를 남긴다(다른 템플릿은 그대로).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from agent_console_contracts.logs import LogDashboard

DEFAULT_TEMPLATES_RESOURCE = "data/dashboard_templates"
"""패키지 안 기본 템플릿 폴더."""

TEMPLATE_SUFFIXES = (".yaml", ".yml", ".json")

_log = logging.getLogger("agent_console_mod_logs")


def _files(folder: Traversable | Path) -> list[Traversable | Path]:
    try:
        if not folder.is_dir():
            return []
        items: Iterable[Traversable | Path] = folder.iterdir()
        return sorted(
            (f for f in items if f.is_file() and f.name.endswith(TEMPLATE_SUFFIXES)),
            key=lambda f: f.name,
        )
    except (FileNotFoundError, NotADirectoryError):
        return []


def parse_dashboard(text: str, *, name: str = "") -> LogDashboard:
    """템플릿 파일 내용(YAML 또는 JSON) → ``LogDashboard``.

    Raises:
        ValueError: 형식이 틀림(``pydantic.ValidationError`` 포함).
    """
    if name.endswith(".json"):
        data = json.loads(text)
    else:
        data = YAML(typ="safe").load(text) if text.strip() else None
    return LogDashboard.model_validate(data or {})


def load_dashboard_templates(folder: Path | None = None) -> list[LogDashboard]:
    """템플릿 목록(파일 이름 순). 같은 id가 여럿이면 앞 파일이 이긴다.

    Args:
        folder: 템플릿 폴더. 없으면 패키지 기본 템플릿.
    """
    root: Traversable | Path = (
        folder
        if folder is not None
        else resources.files("agent_console_mod_logs").joinpath(DEFAULT_TEMPLATES_RESOURCE)
    )
    out: list[LogDashboard] = []
    seen: set[str] = set()
    for file in _files(root):
        try:
            dashboard = parse_dashboard(file.read_text(encoding="utf-8"), name=file.name)
        except (OSError, ValueError, YAMLError, ValidationError) as exc:
            _log.warning(
                "대시보드 템플릿 %s를 읽지 못해 건너뜁니다: %s", file.name, type(exc).__name__
            )
            continue
        if dashboard.id in seen:
            continue
        seen.add(dashboard.id)
        out.append(dashboard)
    return out


__all__ = [
    "DEFAULT_TEMPLATES_RESOURCE",
    "TEMPLATE_SUFFIXES",
    "load_dashboard_templates",
    "parse_dashboard",
]
