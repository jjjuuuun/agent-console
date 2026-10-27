"""5.5R.10: 미리 판정한 결과(`matches`)와 주입한 판정기(`matcher`).

연동 모듈이 결과 캐시·증분 읽기에서 판정을 다시 하지 않으려고 쓴다. 넘겨도 결과가 같아야 한다.
"""

from __future__ import annotations

import pytest

from agent_console_architecture import (
    EventMatch,
    ProfileMatcher,
    project_architecture,
    selector_predicate,
)
from agent_console_conditions import ConditionOperator
from agent_console_contracts.architecture import ArchitectureProfile, ArchitectureSelector
from agent_console_contracts.logs import LogEvent, TokenSample

Ops = dict[str, ConditionOperator]


@pytest.mark.parametrize("max_seq", [None, 4])
def test_precomputed_matches_give_same_view(
    demo_events: list[LogEvent],
    demo_profile: ArchitectureProfile,
    demo_tokens: list[TokenSample],
    operators: Ops,
    source_kinds: dict[str, str],
    max_seq: int | None,
) -> None:
    errors = frozenset({"agent"})
    common = {
        "profile_id": "demo",
        "operators": operators,
        "source_kinds": source_kinds,
        "tokens": demo_tokens,
        "error_categories": errors,
        "max_seq": max_seq,
    }
    plain = project_architecture(demo_events, demo_profile, **common)  # type: ignore[arg-type]
    matcher = ProfileMatcher(demo_profile, operators, error_categories=errors)
    matches = [matcher.match(e) for e in demo_events]
    given = project_architecture(
        demo_events,
        demo_profile,
        matches=matches,
        **common,  # type: ignore[arg-type]
    )
    assert given == plain


def test_precomputed_matches_length_must_match(
    demo_events: list[LogEvent], demo_profile: ArchitectureProfile, operators: Ops
) -> None:
    with pytest.raises(ValueError, match="판정 결과 수"):
        project_architecture(
            demo_events, demo_profile, profile_id="demo", operators=operators, matches=[]
        )


class _Counting(ProfileMatcher):
    def __init__(self, profile: ArchitectureProfile, operators: Ops) -> None:
        super().__init__(profile, operators)
        self.calls = 0

    def match(self, event: LogEvent) -> EventMatch:
        self.calls += 1
        return super().match(event)


def test_selector_predicate_uses_given_matcher(
    demo_events: list[LogEvent], demo_profile: ArchitectureProfile, operators: Ops
) -> None:
    selector = ArchitectureSelector(arch="demo:cell:tools")
    plain = selector_predicate(demo_profile, selector, profile_id="demo", operators=operators)
    counting = _Counting(demo_profile, operators)
    given = selector_predicate(
        demo_profile, selector, profile_id="demo", operators=operators, matcher=counting
    )
    assert [given(e) for e in demo_events] == [plain(e) for e in demo_events]
    assert counting.calls == len(demo_events)
