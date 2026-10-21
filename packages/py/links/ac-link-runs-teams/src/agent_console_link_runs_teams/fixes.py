"""검증 이슈·노드 실패의 해결 버튼(``Fix``) 데이터 표(5.2R.5, ux-overhaul §1.5-C 3단 규칙).

오류 코드 → 버튼 목록은 **데이터**(기본 ``data/issue_fixes.json``)다. 버튼이 데려갈 곳은 웹 라우트
역할 이름(``FixTarget.role``)과 그 화면 안 위치(``section``)·초점(``focus``)이며 서버는 웹 경로를
모른다. 코드·역할을 바꾸려면 다른 표를 ``IssueFixes.from_data``로 만들어
``TeamRules(issue_fixes=)``에 넘긴다.

    >>> fixes = IssueFixes.from_data({"rules": [{"codes": ["x.y"], "actions": [
    ...     {"label": "고치기", "target": {"role": "definition:{team_kind}", "id": "{graph_id}",
    ...      "section": "{node_id}"}}]}]})
    >>> fix = fixes.fix_for("x.y", team_kind="graph", graph_id="g1")
    >>> fix.actions[0].target.model_dump(exclude_none=True)
    {'role': 'definition:graph', 'id': 'g1'}
    >>> fixes.fix_for("other", team_kind="graph", graph_id="g1") is None
    True
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Any

from agent_console_contracts import Fix, FixAction, FixTarget, Issue

__all__ = ["DEFAULT_ISSUE_FIXES", "IssueFixes", "load_issue_fixes"]

_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def _fill(template: Any, values: Mapping[str, str | None]) -> str | None:
    """``{이름}`` 자리를 채운다. 결과가 비면 None(모르는 이름도 빈 값)."""
    if template is None:
        return None
    text = _PLACEHOLDER.sub(lambda m: values.get(m.group(1)) or "", str(template))
    return text or None


@dataclass(frozen=True, slots=True)
class IssueFixes:
    """코드 → 해결 버튼 틀 표.

    Attributes:
        rules: 오류·이슈 코드 → 버튼 틀(``{label, target{role, id?, section?}, focus?}``) 목록.
    """

    rules: Mapping[str, tuple[Mapping[str, Any], ...]] = field(default_factory=dict)

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> IssueFixes:
        """``{"rules": [{"codes": [...], "actions": [...]}]}`` 데이터에서 만든다.

        같은 코드가 여러 규칙에 있으면 뒤 규칙이 이긴다."""
        table: dict[str, tuple[Mapping[str, Any], ...]] = {}
        for rule in data.get("rules", ()):
            actions = tuple(dict(a) for a in rule.get("actions", ()))
            for code in rule.get("codes", ()):
                table[str(code)] = actions
        return cls(table)

    def fix_for(
        self,
        code: str,
        *,
        team_kind: str,
        graph_id: str | None,
        node_id: str | None = None,
        edge_id: str | None = None,
    ) -> Fix | None:
        """코드의 해결 버튼(표에 없거나 채운 뒤 버튼이 하나도 남지 않으면 None).

        Args:
            code: 오류·이슈 코드.
            team_kind: 팀 구성 정의 종류 이름(``{team_kind}``).
            graph_id: 팀 구성 id(``{graph_id}``).
            node_id / edge_id: 문제 위치(``{node_id}``·``{edge_id}``, ``{item_id}`` = 노드 → 엣지).
        """
        templates = self.rules.get(code)
        if not templates:
            return None
        values = {
            "team_kind": team_kind,
            "graph_id": graph_id,
            "node_id": node_id,
            "edge_id": edge_id,
            "item_id": node_id or edge_id,
        }
        actions: list[FixAction] = []
        for tpl in templates:
            target = tpl.get("target") or {}
            role = _fill(target.get("role"), values)
            label = _fill(tpl.get("label"), values)
            if role is None or label is None:
                continue
            actions.append(
                FixAction(
                    label=label,
                    target=FixTarget(
                        role=role,
                        id=_fill(target.get("id"), values),
                        section=_fill(target.get("section"), values),
                    ),
                    focus=_fill(tpl.get("focus"), values),
                )
            )
        return Fix(actions=actions) if actions else None

    def attach(
        self, issues: Iterable[Issue], *, team_kind: str, graph_id: str | None
    ) -> list[Issue]:
        """이슈마다 해결 버튼을 붙인다(이미 ``fix``가 있는 이슈는 그대로)."""
        out: list[Issue] = []
        for issue in issues:
            if issue.fix is None:
                fix = self.fix_for(
                    issue.code,
                    team_kind=team_kind,
                    graph_id=graph_id,
                    node_id=issue.node_id,
                    edge_id=issue.edge_id,
                )
                if fix is not None:
                    issue = issue.model_copy(update={"fix": fix})
            out.append(issue)
        return out

    @property
    def codes(self) -> Sequence[str]:
        """표에 있는 코드(데이터 순서)."""
        return tuple(self.rules)


def load_issue_fixes(data: str | None = None) -> IssueFixes:
    """해결 버튼 표를 읽는다.

    Args:
        data: JSON 텍스트. None이면 패키지 기본 데이터(``data/issue_fixes.json``).
    """
    if data is None:
        data = (
            files("agent_console_link_runs_teams")
            .joinpath("data", "issue_fixes.json")
            .read_text(encoding="utf-8")
        )
    return IssueFixes.from_data(json.loads(data))


DEFAULT_ISSUE_FIXES = load_issue_fixes()
"""기본 표(입구·답변 없음, 백엔드 없음·모름, 알 수 없는 종류, 위임 깊이)."""
