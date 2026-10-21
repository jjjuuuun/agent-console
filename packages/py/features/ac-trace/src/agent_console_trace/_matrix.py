"""여러 실행의 "누가 누구에게 몇 번" 집계(agent_bench `log_store` handoff edges 질의 이식).

agent_bench는 `handoff` 범주 이벤트의 from·to·via를 (보낸 쪽, 받는 쪽, via)로 묶어 횟수 내림차순으로
보여 줬다. 여기서는 그 입력을 위임 흐름(`Trace`)의 명시 관계로 바꿨다:
넘김 화살표(`TraceLink`, via = 연결 종류 id)와 부모 → 자식 위임 span(via = span 종류).
"""

from collections import Counter
from collections.abc import Collection, Iterable

from agent_console_contracts import HandoffCount, HandoffMatrix, Trace, TraceSpan

from ._build import SPAN_KIND_DELEGATED


def _who(span: TraceSpan) -> str | None:
    return span.actor or span.node_id


def handoff_matrix(
    traces: Iterable[Trace],
    *,
    child_kinds: Collection[str] = (SPAN_KIND_DELEGATED,),
    include_links: bool = True,
    limit: int | None = None,
) -> HandoffMatrix:
    """여러 실행의 위임·넘기기를 (넘긴 쪽, 받은 쪽, 종류)별로 센다.

    - 넘긴 쪽·받은 쪽 = span의 `actor`(에이전트 정의 id), 없으면 `node_id`.
      둘 다 없으면 세지 않는다.
    - 넘김 화살표 하나 = 1회(`kind` = 링크의 연결 종류 id, 모르면 None). 위임자 → 호출 NodeRun
      링크(독립 위임 `delegate` 등)도 여기서 연결 종류 id로 센다.
    - 부모가 있는 span 중 `child_kinds`에 든 종류 하나 = 1회(`kind` = span 종류).

    Args:
        traces: 집계할 실행들의 위임 흐름.
        child_kinds: 부모 → 자식 관계를 셀 span 종류(기본: 위임 span).
        include_links: 넘김 화살표를 셀지.
        limit: 결과 칸 수 한도(많은 순). None이면 전부.

    Returns:
        횟수 내림차순(같으면 넘긴 쪽·받은 쪽·종류 순) 칸 목록과 집계한 실행 수.
    """
    counts: Counter[tuple[str, str, str | None]] = Counter()
    runs = 0
    for trace in traces:
        runs += 1
        spans = {s.id: s for s in trace.spans}
        if include_links:
            for link in trace.links:
                source, target = spans.get(link.source), spans.get(link.target)
                if source is None or target is None:
                    continue
                a, b = _who(source), _who(target)
                if a is not None and b is not None:
                    counts[(a, b, link.kind)] += 1
        for span in trace.spans:
            if span.kind not in child_kinds or span.parent_id is None:
                continue
            parent = spans.get(span.parent_id)
            if parent is None:
                continue
            a, b = _who(parent), _who(span)
            if a is not None and b is not None:
                counts[(a, b, span.kind)] += 1
    cells = sorted(
        (HandoffCount(source=a, target=b, kind=k, count=n) for (a, b, k), n in counts.items()),
        key=lambda c: (-c.count, c.source, c.target, c.kind or ""),
    )
    if limit is not None:
        cells = cells[: max(limit, 0)]
    return HandoffMatrix(cells=cells, runs=runs)
