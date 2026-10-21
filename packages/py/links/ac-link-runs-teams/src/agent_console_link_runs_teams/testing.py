"""단독 실행·테스트용 모듈(공개).

``local_runs_module``: ``runs.starter``(검증만 — 엔진 검증 + 받은 준비자 검사)와
``definitions.lookup``(워크스페이스 파일 저장소)을 주는 작은 모듈. 단독 실행
``python -m agent_console_link_runs_teams``가 ``--with`` 없이 실행되면 이것을 붙인다(통합 서버에서는
``mod-runs``·``mod-definitions``가 대신한다). 실행 시작은 하지 않는다(``start_run`` 없음).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agent_console_contracts import ErrorCodes, Graph, Issue
from agent_console_modkit import ErrorReply, Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module
from agent_console_runtime import (
    Registries,
    ServiceKey,
    Services,
    load_registries,
    validate_graph_with,
)
from agent_console_store import DEFAULT_KINDS, GRAPH_KIND, FileDefinitionStore, NotFound

from .ports import DEFINITIONS_LOOKUP, RUN_PREPARERS, RUN_SERVICES, RUNS_STARTER

LOCAL_RUNS_ID = "local-runs"
DEFAULT_WORKSPACE = Path(".agent-console")


class LocalEnvironment:
    """노드 서비스 공급자에게 넘길 실행 환경(``working_directory``·``run_files_root``)."""

    def __init__(self, base: Path, state: Path) -> None:
        self.working_directory = base
        self.run_files_root = state / "runs"


class GraphNotFoundError(LookupError):
    """저장된 팀 구성이 없다(404)."""


class LocalChecker:
    """``runs.starter``의 검증 부분만(엔진 검증 + 준비자 검사).

    Args:
        store: 정의 저장소.
        registries: 플러그인 레지스트리.
        preparers: 지금 준비자 목록을 돌려주는 함수.
        providers: 지금 노드 서비스 공급자 목록을 돌려주는 함수.
        env: 노드 서비스 공급자에게 넘길 실행 환경.
    """

    def __init__(
        self,
        store: Any,
        registries: Registries,
        *,
        preparers: Any = list,
        providers: Any = list,
        env: Any = None,
    ) -> None:
        self._store = store
        self._registries = registries
        self._preparers = preparers
        self._providers = providers
        self._env = env or LocalEnvironment(Path("."), DEFAULT_WORKSPACE / ".state")

    def load_graph(self, graph_id: str, version_hash: str | None = None) -> Graph:
        """지금 팀 구성, 또는 `version_hash`를 주면 그 버전(저장소 버전 이력)."""
        try:
            if version_hash is None:
                return Graph.model_validate(self._store.get(GRAPH_KIND.name, graph_id).document)
            content = self._store.get_version(GRAPH_KIND.name, graph_id, version_hash).content
            return Graph.model_validate(content or {})
        except NotFound:
            shown = f"{graph_id}@{version_hash}" if version_hash else graph_id
            raise GraphNotFoundError(f"팀 구성 {shown}이(가) 없습니다") from None

    def check(self, graph: Graph) -> list[Issue]:
        items: dict[ServiceKey[Any], Any] = {}
        for provider in self._providers():
            items.update(provider.services(self._env))
        services = Services(items)
        engine = validate_graph_with(graph, self._registries, services=services)
        extra: list[Issue] = []
        for preparer in self._preparers():
            extra.extend(preparer.check(graph, engine, services, strict=False))
        return [*engine, *extra]


def _validation(exc: Exception) -> ErrorReply:
    return ErrorReply(code=ErrorCodes.VALIDATION_FAILED, details={"issues": []})


def local_runs_module(
    module_id: str = LOCAL_RUNS_ID,
    *,
    workspace: Path | None = None,
    registries: Registries | None = None,
) -> Module:
    """``runs.starter``(검증만)·``definitions.lookup`` 제공 모듈."""

    def build(ctx: ModuleContext) -> ModuleParts:
        root = workspace or (ctx.paths.workspace if ctx.paths is not None else DEFAULT_WORKSPACE)
        store = FileDefinitionStore(root, DEFAULT_KINDS)
        found = registries or ctx.registries
        if not isinstance(found, Registries):
            found = Registries()
            load_registries(found)
        env = (
            LocalEnvironment(ctx.paths.base_dir, ctx.paths.state) if ctx.paths is not None else None
        )
        checker = LocalChecker(
            store,
            found,
            preparers=lambda: ctx.ports(RUN_PREPARERS),
            providers=lambda: ctx.ports(RUN_SERVICES),
            env=env,
        )
        ctx.provide(RUNS_STARTER, checker)
        ctx.provide(DEFINITIONS_LOOKUP, store)
        return ModuleParts(
            error_map={GraphNotFoundError: ErrorCodes.NOT_FOUND, ValidationError: _validation}
        )

    return fake_module(
        module_id,
        kind="testing",
        provides=[RUNS_STARTER, DEFINITIONS_LOOKUP],
        optional=[RUN_PREPARERS, RUN_SERVICES],
        on_build=build,
    )


def standalone_modules() -> list[Module]:
    """단독 실행 기본 동반 모듈."""
    return [local_runs_module()]


__all__ = [
    "LOCAL_RUNS_ID",
    "GraphNotFoundError",
    "LocalChecker",
    "LocalEnvironment",
    "local_runs_module",
    "standalone_modules",
]
