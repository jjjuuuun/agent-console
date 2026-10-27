"""5.5R.35(5.5R.10 QA 결함): 범위마다 판정 결과(프로필 키)는 ``cache_profiles``개까지만 기억한다."""

from __future__ import annotations

import random
from collections.abc import Callable

from agent_console_architecture.testing import rename_profile_ids
from agent_console_link_logs_architecture.settings import LogsArchitectureSettings
from agent_console_link_logs_architecture.testing import (
    LogArchitectureHarness,
    demo_profiles,
    random_records,
)
from agent_console_logs import IndexBatch, LogIndex


def _namer(suffix: str) -> Callable[[str], str]:
    return lambda name: f"{name}{suffix}"


def test_old_profile_keys_and_their_views_are_dropped(index: LogIndex) -> None:
    index.write(IndexBatch(records=random_records(random.Random(3), 40, sessions=("S1",))))
    box = dict(demo_profiles())
    h = LogArchitectureHarness(index, cache_profiles=2)
    h.catalog._profiles = lambda: box
    keys: list[str] = []
    for i in range(4):
        suffix = str(i)
        box["demo"] = rename_profile_ids(
            demo_profiles()["demo"], cell=_namer(suffix), edge=_namer(suffix)
        )
        h.project(session="S1")
        scope = next(iter(h.views.cache))
        keys.append(next(reversed(scope.judged)))
    assert list(scope.judged) == keys[-2:]
    assert {k[0] for k in scope.views} <= set(keys[-2:])  # type: ignore[index]
    # 남은 키로 다시 부르면 기억한 결과를 쓴다(새 판정 없음)
    judged = h.views.stats.judged
    box["demo"] = rename_profile_ids(demo_profiles()["demo"], cell=_namer("2"), edge=_namer("2"))
    h.project(session="S1")
    assert h.views.stats.judged == judged


def test_cache_profiles_setting_default() -> None:
    assert LogsArchitectureSettings().cache_profiles == 4
