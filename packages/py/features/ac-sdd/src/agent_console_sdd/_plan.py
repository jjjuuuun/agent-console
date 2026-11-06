"""계획: 끝나지 않은 작업의 위상 층(= 병렬 묶음)과 가장 긴 의존 사슬(= 병목), design §6R.1.6.

층은 표준 `graphlib.TopologicalSorter`로 내고, 최장 경로는 위상 순서 위 동적 계획법으로 더한다(새
의존
없음). 순환은 파싱과 같은 Tarjan으로 찾는다.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from graphlib import TopologicalSorter

from agent_console_contracts.sdd import (
    EffectiveSyntax,
    KnownTaskFieldRoles,
    ParsedTask,
    SpecIndex,
    TaskPlan,
)

from ._compiled import CompiledSyntax, compile_syntax
from ._graphs import dependency_cycles

__all__ = ["plan", "task_weight"]


def task_weight(task: ParsedTask, weight_fields: tuple[str, ...] | list[str]) -> float:
    """작업 가중치: 가중치 역할 필드 중 처음 있는 것의 값(양의 유한 수). 없거나 읽을 수 없으면 1."""
    for name in weight_fields:
        raw = task.fields.get(name)
        if raw is None:
            continue
        try:
            value = float(raw.strip())
        except ValueError:
            continue
        if math.isfinite(value) and value > 0:
            return value
    return 1.0


def plan(index: SpecIndex, syntax: EffectiveSyntax | CompiledSyntax) -> TaskPlan:
    """끝나지 않은 작업의 의존 계획을 계산한다(순수 함수).

    규칙:
        - 대상은 끝나지 않은 작업(상태가 `done` 상태가 아님)이다. 끝난 의존은 이미 풀린 것으로 보고,
          문서에 없는 의존(파싱 이슈 `sdd.unknown_dependency`)은 무시한다(`ready`와 같은 규칙).
        - `layers[0]` = 지금 시작할 수 있는 작업, `layers[k]` = 의존이 모두 앞 층에 있는 작업. 층 안
          순서는 문서 순서다.
        - 순환(`cycles`)에 든 작업과 그것에 (간접으로) 기대는 작업은 끝날 수 없어 층에 넣지 않고
          `blocked`에만 둔다.
        - `critical_path` = 층에 든 작업 중 가중치 합이 가장 큰 의존 사슬(시작 → 끝). 가중치는 문법
          `roles`에서 `weight` 역할인 필드 값(없으면 1). 같으면 문서에서 앞선 사슬.

    Args:
        index: `parse_spec` 결과.
        syntax: 같은 파싱에 쓴 유효 문법(끝남 상태·가중치 필드를 읽는다).

    Returns:
        `TaskPlan`.
    """
    compiled = syntax if isinstance(syntax, CompiledSyntax) else compile_syntax(syntax)
    done = compiled.done_ids
    weight_fields = compiled.fields_with_role(KnownTaskFieldRoles.WEIGHT)

    open_tasks = [t for t in index.tasks if t.status not in done]
    order = {t.key: n for n, t in enumerate(open_tasks)}
    deps: dict[str, list[str]] = {
        t.key: [d for d in t.dependencies if d in order] for t in open_tasks
    }
    keys = [t.key for t in open_tasks]
    cycles = dependency_cycles(keys, deps)

    stuck: set[str] = {k for comp in cycles for k in comp}
    if stuck:
        dependents: dict[str, list[str]] = {}
        for k, ds in deps.items():
            for d in ds:
                dependents.setdefault(d, []).append(k)
        frontier = list(stuck)
        while frontier:
            node = frontier.pop()
            for nxt in dependents.get(node, ()):
                if nxt not in stuck:
                    stuck.add(nxt)
                    frontier.append(nxt)

    sorter: TopologicalSorter[str] = TopologicalSorter()
    for k in keys:
        if k not in stuck:
            sorter.add(k, *deps[k])
    sorter.prepare()
    layers: list[list[str]] = []
    layer_of: dict[str, int] = {}
    while sorter.is_active():
        group = sorted(sorter.get_ready(), key=order.__getitem__)
        for k in group:
            layer_of[k] = len(layers)
        layers.append(group)
        sorter.done(*group)

    by_key: Mapping[str, ParsedTask] = {t.key: t for t in open_tasks}
    best: dict[str, float] = {}
    prev: dict[str, str | None] = {}
    for group in layers:
        for k in group:
            weight = task_weight(by_key[k], weight_fields)
            choice: str | None = None
            for d in sorted(deps[k], key=order.__getitem__):
                if choice is None or best[d] > best[choice]:
                    choice = d
            best[k] = weight + (best[choice] if choice is not None else 0.0)
            prev[k] = choice
    critical: list[str] = []
    if best:
        end = min(best, key=lambda k: (-best[k], order[k]))
        step: str | None = end
        while step is not None:
            critical.append(step)
            step = prev[step]
        critical.reverse()

    ready = [k for k in keys if k not in stuck and not deps[k]]
    blocked = [k for k in keys if k in stuck or deps[k]]
    return TaskPlan(
        ready=ready,
        layers=layers,
        critical_path=critical,
        blocked=blocked,
        cycles=cycles,
    )
