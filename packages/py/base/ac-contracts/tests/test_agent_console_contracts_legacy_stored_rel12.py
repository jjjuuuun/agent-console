"""저장 데이터에 0.15.0에서 지운 키가 있어도 읽기가 실패하지 않는다(REL.12 조건 REL.16-1·2).

검사는 "읽는다"(뜻을 해석한다)가 아니라 "있어도 읽기가 실패하지 않는다"다. 공통 설정·로그 설정은
옛 키를 모르는 키로 보존하고(`model_extra`) 저장 때 되돌려 쓴다. 저장 형식의 해시(사용자 문서 dict로
계산하는 버전 해시와 같은 입력)는 키가 있든 없든 문서 그대로다. 프로젝트 등록부·합친 보기는
`working_directory`를 `folder`로 옮기고 `IGNORED_PROJECT_KEYS`를 버린다. 폴더 매니페스트는 모르는
키로 보존한다(읽고 무시는 프로젝트 모듈이 한다).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from agent_console_contracts import (
    IGNORED_SETTINGS_KEYS,
    LogSessionSummary,
    LogSettings,
    Project,
    ProjectManifest,
    ProjectRegistration,
    WorkspaceSettings,
    ignored_settings_keys,
)

REMOVED_KEYS = ("projects", "logs.projects", "project", "working_directory", "log_projects")
"""0.15.0에서 모델 필드를 지운 저장 키 허용 목록(이 키가 든 문서는 읽기가 실패하면 안 된다)."""

OLD_SETTINGS: dict[str, Any] = {
    "projects": {
        "new_definition_scope": {"agent": "project", "zz-kind": "shared"},
        "fallback": "x",
    },
    "logs": {
        "sources": [{"id": "s"}],
        "projects": {
            "groups": [{"id": "g", "label": "G", "match": ["/w/**"]}],
            "ungrouped": "repo_root",
            "git_worktrees": False,
        },
    },
    "zz-future": {"kept": True},
}


def _sha(doc: Any) -> str:
    text = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_allow_list_matches_ignored_settings_keys() -> None:
    assert set(IGNORED_SETTINGS_KEYS) <= set(REMOVED_KEYS)


def test_workspace_settings_keep_removed_keys() -> None:
    settings = WorkspaceSettings.model_validate(OLD_SETTINGS)
    assert settings.model_extra is not None
    assert settings.model_extra["projects"] == OLD_SETTINGS["projects"]
    assert settings.logs.model_extra == {"projects": OLD_SETTINGS["logs"]["projects"]}
    stored = settings.model_dump(mode="json", exclude_unset=True)
    assert stored == OLD_SETTINGS  # 저장 때 되돌려 쓴다
    assert _sha(stored) == _sha(OLD_SETTINGS)  # 버전 해시 입력 불변
    # 다시 읽어도 같다(왕복)
    again = WorkspaceSettings.model_validate(stored).model_dump(mode="json", exclude_unset=True)
    assert again == OLD_SETTINGS
    assert ignored_settings_keys(settings) == ["projects", "logs.projects"]


@pytest.mark.parametrize(
    "value",
    [None, {}, {"ungrouped": "zz"}, {"groups": "not-a-list"}, [1, 2], "x", 3],
    ids=["null", "empty", "bad-enum", "bad-groups", "list", "str", "int"],
)
def test_any_old_logs_projects_value_reads(value: Any) -> None:
    """옛 모델이 거부하던 값도 이제는 모르는 키라 읽기가 실패하지 않는다."""
    parsed = LogSettings.model_validate({"projects": value})
    assert parsed.model_dump(mode="json", exclude_unset=True) == {"projects": value}
    ws = WorkspaceSettings.model_validate({"projects": value})
    assert ws.model_dump(mode="json", exclude_unset=True) == {"projects": value}


def test_settings_without_removed_keys_hash_is_unchanged() -> None:
    doc = {"logs": {"sources": [{"id": "s"}]}}
    stored = WorkspaceSettings.model_validate(doc).model_dump(mode="json", exclude_unset=True)
    assert stored == doc
    assert _sha(stored) == _sha(doc)
    full = WorkspaceSettings.model_validate(doc).model_dump(mode="json")
    assert "projects" not in full
    assert "projects" not in full["logs"]


def test_old_log_session_summary_reads() -> None:
    """옛 응답(또는 외부 색인)의 `project`는 무시된다(응답 모델은 모르는 키를 버린다)."""
    old = {"session": "s", "project": {"id": "g", "label": "G"}, "project_id": "p"}
    summary = LogSessionSummary.model_validate(old)
    assert summary.project_id == "p"
    assert "project" not in summary.model_dump(mode="json")


def test_old_registration_and_project_read_folder() -> None:
    reg = {"id": "demo", "working_directory": "/w", "log_projects": ["g"], "zz": 1}
    stored = ProjectRegistration.model_validate(reg).model_dump(mode="json", exclude_unset=True)
    assert stored == {"id": "demo", "folder": "/w", "zz": 1}
    view = Project.model_validate({**reg, "name": "D", "uses": [], "import_mode": "x"})
    assert view.folder == "/w"
    dumped = view.model_dump(mode="json", exclude_unset=True)
    for key in ("working_directory", "log_projects", "uses", "import_mode"):
        assert key not in dumped
    assert not hasattr(view, "working_directory")
    assert not hasattr(view, "log_projects")


def test_old_manifest_keeps_unknown_keys() -> None:
    doc = {
        "format": 1,
        "id": "demo",
        "name": "D",
        "working_directory": "/w",
        "log_projects": ["g"],
        "uses": [],
        "import_mode": "all",
    }
    manifest = ProjectManifest.model_validate(doc)
    assert manifest.model_dump(mode="json", exclude_unset=True) == doc
