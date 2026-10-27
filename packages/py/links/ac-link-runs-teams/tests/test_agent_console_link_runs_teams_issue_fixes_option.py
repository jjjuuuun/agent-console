"""5.2R.106 후속: 설치자 옵션 ``issue_fixes_file``(해결 버튼 표 교체·끄기, R0.1(3))."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_console_contracts import Graph
from agent_console_link_runs_teams import (
    DEFAULT_ISSUE_FIXES,
    RUN_PREPARERS,
    IssueFixes,
    RunsTeamsLinkSettings,
    TeamRules,
    issue_fixes_of,
    module,
)
from agent_console_mod_definitions import module as definitions
from agent_console_mod_runs import module as runs
from agent_console_modkit import ModulesConfig

from .test_agent_console_link_runs_teams import (  # type: ignore[import-not-found]
    _client,
    _graph,
)

CODE = DEFAULT_ISSUE_FIXES.codes[0]
MINE = {
    "rules": [{"codes": ["my.code"], "actions": [{"label": "열기", "target": {"role": "graph"}}]}]
}


def test_descriptor_declares_settings_schema() -> None:
    assert module.descriptor.settings_schema is RunsTeamsLinkSettings
    assert RunsTeamsLinkSettings().issue_fixes_file is None
    assert RunsTeamsLinkSettings.model_validate({"issue_fixes_file": ""}).issue_fixes_file is None
    with pytest.raises(ValidationError):
        RunsTeamsLinkSettings.model_validate({"other": 1})


def test_issue_fixes_of(tmp_path: Path) -> None:
    assert issue_fixes_of(None) is DEFAULT_ISSUE_FIXES
    (tmp_path / "empty.json").write_text('{"rules": []}', encoding="utf-8")
    assert issue_fixes_of(Path("empty.json"), tmp_path).codes == ()  # 상대 경로 = 설정 폴더
    assert issue_fixes_of(tmp_path / "missing.json") == IssueFixes()
    (tmp_path / "mine.json").write_text(json.dumps(MINE), encoding="utf-8")
    assert issue_fixes_of(tmp_path / "mine.json").codes == ("my.code",)
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Expecting"):
        issue_fixes_of(tmp_path / "bad.json")


@pytest.mark.parametrize(
    ("table", "default_fix", "mine_fix"),
    [(None, True, False), ({"rules": []}, False, False), (MINE, False, True)],
)
def test_module_uses_option(
    tmp_path: Path, table: dict[str, object] | None, default_fix: bool, mine_fix: bool
) -> None:
    options: dict[str, object] = {}
    if table is not None:
        (tmp_path / "fixes.json").write_text(json.dumps(table), encoding="utf-8")
        options["issue_fixes_file"] = "fixes.json"
    config = ModulesConfig(options={"link-runs-teams": options})
    with _client(tmp_path, definitions, runs, module, config=config) as (_http, assembly):
        [rules] = assembly.ports(RUN_PREPARERS)
        assert isinstance(rules, TeamRules)
        graph = Graph.model_validate(_graph("flow", "fast"))
        assert (rules.error_fix(CODE, graph, None) is not None) is default_fix
        assert (rules.error_fix("my.code", graph, None) is not None) is mine_fix
