"""6R.16: ``RunService.host_id(project_id)`` — 다른 모듈(자동 진행)이 자기 앱 Run만 고르게 한다.

- 기록 공간 포트가 있으면 그 공간 핸들의 ``host_id``.
- 프로젝트 없음·기록 공간 포트 없음·모르는 공간 = None.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_mod_runs import DEFINITIONS_LOOKUP, RECORDS_SPACES, RUNS_STARTER, module
from agent_console_modkit import BaseServices, Module, ModuleContext, ModuleParts, Paths, assemble
from agent_console_modkit.testing import fake_module
from agent_console_runtime import Registries, load_registries
from agent_console_store import DEFAULT_KINDS, InMemoryDefinitionStore


class _Handle:
    host_id = "host-mine"
    state: Any = None

    def read_engine(self) -> None:
        return None


class _Spaces:
    def open(self, space: str) -> _Handle:
        if space.endswith(":nope"):
            raise LookupError(space)
        return _Handle()

    def state(self, space: str) -> Any:
        return None

    def close(self, space: str) -> None:
        pass


def _module(module_id: str, port: Any, item: object) -> Module:
    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(port, item)
        return ModuleParts()

    return fake_module(module_id, kind="link", provides=[port], on_build=build)


def _service(tmp_path: Path, *, spaces: bool) -> Any:
    registries = Registries()
    load_registries(registries)
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=registries,
    )
    library = InMemoryDefinitionStore(DEFAULT_KINDS)
    modules = [module, _module("t-defs", DEFINITIONS_LOOKUP, library)]
    if spaces:
        modules.append(_module("t-records", RECORDS_SPACES, _Spaces()))
    return assemble(modules, base=base).port(RUNS_STARTER)


def test_host_id_from_records_space(tmp_path: Path) -> None:
    service = _service(tmp_path, spaces=True)
    assert service.host_id("pa") == "host-mine"
    assert service.host_id(None) is None
    assert service.host_id("nope") is None


def test_host_id_without_records_spaces(tmp_path: Path) -> None:
    service = _service(tmp_path, spaces=False)
    assert service.host_id("pa") is None
