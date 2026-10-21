"""agent-console-settings: 설정 층 병합과 값별 출처 추적, 문서 비교(순수 로직, 사내 의존 없음,
외부 의존은 문서 비교용 jsonpatch 하나).

층(공통 → 팀 구성 → 에이전트 → 노드 등)은 호출자가 넘기는 **데이터**이고, 필드별 병합 규칙도
데이터(스키마 `x-merge`, 사용자 규칙 `rules`)다. 이 패키지는 필드 이름을 모른다.

공개 API:
    - ``Layer(id, label, value, source)``, ``resolve_layers(layers, *, schema, rules, strategies)
      -> Resolved{value, provenance, layers, issues}``: 층 병합 + 위치별 출처.
    - ``rule_for(pointer, incoming, *, schema, rules)``: 위치에 쓸 전략 이름과 근거.
    - 전략: ``MergeStrategy``(프로토콜), ``MergeContext``, ``TracedValue``, ``StrategyTable``
      (``register``·``freeze``·``copy``), ``default_strategies()``, ``DEFAULT_STRATEGIES``,
      기본 전략 함수 ``replace``·``merge``·``append``·``union``·``intersect``.
    - 넓힘 경고: ``find_widenings(layers, *, checks, schema, ...) -> list[Widening]``,
      ``DEFAULT_WIDEN_CHECKS``(``subset``·``path_subset``·``order``).
    - 층 편집: ``set_at``(이 층에서 덮어쓰기), ``unset_at``(상속으로 되돌리기), ``get_at``,
      ``split_pointer``·``join_pointer``·``escape_token``·``unescape_token``, ``MISSING``.
    - 스키마 주석: ``schema_annotation(schema, pointer, key)``, ``MERGE_ANNOTATION``(``x-merge``),
      ``WIDEN_ANNOTATION``(``x-widen``).
    - 문서 비교: ``diff_documents(before, after, *, before_secrets, after_secrets, mask)
      -> list[DocumentChange{op, path, before, after, secret}]``(경로는 원래 문서 기준, 비밀 위치는
      ``mask``), ``diff_digests({경로: 해시}, {경로: 해시}) -> list[DigestChange]``.
"""

from agent_console_settings._diff import (
    DEFAULT_SECRET_MASK,
    DigestChange,
    DocumentChange,
    diff_digests,
    diff_documents,
)
from agent_console_settings._pointer import (
    MISSING,
    PointerError,
    escape_token,
    get_at,
    join_pointer,
    set_at,
    split_pointer,
    unescape_token,
    unset_at,
)
from agent_console_settings._resolve import (
    MERGE_ANNOTATION,
    Layer,
    LayerInfo,
    Resolved,
    resolve_layers,
    rule_for,
)
from agent_console_settings._schema import schema_annotation
from agent_console_settings._strategies import (
    DEFAULT_STRATEGIES,
    MergeContext,
    MergeIssue,
    MergeStrategy,
    StrategyTable,
    append,
    default_strategies,
    intersect,
    merge,
    replace,
    union,
)
from agent_console_settings._traced import TracedValue
from agent_console_settings._widen import (
    DEFAULT_WIDEN_CHECKS,
    WIDEN_ANNOTATION,
    WidenCheck,
    Widening,
    find_widenings,
)

__all__ = [
    "DEFAULT_SECRET_MASK",
    "DEFAULT_STRATEGIES",
    "DEFAULT_WIDEN_CHECKS",
    "MERGE_ANNOTATION",
    "MISSING",
    "WIDEN_ANNOTATION",
    "DigestChange",
    "DocumentChange",
    "Layer",
    "LayerInfo",
    "MergeContext",
    "MergeIssue",
    "MergeStrategy",
    "PointerError",
    "Resolved",
    "StrategyTable",
    "TracedValue",
    "WidenCheck",
    "Widening",
    "append",
    "default_strategies",
    "diff_digests",
    "diff_documents",
    "escape_token",
    "find_widenings",
    "get_at",
    "intersect",
    "join_pointer",
    "merge",
    "replace",
    "resolve_layers",
    "rule_for",
    "schema_annotation",
    "set_at",
    "split_pointer",
    "unescape_token",
    "union",
    "unset_at",
]
