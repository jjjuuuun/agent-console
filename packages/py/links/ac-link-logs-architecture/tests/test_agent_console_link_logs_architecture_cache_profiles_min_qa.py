"""5.5R.35 QA: `cache_profiles` 최소값(1) 검증."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_console_link_logs_architecture.settings import LogsArchitectureSettings


@pytest.mark.parametrize("bad", [0, -1])
def test_cache_profiles_below_one_is_rejected(bad: int) -> None:
    with pytest.raises(ValidationError):
        LogsArchitectureSettings(cache_profiles=bad)


def test_cache_profiles_one_is_accepted() -> None:
    assert LogsArchitectureSettings(cache_profiles=1).cache_profiles == 1
