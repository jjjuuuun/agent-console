"""자식 Run 이어 가기 거절(409)의 해결 버튼은 데이터다(5.5R.32): 문구·웹 역할을 바꿔 넘길 수 있고,
기본 역할은 이 모듈이 선언한 실행 화면 역할이다."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_console_mod_runs import (
    DEFAULT_CHILD_RESUME_FIX,
    ERROR_MAP,
    WEB_ROLES,
    ChildResumeFix,
    RunsModule,
    error_map,
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
