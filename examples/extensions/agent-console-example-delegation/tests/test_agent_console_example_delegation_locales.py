"""Message catalogs (``locales/<lang>.json``): entry point, shape, ko/en codes and placeholders.

Standard library only, so the package keeps no dependency on the i18n feature.
"""

from __future__ import annotations

import json
import re
import tomllib
from importlib.resources import files
from pathlib import Path
from typing import Any

import agent_console_example_delegation

ENTRY_POINT = "agent-console-example-delegation"
LANGUAGES = ("ko", "en")
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][\w.]*)(?:\s*,[^{}]*)?\}")


def _catalog(language: str) -> dict[str, Any]:
    """Catalog file of ``language`` (an empty catalog when the package has no file for it)."""
    path = files(agent_console_example_delegation).joinpath("locales", f"{language}.json")
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_catalog_entry_point_is_declared() -> None:
    # 예제는 설치하지 않고 검사하므로(poe examples) 설치 메타데이터 대신 pyproject 선언을 본다.
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    declared = data["project"]["entry-points"]["agent_console.message_catalogs"]
    assert declared.get(ENTRY_POINT) == agent_console_example_delegation.__name__


def test_catalog_sections_are_string_maps() -> None:
    for language in LANGUAGES:
        data = _catalog(language)
        assert set(data) <= {"text", "codes", "ns"}
        for section in ("text", "codes"):
            for key, value in data.get(section, {}).items():
                assert isinstance(key, str), (language, key)
                assert isinstance(value, str), (language, key)
                assert value, (language, key)


def test_codes_match_between_languages() -> None:
    ko, en = (_catalog(lang).get("codes", {}) for lang in LANGUAGES)
    assert set(ko) == set(en)
    for code, template in en.items():
        assert set(_PLACEHOLDER.findall(template)) == set(_PLACEHOLDER.findall(ko[code])), code
