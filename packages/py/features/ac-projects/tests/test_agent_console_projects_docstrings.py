"""공개 함수 문서의 `>>>` 예가 실제 동작과 같은지(README doctest는 pytest 설정이 돌린다)."""

from __future__ import annotations

import doctest
from types import ModuleType

import pytest

from agent_console_projects import _folders, _layer, _logs, _scope


@pytest.mark.parametrize("module", [_folders, _layer, _logs, _scope])
def test_module_doctests(module: ModuleType) -> None:
    result = doctest.testmod(module, optionflags=doctest.ELLIPSIS)
    assert result.attempted > 0
    assert result.failed == 0
