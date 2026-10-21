"""5R.19: 세션 제목 순위 규칙은 설치자 옵션 데이터(`session_title_rules`), 비우면 ac-logs 기본."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_console_logs import SessionTitleRule, load_default_session_title_rules
from agent_console_mod_logs import LogsModuleSettings

from .test_agent_console_mod_logs_module import (  # type: ignore[import-not-found]
    _assembly,
    _service,
)


def test_default_rules_come_from_logs_package_data(tmp_path: Path) -> None:
    ctx = _service(_assembly(tmp_path)).query_context()
    assert ctx.session_title_rules == load_default_session_title_rules()
    assert "meta" in ctx.hidden_categories  # 기본 분류 체계의 숨김 범주


def test_installer_option_replaces_rules(tmp_path: Path) -> None:
    options = {"session_title_rules": [{"tag": "mine", "pick": "last"}, {"tag": "session_title"}]}
    ctx = _service(_assembly(tmp_path, options=options)).query_context()
    assert ctx.session_title_rules == (
        SessionTitleRule("mine", "last"),
        SessionTitleRule("session_title", "first"),
    )
    empty = _service(_assembly(tmp_path / "e", options={"session_title_rules": []}))
    assert empty.query_context().session_title_rules == ()


@pytest.mark.parametrize("bad", [[{"tag": ""}], [{"tag": "a", "pick": "middle"}], [{"x": 1}]])
def test_bad_rules_are_rejected(bad: object) -> None:
    with pytest.raises(ValidationError):
        LogsModuleSettings.model_validate({"session_title_rules": bad})
