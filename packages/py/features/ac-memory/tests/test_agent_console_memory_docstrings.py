"""공개 함수 문서의 `>>>` 예가 실제 동작과 같은지(README doctest는 pytest 설정이 돌린다)."""

from __future__ import annotations

import doctest
from types import ModuleType

import pytest

from agent_console_memory import (
    _access,
    _keys,
    _policy,
    _scan,
    _scope_kinds,
    _shared,
    _toolkit,
)
from agent_console_memory.testing import _samples


@pytest.mark.parametrize(
    "module",
    [_access, _keys, _policy, _scan, _scope_kinds, _shared, _toolkit, _samples],
)
def test_module_doctests(module: ModuleType) -> None:
    result = doctest.testmod(module, optionflags=doctest.ELLIPSIS)
    assert result.attempted > 0
    assert result.failed == 0
