"""계약 0.15.0(깨는 변경): 0.11~0.12에 deprecated로 둔 프로젝트 범위 API 삭제 + R13 더하기.

- 지움: `MovePlan`·`MovePlanRequest`·`DefinitionMove`·`DeletePlan`·`ProjectDeleteMode`,
  `WorkspaceSettings.projects`(`ProjectPreferences`·`DefinitionScope`), `LogSettings.projects`
  (`LogProjectSettings`·`LogProjectGroup`·`LogUngroupedPolicy`), `LogSessionSummary.project`
  (`LogProjectRef`), 이슈 코드 4개, 제안 id `project.move_to_shared`(표는 빈 채로 남김).
- 더함: `MemoryChanged.space`, 오류·이슈 코드 `project.memory_unavailable`(409),
  `WikiInfo.wiki_kind`·`reserved_page_names`, `WIKI_GRAPH_DEPTH_ALL`·`WikiGraph.depth`,
  `WikiRuleEntry.severity`를 `IssueSeverity`로 좁힘, `LOG_PROJECT_UNGROUPED` deprecated 해제.
"""

from __future__ import annotations

import importlib

import pytest
from pydantic import ValidationError

import agent_console_contracts as contracts
from agent_console_contracts import (
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    HTTP_STATUS_BY_ERROR_CODE,
    LOG_PROJECT_UNGROUPED,
    WIKI_GRAPH_DEPTH_ALL,
    ErrorCodes,
    KnownIssueCodes,
    KnownSuggestionIds,
)
from agent_console_contracts import wiki as wiki_module
from agent_console_contracts.memory import MemoryChanged
from agent_console_contracts.schema import build_schema
from agent_console_contracts.wiki import WikiGraph, WikiInfo, WikiRuleEntry

REMOVED_MODELS = (
    "MovePlan",
    "MovePlanRequest",
    "DefinitionMove",
    "DeletePlan",
    "ProjectDeleteMode",
    "ProjectPreferences",
    "DefinitionScope",
    "LogProjectSettings",
    "LogProjectGroup",
    "LogProjectRef",
    "LogUngroupedPolicy",
)
"""0.15.0에서 지운 모델·타입 이름(루트·하위 모듈·스키마 어디에도 없어야 한다)."""

REMOVED_ISSUE_CODES = (
    "PROJECT_MEMORY_NETWORK_FS",
    "PROJECT_SHARED_USES_PROJECT",
    "PROJECT_CROSS_PROJECT",
    "PROJECT_DEFINITIONS_UNAVAILABLE",
)


def test_contracts_version_is_0_15_0() -> None:
    assert CONTRACTS_VERSION == "0.15.0"
    constants = build_schema()["x-constants"]
    assert constants["CONTRACTS_VERSION"] == "0.15.0"
    assert CONTRACT_VERSIONS == {
        "common": "2.0.0",
        "resources": "1.1.0",
        "logs": "2.0.0",
        "definitions": "2.0.0",
        "runs": "1.9.0",
        "usage": "1.1.0",
        "projects": "4.0.0",
        "chat": "1.4.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.3.0",
        "sdd": "1.3.0",
        "wiki": "1.3.0",
        "modules": "1.7.0",
    }
    assert constants["CONTRACT_VERSIONS"] == CONTRACT_VERSIONS


# ---------------------------------------------------------------- 지운 것


@pytest.mark.parametrize("name", REMOVED_MODELS)
def test_removed_models_are_gone_everywhere(name: str) -> None:
    assert not hasattr(contracts, name)
    assert name not in contracts.__all__
    for sub in ("projects", "definitions", "logs"):
        module = importlib.import_module(f"agent_console_contracts.{sub}")
        assert not hasattr(module, name), (sub, name)
    schema = build_schema()
    assert name not in schema["$defs"]
    assert all(name not in names for names in schema["x-modules"].values())


def test_removed_import_fails() -> None:
    with pytest.raises(ImportError):
        exec("from agent_console_contracts import DeletePlan", {})
    with pytest.raises(ImportError):
        exec("from agent_console_contracts.projects import MovePlan", {})


def test_removed_fields_are_not_model_fields() -> None:
    assert "projects" not in contracts.WorkspaceSettings.model_fields
    assert "projects" not in contracts.LogSettings.model_fields
    assert "project" not in contracts.LogSessionSummary.model_fields
    assert "project_id" in contracts.LogSessionSummary.model_fields
    # 0.15.0에 남기는 deprecated 필드(K-18)
    assert "default_backend" in contracts.WorkspaceSettings.model_fields


