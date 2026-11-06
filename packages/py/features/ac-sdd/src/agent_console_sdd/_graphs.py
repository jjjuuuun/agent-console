"""작업 의존 그래프 공용 도구(파싱의 순환 이슈와 계획이 같은 계산을 쓴다)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

__all__ = ["dependency_cycles"]


def dependency_cycles(keys: Sequence[str], deps: Mapping[str, Sequence[str]]) -> list[list[str]]:
    """강하게 연결된 묶음 중 순환인 것(크기 2 이상 또는 자기 자신 의존). 반복형 Tarjan.

    Args:
        keys: 작업 키(이 순서로 탐색을 시작한다 — 결과 순서가 문서 순서를 따른다).
        deps: 작업 키 → 의존 작업 키. `keys`에 없는 키를 가리켜도 된다(그 키는 잎으로 본다).

    Returns:
        순환 묶음 목록. 묶음 안 순서는 탐색 순서(첫 원소가 먼저 찾은 작업).
    """
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    found: list[list[str]] = []
    counter = 0
    for root in keys:
        if root in index:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, child_i = work[-1]
            if child_i == 0:
                index[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            children = deps.get(node, ())
            if child_i < len(children):
                work[-1] = (node, child_i + 1)
                child = children[child_i]
                if child not in index:
                    work.append((child, 0))
                elif child in on_stack:
                    low[node] = min(low[node], index[child])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                comp: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                if len(comp) > 1 or node in deps.get(node, ()):
                    comp.reverse()
                    found.append(comp)
    return found
