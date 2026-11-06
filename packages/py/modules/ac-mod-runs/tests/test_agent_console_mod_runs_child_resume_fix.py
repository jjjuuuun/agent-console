"""자식 Run 이어 가기 거절(409)의 해결 버튼은 데이터다(5.5R.32): 문구·웹 역할을 바꿔 넘길 수 있고,
기본 역할은 이 모듈이 선언한 실행 화면 역할이다."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from agent_console_mod_runs import (
    DEFAULT_CHILD_RESUME_FIX,
    ERROR_MAP,
    WEB_ROLES,
    ChildResumeFix,
    RunsModule,
    RunsModuleSettings,
    child_resume_fix_of,
    error_map,
    load_child_resume_fix,
)
from agent_console_modkit import ErrorMapping, ErrorReply
from agent_console_runtime import ResumeError


def _child_refusal() -> ResumeError:
    return ResumeError("자식 실행은 따로 이어 갈 수 없습니다", details={"root_run_id": "root-1"})


def _reply(table: Mapping[type[Exception], ErrorMapping], exc: Exception) -> ErrorReply:
    handler = table[ResumeError]
    assert callable(handler)
    reply = handler(exc)
    assert isinstance(reply, ErrorReply)
    return reply


def _reply_fix(table: Mapping[type[Exception], ErrorMapping]) -> Mapping[str, Any] | None:
    return _reply(table, _child_refusal()).fix


def test_default_role_is_module_web_role() -> None:
    assert DEFAULT_CHILD_RESUME_FIX.role in WEB_ROLES
    fix = _reply_fix(ERROR_MAP)
    assert fix == {
        "actions": [
            {
                "label": DEFAULT_CHILD_RESUME_FIX.label,
                "target": {"role": DEFAULT_CHILD_RESUME_FIX.role, "id": "root-1"},
            }
        ]
    }


def test_custom_data_changes_label_and_role() -> None:
    data = ChildResumeFix(label="처음 실행으로", role="zz-history")
    fix = _reply_fix(error_map(child_resume=data))
    assert fix is not None
    [action] = fix["actions"]
    assert action == {"label": "처음 실행으로", "target": {"role": "zz-history", "id": "root-1"}}


def test_no_fix_without_root() -> None:
    assert _reply(ERROR_MAP, ResumeError("없음")).fix is None


def test_module_accepts_data() -> None:
    data = ChildResumeFix(label="x", role="y")
    assert RunsModule(child_resume_fix=data)._child_resume_fix is data


def test_default_comes_from_package_data() -> None:
    """문구·역할은 코드 상수가 아니라 패키지 데이터(``data/issue_fixes.json``)다(6R.7, L-18)."""
    import json
    from importlib.resources import files

    raw = json.loads(
        files("agent_console_mod_runs").joinpath("data/issue_fixes.json").read_text("utf-8")
    )
    assert ChildResumeFix(**raw["child_resume"]) == DEFAULT_CHILD_RESUME_FIX
    assert load_child_resume_fix() == DEFAULT_CHILD_RESUME_FIX


def test_table_without_entry_means_no_button() -> None:
    assert load_child_resume_fix('{"child_resume": {"label": "", "role": "runs"}}') is None
    assert load_child_resume_fix("{}") is None
    assert _reply_fix(error_map(child_resume=None)) is None


def test_installer_file_overrides(tmp_path: Path) -> None:
    (tmp_path / "fixes.json").write_text(
        '{"child_resume": {"label": "처음으로", "role": "zz-runs"}}', encoding="utf-8"
    )
    fix = child_resume_fix_of(Path("fixes.json"), tmp_path)
    assert fix == ChildResumeFix(label="처음으로", role="zz-runs")
    assert child_resume_fix_of(None) == DEFAULT_CHILD_RESUME_FIX
    custom = ChildResumeFix(label="x", role="y")
    assert child_resume_fix_of(None, default=custom) is custom
    assert child_resume_fix_of(Path("missing.json"), tmp_path) is None


def test_settings_blank_file_is_default() -> None:
    assert RunsModuleSettings(issue_fixes_file="  ").issue_fixes_file is None  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="객체"):
        load_child_resume_fix("[]")