@pytest.mark.parametrize("name", REMOVED_ISSUE_CODES)
def test_removed_issue_codes(name: str) -> None:
    assert not hasattr(KnownIssueCodes, name)
    assert name not in build_schema()["x-constants"]["KNOWN_ISSUE_CODES"]


def test_kept_issue_codes_and_empty_suggestion_table() -> None:
    assert KnownIssueCodes.PROJECT_UNKNOWN == "project.unknown"
    assert KnownIssueCodes.PROJECT_REFERENCES_UNAVAILABLE == "project.references_unavailable"
    assert KnownIssueCodes.PROJECT_NETWORK_FS == "project.network_fs"
    assert KnownIssueCodes.SETTINGS_IGNORED_KEY == "settings.ignored_key"
    assert [n for n in vars(KnownSuggestionIds) if n.isupper()] == []
    assert build_schema()["x-constants"]["KNOWN_SUGGESTION_IDS"] == {}


def test_log_project_ungrouped_is_kept() -> None:
    assert LOG_PROJECT_UNGROUPED == "~ungrouped"
    assert build_schema()["x-constants"]["LOG_PROJECT_UNGROUPED"] == "~ungrouped"


# ---------------------------------------------------------------- 더한 것


def test_project_memory_unavailable_code() -> None:
    code = "project.memory_unavailable"
    assert code == ErrorCodes.PROJECT_MEMORY_UNAVAILABLE
    assert code == KnownIssueCodes.PROJECT_MEMORY_UNAVAILABLE
    assert HTTP_STATUS_BY_ERROR_CODE[code] == 409
    constants = build_schema()["x-constants"]
    assert constants["ERROR_CODES"]["PROJECT_MEMORY_UNAVAILABLE"] == code
    assert constants["KNOWN_ISSUE_CODES"]["PROJECT_MEMORY_UNAVAILABLE"] == code
    assert constants["HTTP_STATUS_BY_ERROR_CODE"][code] == 409
    # 모듈이 꺼진 경우와 구분한다
    assert code != ErrorCodes.FEATURE_UNAVAILABLE


def test_memory_changed_space() -> None:
    base = {
        "scope": {"kind": "global", "id": ""},
        "key": "k",
        "entry_id": "e",
        "version": 1,
        "op": "create",
        "author_kind": "user",
    }
    old = MemoryChanged.model_validate(base)
    assert old.space is None  # 옛 서버·라이브러리
    assert "space" not in old.model_dump(exclude_unset=True)
    assert MemoryChanged.model_validate({**base, "space": "demo"}).space == "demo"
    prop = build_schema()["$defs"]["MemoryChanged"]["properties"]["space"]
    assert "space" not in build_schema()["$defs"]["MemoryChanged"].get("required", [])
    assert {"type": "null"} in prop["anyOf"]


def test_wiki_info_new_fields() -> None:
    base = {"limits": {"max_page_bytes": 1, "max_pages": 1, "graph_max_nodes": 1}}
    old = WikiInfo.model_validate(base)
    assert (old.wiki_kind, old.reserved_page_names) == (None, None)
    info = WikiInfo.model_validate(
        {**base, "wiki_kind": "zz-wiki", "reserved_page_names": ["history"]}
    )
    assert (info.wiki_kind, info.reserved_page_names) == ("zz-wiki", ["history"])
    props = build_schema()["$defs"]["WikiInfo"]["properties"]
    assert {"wiki_kind", "reserved_page_names", "writable", "rules_kind"} <= set(props)


def test_wiki_graph_depth_all() -> None:
    assert WIKI_GRAPH_DEPTH_ALL == wiki_module.WIKI_GRAPH_DEPTH_ALL == "all"
    assert build_schema()["x-constants"]["WIKI_GRAPH_DEPTH_ALL"] == "all"
    assert WikiGraph().depth is None
    assert WikiGraph.model_validate({"depth": 2}).depth == 2
    with pytest.raises(ValidationError):
        WikiGraph.model_validate({"depth": -1})


def test_wiki_rule_entry_severity_is_narrowed() -> None:
    base = {"kind": "lint", "id": "x", "rule_id": "r"}
    for value in ("error", "warning", "info", None):
        assert WikiRuleEntry.model_validate({**base, "severity": value}).severity == value
    with pytest.raises(ValidationError):
        WikiRuleEntry.model_validate({**base, "severity": "zz"})
    prop = build_schema()["$defs"]["WikiRuleEntry"]["properties"]["severity"]
    assert {"$ref": "#/$defs/IssueSeverity"} in prop["anyOf"]
