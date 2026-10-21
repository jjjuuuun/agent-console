"""그래프 버전 해시: 의미 있는 변경에만 바뀌는 안정 해시."""

import hashlib
import json
from typing import Any

from agent_console_contracts import Graph

HASH_ALGORITHM = "sha256"
"""`graph_hash` 알고리즘(hex 다이제스트)."""

_IGNORED_GRAPH_FIELDS = frozenset({"ui", "project"})
_IGNORED_NODE_FIELDS = frozenset({"position", "layout"})
_IGNORED_EDGE_FIELDS = frozenset({"layout"})


def canonical_graph(graph: Graph) -> dict[str, Any]:
    """해시 계산에 쓰는 정규화된 그래프 문서(JSON 호환 dict).

    정규화 규칙:
      1. 계약 모델로 직렬화(`mode="json"`, 별칭 사용) — 생략한 필드와 기본값을 명시한 필드가 같다.
         정의 모델이 보존하는 모르는 필드는 포함된다.
      2. 표시 전용 필드 제거: 그래프 최상위 `ui`, 노드 `position`·`layout`, 엣지 `layout`
         (화면 배치는 실행 의미가 아니다, design E-3·graph-edges §5.3 S2). 그래프 최상위
         `project`(정의 범위, 계약 0.8.0)도 뺀다 — 팀 구성을 다른 프로젝트로 옮겨도 실행 버전
         고정·resume 해시 비교가 "바뀜"으로 보지 않게 한다(design §UX-P.4).
      3. `nodes`, `edges`는 `id` 기준으로 정렬(같은 id끼리는 정규 JSON 문자열 순) —
         목록 안 순서는 의미가 없다. 다른 목록(`inputs`, `labels` 등)의 순서는 유지한다.
    """
    doc = graph.model_dump(mode="json", by_alias=True)
    for key in _IGNORED_GRAPH_FIELDS:
        doc.pop(key, None)
    nodes = [
        {k: v for k, v in node.items() if k not in _IGNORED_NODE_FIELDS}
        for node in doc.get("nodes", [])
    ]
    edges = [
        {k: v for k, v in edge.items() if k not in _IGNORED_EDGE_FIELDS}
        for edge in doc.get("edges", [])
    ]
    doc["nodes"] = sorted(nodes, key=_sort_key)
    doc["edges"] = sorted(edges, key=_sort_key)
    return doc


def graph_hash(graph: Graph) -> str:
    """그래프 버전 해시(sha256 hex, 64자).

    키 순서·노드/엣지 목록 순서·레이아웃 좌표(`position`)·화면 배치(`layout`)·편집기 상태(`ui`)·
    정의 범위(`project`)가 달라도 같다.
    규칙은 `canonical_graph` 참고. 정규 JSON은 키 정렬, 구분자 공백 없음, `ensure_ascii=False`
    UTF-8이다.
    """
    data = _dumps(canonical_graph(graph)).encode("utf-8")
    return hashlib.new(HASH_ALGORITHM, data).hexdigest()


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sort_key(item: dict[str, Any]) -> tuple[str, str]:
    return (str(item.get("id", "")), _dumps(item))
