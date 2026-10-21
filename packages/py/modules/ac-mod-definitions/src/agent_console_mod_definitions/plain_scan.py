"""평문 비밀 점검(``GET /server-info``의 ``warnings`` 기여, design §2R.4·§3R.1.5).

저장된 정의 전부를 훑어 ``secret.plain_found`` 경고(값 없음)로 바꾸고 캐시한다. 경고 = 저장 전
검사(``definitions.checks``)의 평문 이슈 + 문서 전체의 의심 값(``SecretRules.find_suspected``).
정의가 저장(토픽 ``definitions.saved``)·삭제되면 캐시를 버린다.

잠금 규칙(교착·낡은 캐시 방지, 3R.10 QA 후속):
- 계산 잠금(``_compute_lock``)은 계산을 한 번에 하나로 묶는다. 계산은 저장소를 읽는다(저장소 잠금).
- 상태 잠금(``_state_lock``)은 세대 번호와 캐시만 다룬다. **이 잠금 안에서는 저장소를 읽지 않는다.**
  ``invalidate``(저장소가 쓰기 잠금을 쥔 채 부른다)는 상태 잠금만 짧게 잡으므로 교착되지 않는다.
- 계산 결과는 "계산 시작 때의 세대 = 지금 세대"일 때만 담는다. 비교와 대입을 같은 상태 잠금
  안에서 하므로, 그 사이에 무효화가 끼어 낡은 결과가 남는 틈이 없다.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from typing import Any

from agent_console_contracts import Issue, KnownIssueCodes
from agent_console_secret_rules import SecretRules
from agent_console_store import DefinitionCorrupt, DefinitionStore, InvalidIdentifier, NotFound

from .ports import DefinitionCheck

PLAIN_SECRET_MESSAGE = "평문 비밀로 의심되는 값이 있습니다. secret:// 참조로 바꾸세요"


def plain_secret_warnings(
    kind: str,
    item_id: str,
    document: Mapping[str, Any],
    check_issues: Iterable[Issue],
    rules: SecretRules,
    *,
    plain_codes: Collection[str],
) -> list[Issue]:
    """정의 하나의 평문 점검 경고(``secret.plain_found``): 검사의 평문 이슈 + 문서 전체 의심.

    path는 정의 문서 기준 JSON Pointer, details는 ``{kind, id}``. 값은 담지 않는다.
    """
    paths = [i.path or "" for i in check_issues if i.code in plain_codes]
    paths += [f.path for f in rules.find_suspected(dict(document))]
    return [
        Issue(
            severity="warning",
            code=KnownIssueCodes.SECRET_PLAIN_FOUND,
            message=PLAIN_SECRET_MESSAGE,
            path=path or None,
            details={"kind": kind, "id": item_id},
        )
        for path in dict.fromkeys(paths)
    ]


def scan_store(
    store: DefinitionStore,
    *,
    checks: Callable[[], Sequence[DefinitionCheck]],
    rules: Callable[[], SecretRules],
    plain_codes: Collection[str],
    kinds: Iterable[str] | None = None,
) -> list[Issue]:
    """저장소 정의 전부의 평문 점검 경고(읽을 수 없는 파일은 건너뛴다)."""
    current_checks = list(checks())
    current_rules = rules()
    found: list[Issue] = []
    for kind in kinds if kinds is not None else store.kinds():
        for item_id in store.list_ids(kind):
            try:
                stored = store.get(kind, item_id)
            except (NotFound, DefinitionCorrupt, InvalidIdentifier):
                continue
            issues = [i for c in current_checks for i in c.issues(kind, stored.document)]
            found += plain_secret_warnings(
                kind, item_id, stored.document, issues, current_rules, plain_codes=plain_codes
            )
    return found


class PlainSecretScan:
    """평문 점검 결과 캐시. 정의 저장·삭제 때 ``invalidate``한다(맨 처음 읽을 때 계산).

    Args:
        compute: 경고 목록을 계산하는 함수(저장소를 읽는다).
    """

    def __init__(self, compute: Callable[[], list[Issue]]) -> None:
        self._compute = compute
        self._compute_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._generation = 0
        self._cached: list[Issue] | None = None

    def warnings(self) -> list[Issue]:
        """캐시한 경고(없으면 계산). 계산 도중 무효화되면 결과는 돌려주되 담지 않는다."""
        cached = self._read_cache()
        if cached is not None:
            return cached
        with self._compute_lock:
            with self._state_lock:
                cached = None if self._cached is None else list(self._cached)
                generation = self._generation
            if cached is not None:
                return cached
            result = self._compute()
            with self._state_lock:
                if generation == self._generation:
                    self._cached = result
            return list(result)

    def _read_cache(self) -> list[Issue] | None:
        with self._state_lock:
            return None if self._cached is None else list(self._cached)

    def invalidate(self) -> None:
        """캐시를 버린다(상태 잠금만 짧게 잡는다 — 저장소 쓰기 잠금 안에서 불러도 안전)."""
        with self._state_lock:
            self._generation += 1
            self._cached = None


__all__ = ["PLAIN_SECRET_MESSAGE", "PlainSecretScan", "plain_secret_warnings", "scan_store"]
