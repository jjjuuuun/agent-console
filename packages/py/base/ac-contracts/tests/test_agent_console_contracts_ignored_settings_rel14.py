"""REL.14(K-6): 공통 설정의 읽고 무시하는 옛 키 찾기.

필드가 모델에 있는 계약(0.14)과 필드를 지운 계약(0.15)에서 같은 답을 내야 한다. 0.15 상태는
모르는 키로 보존된 값(`model_extra`)과 같으므로, 필드가 없는 모델로 흉내 낸다.
REL.16(0.15.0)부터 `WorkspaceSettings`·`LogSettings` 자체가 필드를 지운 모델이다 —
"model-0.14" 경우는 이름만 남았고 실제로는 지금 계약 모델로 같은 답을 확인한다.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ConfigDict

from agent_console_contracts import (
    IGNORED_SETTINGS_KEYS,
    DefinitionModel,
    LogSettings,
    WorkspaceSettings,
    ignored_settings_keys,
)

OLD_DOC: dict[str, Any] = {
    "projects": {"new_definition_scope": {"agent": "project"}, "fallback": "shared"},
    "logs": {"projects": {"groups": [{"id": "g", "match": ["/w/**"]}], "ungrouped": "none"}},
}


class _Logs015(DefinitionModel):
    """필드를 지운 뒤의 `LogSettings` 흉내(모르는 키 보존)."""

    model_config = ConfigDict(extra="allow")


class _Workspace015(DefinitionModel):
    model_config = ConfigDict(extra="allow")

    logs: _Logs015 = _Logs015()


def test_constant() -> None:
    assert IGNORED_SETTINGS_KEYS == ("projects", "logs.projects", "default_backend")


@pytest.mark.parametrize(
    "settings",
    [
        OLD_DOC,
        WorkspaceSettings.model_validate(OLD_DOC),
        _Workspace015.model_validate(OLD_DOC),
    ],
    ids=["dict", "model-0.14", "model-0.15"],
)
def test_finds_both_keys_with_or_without_fields(settings: Any) -> None:
    assert ignored_settings_keys(settings) == ["projects", "logs.projects"]


@pytest.mark.parametrize(
    "logs",
    [
        OLD_DOC["logs"],
        LogSettings.model_validate(OLD_DOC["logs"]),
        _Logs015.model_validate(OLD_DOC["logs"]),
    ],
    ids=["dict", "model-0.14", "model-0.15"],
)
def test_section_reads_section_value(logs: Any) -> None:
    assert ignored_settings_keys(logs, section="logs") == ["logs.projects"]


@pytest.mark.parametrize(
    "settings",
    [
        {},
        {"logs": {"sources": []}},
        {"projects": None, "logs": {"projects": None}},
        WorkspaceSettings(),
        WorkspaceSettings.model_validate({"logs": {"sources": []}}),
        _Workspace015(),
        "not a document",
        None,
    ],
)
def test_absent_or_null_is_empty(settings: Any) -> None:
    assert ignored_settings_keys(settings) == []
    assert ignored_settings_keys(settings, section="logs") == []


def test_section_skips_other_keys() -> None:
    assert ignored_settings_keys({"projects": {}}, section="logs") == ["logs.projects"]
    assert ignored_settings_keys({"logs": {}}, section="logs") == []
    assert ignored_settings_keys(OLD_DOC, section="missing") == []
