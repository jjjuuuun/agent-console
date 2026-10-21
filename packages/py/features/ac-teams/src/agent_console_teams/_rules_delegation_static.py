"""저장 시점 위임 검사(design §5.2R.7, 5.2R.37 B-1).

실행 시점 값(대상 유효 설정·실행 묶음·백엔드 능력) 없이 그래프와 디스크립터만으로 알 수 있는 위임
문제를 저장 전에 낸다. 실행 시점 `validate(plan)`(위임 방식 X12)은 그대로 실행 때 돈다.

- 일반 규칙 `check_delegation_config`(`validate_team` 규칙 목록에 들어 있다):
    - 위임자 노드 config `delegation[방식 id]`를 그 방식 디스크립터 `config_schema`(JSON Schema,
      데이터)로 검사 → `delegation.invalid_config`(path `/delegation/<방식 id>/…`).
    - 한 위임자가 같은 대상을 같은 방식으로 두 번 넘게 이음 → `delegation.duplicate_member`.
- 방식 고유 검사 `delegation_static_issues`(주입): 위임 방식 객체의 선택 메서드
  `static_issues(config, members)`·`declared_names(config, members)`(ac-runtime
  `StaticDelegationChecks`·`DelegationNameDeclarer`)를 구조적으로 부른다. 한 위임자가 합쳐 실행할
  방식을 여럿 쓰면 알린 이름을 묶음별로 모아 겹침을 `delegation.duplicate_<묶음>_names`로 낸다.
  이 패키지는 ac-runtime을 import하지 않는다(메서드 유무로만 판단).

위임 방식·노드 타입 이름은 모른다. 방식 config 위치는 `TeamConventions.node_delegation_key`다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts import Agent, DelegationStrategyDescriptor, Issue
from agent_console_graph import InvalidSchemaError, SchemaChecker, compile_schema

from ._check_context import TeamCheckContext
from ._issues import TeamIssueCodes, make_issue
from ._plan import DelegationLink, TeamPlan, describe_member

__all__ = [
    "DelegationTarget",
    "check_delegation_config",
    "delegation_static_issues",
    "delegation_targets",
]

_C = TeamIssueCodes


@dataclass(frozen=True, slots=True)
class DelegationTarget:
    """정적 검사에 넘기는 위임 대상 하나(ac-runtime `DelegationMemberView`를 구조적으로 만족).

    Attributes:
        node_id: 대상 노드 id.
        edge_id: 위임자 → 대상 연결 id.
        agent_id: 대상 에이전트 정의 id(없으면 None).
        role: 이 팀 안의 역할 이름(노드 config → 에이전트 정의 순, 없으면 None).
        delegate_when: 언제 맡길지(같은 순서, 없으면 빈 문자열).
        config: 위임 연결(엣지) config.
    """

    node_id: str
    edge_id: str
    agent_id: str | None = None
    role: str | None = None
    delegate_when: str = ""
    config: Mapping[str, Any] = field(default_factory=dict)


def _pointer_part(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _strategy_configs(plan: TeamPlan, delegator: str) -> Mapping[str, Any] | None:
    node = plan.node(delegator)
    if node is None:
        return None
    raw = node.config.get(plan.conventions.node_delegation_key)
    return raw if isinstance(raw, Mapping) else None


def _strategy_config(plan: TeamPlan, delegator: str, strategy: str) -> dict[str, Any]:
    configs = _strategy_configs(plan, delegator)
    value = configs.get(strategy) if configs is not None else None
    return dict(value) if isinstance(value, Mapping) else {}


# ---------------------------------------------------------------- 일반 규칙


def check_delegation_config(ctx: TeamCheckContext) -> None:
    """위임 방식 config 스키마 검사·같은 대상 중복(`validate_team` 규칙)."""
    _check_configs(ctx)
    _check_duplicate_members(ctx)


def _check_configs(ctx: TeamCheckContext) -> None:
    plan = ctx.plan
    key = plan.conventions.node_delegation_key
    checkers: dict[str, SchemaChecker | InvalidSchemaError] = {}
    for delegator in plan.delegates_of:
        configs = _strategy_configs(plan, delegator)
        if not configs:
            continue
        for sid, value in configs.items():
            desc = ctx.strategies.get(sid)
            if desc is None:  # 모르는 방식 config는 검사할 근거가 없다(연결이면 unknown_strategy)
                continue
            checker = _checker(checkers, desc)
            base = f"/{_pointer_part(key)}/{_pointer_part(sid)}"
            if isinstance(checker, InvalidSchemaError):
                ctx.add(
                    make_issue(
                        "warning",
                        _C.DELEGATION_INVALID_CONFIG_SCHEMA,
                        f"위임 방식 '{desc.title}'의 설정 스키마가 잘못되어 설정을 검사하지 "
                        f"못했습니다: {checker}",
                        node_id=delegator,
                        path=base,
                        details={"strategy": sid},
                    )
                )
                continue
            for v in checker(value):
                ctx.add(
                    make_issue(
                        "error",
                        _C.DELEGATION_INVALID_CONFIG,
                        f"'{ctx.label(delegator)}'의 위임 방식 '{desc.title}' 설정이 유효하지 "
                        f"않습니다: {v.message}",
                        node_id=delegator,
                        path=base + v.pointer,
                        details={"strategy": sid, "validator": v.validator},
                    )
                )


def _checker(
    cache: dict[str, SchemaChecker | InvalidSchemaError], desc: DelegationStrategyDescriptor
) -> SchemaChecker | InvalidSchemaError:
    found = cache.get(desc.id)
    if found is None:
        try:
            found = compile_schema(desc.config_schema)
        except InvalidSchemaError as exc:
            found = exc
        cache[desc.id] = found
    return found


def _check_duplicate_members(ctx: TeamCheckContext) -> None:
    for delegator, links in ctx.plan.delegates_of.items():
        groups: dict[tuple[str, str], list[DelegationLink]] = {}
        for link in links:
            groups.setdefault((link.member, link.strategy), []).append(link)
        for (member, strategy), same in groups.items():
            if len(same) < 2:
                continue
            edges = [link.edge_id for link in same]
            for link in same[1:]:
                ctx.add(
                    make_issue(
                        "error",
                        _C.DELEGATION_DUPLICATE_MEMBER,
                        f"'{ctx.label(delegator)}'이(가) '{ctx.label(member)}'을(를) 같은 위임 "
                        f"방식으로 {len(same)}번 잇습니다. 연결 하나만 남기세요",
                        node_id=member,
                        edge_id=link.edge_id,
                        details={
                            "delegator": delegator,
                            "member": member,
                            "strategy": strategy,
                            "edges": edges,
                        },
                    )
                )


# ---------------------------------------------------------------- 방식 고유 검사(주입)


def delegation_targets(
    plan: TeamPlan, links: Iterable[DelegationLink], agents: Mapping[str, Agent] | None = None
) -> list[DelegationTarget]:
    """위임 연결 → 정적 검사용 대상(역할·언제 맡길지는 `describe_member`와 같은 순서)."""
    targets: list[DelegationTarget] = []
    for link in links:
        ref = plan.agent_refs.get(link.member)
        agent = agents.get(ref) if agents is not None and ref is not None else None
        profile = describe_member(link, agent)
        edge = plan.edge(link.edge_id)
        targets.append(
            DelegationTarget(
                node_id=link.member,
                edge_id=link.edge_id,
                agent_id=ref,
                role=profile.role or None,
                delegate_when=profile.delegate_when,
                config=dict(edge.config) if edge is not None else {},
            )
        )
    return targets


def _composable(check: object) -> bool:
    """방식 객체에 디스크립터가 있으면 그 `composable`, 없으면 합칠 수 있다고 본다."""
    desc = getattr(check, "descriptor", None)
    return bool(getattr(desc, "composable", True))


def _failed(delegator: str, sid: str, method: str, exc: Exception) -> Issue:
    return make_issue(
        "warning",
        _C.VALIDATOR_FAILED,
        f"위임 방식 {sid!r}의 정적 검사({method})가 실패했습니다: {exc}",
        node_id=delegator,
        details={"strategy": sid, "method": method},
    )


def _normalize(issue: Issue, delegator: str, base: str) -> Issue:
    """방식이 낸 이슈 → 그래프 기준(위임자 노드·방식 config 경로)."""
    update: dict[str, Any] = {}
    if issue.edge_id is None:
        if issue.node_id is None:
            update["node_id"] = delegator
        if issue.path is not None:
            update["path"] = base + issue.path
    return issue.model_copy(update=update) if update else issue


def delegation_static_issues(
    plan: TeamPlan,
    checks: Mapping[str, object],
    *,
    delegators: Iterable[str] | None = None,
    agents: Mapping[str, Agent] | None = None,
) -> list[Issue]:
    """위임 방식의 선택 정적 검사(`static_issues`)와 합침 이름 충돌(`declared_names`).

    Args:
        plan: 팀 구성 해석 결과.
        checks: 위임 방식 id → 방식 객체(예: 위임 방식 레지스트리의 구현). 선택 메서드
            `static_issues(config, members) -> list[Issue]`·`declared_names(config, members) ->
            {묶음: [이름]}`가 있으면 부른다. 없는 방식·메서드는 건너뛴다. 객체에 `descriptor`가
            있으면 `composable`이 거짓인 방식은 이름 충돌 계산에서 뺀다(섞임은 다른 규칙이 알린다).
        delegators: 검사할 위임자 노드 id(None이면 모든 위임자, 그래프 순서).
        agents: 에이전트 정의(대상 역할·설명 보충, 없으면 노드 config만).

    Returns:
        이슈 목록. 방식 이슈는 `node_id`가 비면 위임자로 채우고, 연결 이슈(`edge_id`)가 아니면
        `path`에 `/delegation/<방식 id>`를 앞에 붙인다. 방식 메서드가 예외를 던지면
        `team.validator_failed` 경고다.
    """
    key = plan.conventions.node_delegation_key
    wanted = list(plan.delegates_of) if delegators is None else list(delegators)
    issues: list[Issue] = []
    for delegator in wanted:
        links = plan.delegates_of.get(delegator, ())
        groups: dict[str, list[DelegationLink]] = {}
        for link in links:
            groups.setdefault(link.strategy, []).append(link)
        declared: list[tuple[str, Mapping[str, Sequence[str]]]] = []
        for sid, same in groups.items():
            check = checks.get(sid)
            if check is None:
                continue
            config = _strategy_config(plan, delegator, sid)
            members = delegation_targets(plan, same, agents)
            base = f"/{_pointer_part(key)}/{_pointer_part(sid)}"
            static: Callable[..., Any] | None = getattr(check, "static_issues", None)
            if callable(static):
                try:
                    found = list(static(config, members))
                except Exception as exc:  # 플러그인 오류는 경고로(검증 전체를 깨지 않는다)
                    issues.append(_failed(delegator, sid, "static_issues", exc))
                else:
                    issues.extend(_normalize(i, delegator, base) for i in found)
            names: Callable[..., Any] | None = getattr(check, "declared_names", None)
            if callable(names) and _composable(check):
                try:
                    declared.append((sid, dict(names(config, members))))
                except Exception as exc:
                    issues.append(_failed(delegator, sid, "declared_names", exc))
        if len(groups) > 1:
            issues.extend(_name_collisions(plan, delegator, declared))
    return issues


def _name_collisions(
    plan: TeamPlan, delegator: str, declared: Sequence[tuple[str, Mapping[str, Sequence[str]]]]
) -> list[Issue]:
    owners: dict[str, dict[str, list[str]]] = {}  # 묶음 → 이름 → 방식 id(알린 순서, 중복 포함)
    for sid, groups in declared:
        for group, names in groups.items():
            for name in names:
                owners.setdefault(group, {}).setdefault(name, []).append(sid)
    issues: list[Issue] = []
    for group, by_name in owners.items():
        dups = sorted(n for n, sids in by_name.items() if len(sids) > 1)
        if not dups:
            continue
        strategies = list(dict.fromkeys(s for n in dups for s in by_name[n]))
        issues.append(
            make_issue(
                "error",
                _C.DELEGATION_DUPLICATE_NAMES.format(group=group),
                f"'{plan.label_of(delegator)}'에서 함께 실행할 위임 방식의 이름이 겹칩니다"
                f"({group}): {', '.join(dups)}",
                node_id=delegator,
                details={"group": group, "names": dups, "strategies": strategies},
            )
        )
    return issues
