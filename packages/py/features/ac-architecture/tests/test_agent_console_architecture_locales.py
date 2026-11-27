"""Message catalogs (``locales/<lang>.json``): entry point, shape, ko/en codes and placeholders.

Standard library only, so the package keeps no dependency on the i18n feature.
"""

from __future__ import annotations

import importlib.metadata
import json
import re
from importlib.resources import files
from typing import Any

import agent_console_architecture

ENTRY_POINT = "ac-architecture"
LANGUAGES = ("ko", "en")
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][\w.]*)(?:\s*,[^{}]*)?\}")


def _catalog(language: str) -> dict[str, Any]:
    """Catalog file of ``language`` (an empty catalog when the package has no file for it)."""
    path = files(agent_console_architecture).joinpath("locales", f"{language}.json")
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_catalog_entry_point_points_at_package() -> None:
    found = {
        ep.name: ep.value
        for ep in importlib.metadata.entry_points(group="agent_console.message_catalogs")
    }
    assert found.get(ENTRY_POINT) == agent_console_architecture.__name__


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
