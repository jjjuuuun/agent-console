"""설정 폼 도움말 린트(``uv run poe schema-help-lint``).

계약 폼 모델과 설치된 플러그인 디스크립터의 설정 스키마(노드·연결 종류, 리소스 종류, 사용량
출처, 로그 출처, 실행 백엔드 옵션·관측 수집기, 위임 방식), 설치된 서버 모듈의 옵션 스키마
(``modules.options.<id>``, 설정 화면이 읽기 전용으로 보인다), 모듈·연동 모듈이 조립 때 내놓는
하위 설정 스키마(entry point ``agent_console.config_schemas``)를
``agent_console_contracts.schema_help``로 검사한다.

``agent_console.config_schemas``: 레지스트리 entry point가 아니라 모듈 ``build``가 포트로 내놓는
출처(예: 연동 모듈의 사용량·로그 출처)의 설정 스키마를 이 검사에 알리는 선언이다. 값은 JSON
Schema 객체 또는 그것을 돌려주는 인자 없는 함수다. 이름이 보고 위치(``config-schemas/<이름>``)가
된다.

- 계약과 **번들 플러그인**(이 저장소 워크스페이스 패키지가 등록한 것) 위반 = 규칙 심각도대로
  (오류면 exit 1, 어려운 용어 같은 경고 규칙은 경고).
- **외부 플러그인**(그 밖의 배포판, 출처를 모르는 것) 위반 = 경고(종료 코드에 영향 없음).

번들 여부는 레지스트리 항목의 출처 문자열 끝 ``[배포판 이름 버전]``과 루트 ``pyproject.toml``의
``[tool.uv.sources]`` 워크스페이스 이름으로 정한다. 종류 이름은 이 스크립트에 없다.

사용::

    python scripts/schema_help_lint.py [--root .] [--quiet]
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_console_contracts.schema_help import HelpIssue, lint_contract_help, lint_schema_help

_DIST = re.compile(r"\[([A-Za-z0-9_.\-]+) [^\]]*\]\s*$")

CONFIG_SCHEMAS_GROUP = "agent_console.config_schemas"
"""모듈이 조립 때 내놓는 하위 설정 스키마를 선언하는 entry point 그룹(값 = 스키마 또는 함수)."""


@dataclass(frozen=True, slots=True)
class Target:
    """검사할 스키마 하나.

    Attributes:
        label: 보고 위치 접두사(예: ``node-types/agent/config_schema``).
        schema: JSON Schema.
        dist: 등록한 배포판 이름(모르면 None = 외부로 본다).
    """

    label: str
    schema: Mapping[str, Any]
    dist: str | None


def workspace_dists(root: Path) -> set[str]:
    """루트 ``pyproject.toml``의 ``[tool.uv.sources]`` 중 워크스페이스 패키지 이름."""
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    sources = data.get("tool", {}).get("uv", {}).get("sources", {})
    return {
        name
        for name, spec in sources.items()
        if isinstance(spec, Mapping) and spec.get("workspace") is True
    }


def dist_of(source: str | None) -> str | None:
    """레지스트리 출처 문자열에서 배포판 이름을 꺼낸다(없으면 None)."""
    if not source:
        return None
    m = _DIST.search(source)
    return m.group(1) if m else None


def _entries(registry: Any) -> Iterable[Any]:
    return list(registry.list())


def _descriptor_targets(
    group: str, registry: Any, extra: Callable[[Any], Iterable[tuple[str, Any]]] | None = None
) -> list[Target]:
    out: list[Target] = []
    for entry in _entries(registry):
        desc = entry.item.descriptor
        dist = dist_of(getattr(entry, "source", None))
        schema = getattr(desc, "config_schema", None) or {}
        if schema:
            out.append(Target(f"{group}/{desc.id}/config_schema", schema, dist))
        if extra is not None:
            for label, sub in extra(desc):
                if sub:
                    out.append(Target(f"{group}/{desc.id}/{label}", sub, dist))
    return out


def _collectors(desc: Any) -> Iterable[tuple[str, Any]]:
    for c in getattr(desc, "collectors", ()) or ():
        yield f"collectors/{c.id}/config_schema", c.config_schema


def module_option_targets() -> list[Target]:
    """설치된 서버 모듈(entry point)의 옵션 스키마(``settings_schema``가 있는 것만)."""
    from agent_console_modkit import MODULES_GROUP, as_module
    from agent_console_registry import Registry, load_entry_points

    registry: Registry[Any] = Registry("server_modules", validator=as_module)
    load_entry_points(MODULES_GROUP, registry)
    out: list[Target] = []
    for entry in _entries(registry):
        desc = entry.item.descriptor
        model = getattr(desc, "settings_schema", None)
        if model is None:
            continue
        schema = model.model_json_schema()
        out.append(Target(f"modules/{desc.id}/options", schema, dist_of(entry.source)))
    return out


def declared_schema_targets(entry_points: Iterable[Any] | None = None) -> list[Target]:
    """entry point ``agent_console.config_schemas``가 선언한 스키마.

    Args:
        entry_points: 테스트용 주입(주면 설치된 패키지를 훑지 않는다).

    Raises:
        TypeError: 값이 JSON Schema 객체(또는 그것을 돌려주는 함수)가 아닐 때.
    """
    from importlib.metadata import entry_points as installed

    eps = installed(group=CONFIG_SCHEMAS_GROUP) if entry_points is None else entry_points
    out: list[Target] = []
    for ep in sorted(eps, key=lambda e: str(e.name)):
        value = ep.load()
        schema = value() if callable(value) else value
        if not isinstance(schema, Mapping):
            raise TypeError(f"{CONFIG_SCHEMAS_GROUP}:{ep.name}: JSON Schema 객체가 아닙니다")
        dist = getattr(getattr(ep, "dist", None), "name", None)
        out.append(Target(f"config-schemas/{ep.name}/config_schema", schema, dist))
    return out


def log_source_targets() -> list[Target]:
    """로그 출처 레지스트리(entry point)의 설정 스키마(설정 > 로그의 출처 카드 폼).

    분류기 설정 스키마는 보지 않는다: 폼으로 그리지 않고 규칙 데이터 파일로만 고친다.
    """
    from agent_console_logs import LogRegistries

    regs = LogRegistries()
    regs.load()
    return _descriptor_targets("log-sources", regs.sources)


def collect_targets() -> list[Target]:
    """설치된 플러그인의 설정 스키마를 모은다(실행 엔진·리소스·사용량 레지스트리를 새로 로드)."""
    from agent_console_registry import Registry
    from agent_console_resources import load_resource_types
    from agent_console_runtime import Registries, load_registries
    from agent_console_usage import load_usage_sources

    regs = Registries()
    load_registries(regs)
    resource_types: Registry[Any] = Registry()
    load_resource_types(resource_types)
    usage_sources: Registry[Any] = Registry()
    load_usage_sources(usage_sources)
    targets: list[Target] = []
    targets += _descriptor_targets("node-types", regs.node_types)
    targets += _descriptor_targets("edge-types", regs.edge_types)
    targets += _descriptor_targets("backends", regs.backends, _collectors)
    targets += _descriptor_targets("delegation-strategies", regs.delegation_strategies)
    targets += _descriptor_targets("resource-types", resource_types)
    targets += _descriptor_targets("usage-sources", usage_sources)
    targets += log_source_targets()
    targets += module_option_targets()
    targets += declared_schema_targets()
    return targets


def run(
    targets: Iterable[Target], bundled: set[str], *, contract: bool = True
) -> tuple[list[HelpIssue], list[HelpIssue]]:
    """(오류, 경고)를 돌려준다.

    계약·번들 = 규칙 심각도 그대로(``error``는 오류, ``warning``은 경고), 외부 = 모두 경고.
    플러그인·모듈 스키마도 객체 설명(모델 docstring, 폼·묶음 머리말)까지 본다(``objects=True``).
    """
    errors: list[HelpIssue] = []
    warnings: list[HelpIssue] = []

    def add(issues: Iterable[HelpIssue], *, own: bool) -> None:
        for i in issues:
            (errors if own and i.severity == "error" else warnings).append(i)

    if contract:
        add(lint_contract_help(), own=True)
    for t in targets:
        add(lint_schema_help(t.schema, path=t.label, objects=True), own=t.dist in bundled)
    return errors, warnings


def _print(kind: str, issues: list[HelpIssue]) -> None:
    for i in issues:
        print(f"{kind} [{i.rule}] {i.path}: {i.message}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="schema-help-lint")
    parser.add_argument("--root", default=".", help="저장소 루트(pyproject.toml이 있는 곳)")
    parser.add_argument("--quiet", action="store_true", help="경고는 개수만 보인다")
    args = parser.parse_args(argv)
    targets = collect_targets()
    errors, warnings = run(targets, workspace_dists(Path(args.root)))
    if not args.quiet:
        _print("경고", warnings)
    _print("오류", errors)
    print(
        f"schema-help-lint: 스키마 {len(targets) + 1}개, 오류 {len(errors)}, 경고 {len(warnings)}"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
