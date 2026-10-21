"""버전 해시 함수 형식과 기본 구현."""

import hashlib
import json
from collections.abc import Callable, Mapping
from typing import Any

type HashFn = Callable[[Mapping[str, Any]], str]
"""정의 문서(JSON 호환 dict) -> 버전 해시. 같은 의미의 문서는 같은 값이어야 한다.

그래프는 ac-graph의 `graph_hash`(키 순서·레이아웃 좌표 무관)를 감싸 주입한다:
`DefinitionKind(..., hash_fn=lambda doc: graph_hash(Graph.model_validate(doc)))`.
"""


def canonical_json(document: Mapping[str, Any]) -> str:
    """키를 정렬하고 공백을 없앤 정규화 JSON."""
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def default_hash(document: Mapping[str, Any]) -> str:
    """기본 해시: 정규화 JSON의 sha256(16진수 64자)."""
    return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()
