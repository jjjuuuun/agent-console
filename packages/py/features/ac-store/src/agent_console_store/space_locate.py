"""기록 id → 그 기록이 있는 공간 찾기(`SpaceLocator`, 요청 11/07·11/08 후속).

대화·실행처럼 호스트 DB와 프로젝트 기록 DB(공간)로 나뉘어 저장되는 기록을 id 하나로 찾는다.
이 모듈은 기록 종류를 모른다 - "그 자리에 그 id가 있나"(`has`)를 주입받는다.

- 찾을 자리: 이 프로세스가 아는 공간(`opened`) → 등록 공간 id(`project_ids`, 앞에서 `limit`개,
  중복 제외) → 호스트(None). 공간 포트가 없으면(`spaced`가 거짓) 호스트만 본다.
- 찾은 자리가 하나면 기억해 두고(상한 `remember`, 오래된 것부터 잊는다) 다음에는 그 자리만 다시
  확인한다. 없거나 여럿이면 기억을 지운다.
- `has`가 예외를 내면 그 자리는 없는 것으로 본다(읽을 수 없는 공간은 건너뛴다).
- 결과 해석(없음 = 404, 여럿 = 409)은 호출자가 한다(`find`는 찾은 자리 목록만 돌려준다).

>>> rows = {None: {"a"}, "p1": {"b"}, "p2": {"b", "c"}, "p3": {"c"}}
>>> def has(place, key):
...     return key in rows[place]
>>> loc = SpaceLocator(has, project_ids=lambda: ["p1", "p2", "p3"])
>>> loc.find("a")
[None]
>>> loc.find("b")
['p1', 'p2']
>>> loc.find("c")
['p2', 'p3']
>>> loc.find("z")
[]
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable, Iterable

DEFAULT_LOCATE_LIMIT = 200
"""`SpaceLocator`가 읽는 등록 공간 최대 개수 기본값."""

DEFAULT_LOCATE_REMEMBER = 4096
"""`SpaceLocator`가 기억하는 찾은 자리 최대 개수 기본값."""

_log = logging.getLogger(__name__)


class SpaceLocator:
    """기록 id → 그 기록이 있는 공간(None = 호스트).

    Args:
        has: (자리, id) → 그 자리에 있나. 자리 None = 호스트. 예외 = 없음.
        opened: 이 프로세스가 아는 공간 id(부를 때마다). 먼저 본다.
        project_ids: 등록 공간 id(부를 때마다, 보통 ``projects.lookup``). None이면 아는 공간만.
        limit: ``project_ids``에서 읽는 최대 개수(0 = 아는 공간과 호스트만).
        remember: 기억할 찾은 자리 최대 개수.
        spaced: 공간 포트가 있나(부를 때마다). 거짓이면 호스트만 본다.
        label: 기록 메시지에 붙일 이름(예: ``"대화"``).
    """

    def __init__(
        self,
        has: Callable[[str | None, str], bool],
        *,
        opened: Callable[[], Iterable[str]] = lambda: (),
        project_ids: Callable[[], Iterable[str]] | None = None,
        limit: int = DEFAULT_LOCATE_LIMIT,
        remember: int = DEFAULT_LOCATE_REMEMBER,
        spaced: Callable[[], bool] = lambda: True,
        label: str = "기록",
    ) -> None:
        self._has_raw = has
        self._opened = opened
        self._project_ids = project_ids
        self._limit = max(0, limit)
        self._cap = max(0, remember)
        self._spaced = spaced
        self._label = label
        self._found: OrderedDict[str, str | None] = OrderedDict()
        self._lock = threading.Lock()

    def find(self, item_id: str) -> list[str | None]:
        """그 id가 있는 자리 목록(빈 목록 = 어디에도 없음, 둘 이상 = 모호).

        기억한 자리에 아직 있으면 그 자리 하나만 돌려준다.
        """
        with self._lock:
            known = item_id in self._found
            remembered = self._found.get(item_id)
        if known and self._has(remembered, item_id):
            return [remembered]
        found = [place for place in self.candidates() if self._has(place, item_id)]
        if len(found) == 1:
            self._remember(item_id, found[0])
        else:
            self.forget(item_id)
        return found

    def candidates(self) -> list[str | None]:
        """찾을 자리: 아는 공간 → 등록 id(상한까지, 중복 제외) → 호스트(None)."""
        out: list[str | None] = []
        if self._spaced():
            seen: set[str] = set()
            for space in list(self._opened()):
                if space and space not in seen:
                    seen.add(space)
                    out.append(space)
            if self._project_ids is not None and self._limit > 0:
                try:
                    ids = list(self._project_ids())
                except Exception:
                    _log.exception("%s 위치 찾기: 공간 목록을 읽지 못했습니다", self._label)
                    ids = []
                listed = 0
                for space in ids:
                    if not space or space in seen:
                        continue
                    if listed >= self._limit:
                        _log.info(
                            "%s 위치 찾기: 공간 %d개 중 %d개만 읽었습니다",
                            self._label,
                            len(ids),
                            self._limit,
                        )
                        break
                    seen.add(space)
                    out.append(space)
                    listed += 1
        out.append(None)
        return out

    def forget(self, item_id: str) -> None:
        """기억한 자리를 지운다(없으면 그대로)."""
        with self._lock:
            self._found.pop(item_id, None)

    def _remember(self, item_id: str, place: str | None) -> None:
        if self._cap == 0:
            return
        with self._lock:
            self._found[item_id] = place
            self._found.move_to_end(item_id)
            while len(self._found) > self._cap:
                self._found.popitem(last=False)

    def _has(self, place: str | None, item_id: str) -> bool:
        try:
            return bool(self._has_raw(place, item_id))
        except Exception:
            _log.debug("%s 위치 찾기: %r를 읽지 못했습니다", self._label, place, exc_info=True)
            return False


__all__ = ["DEFAULT_LOCATE_LIMIT", "DEFAULT_LOCATE_REMEMBER", "SpaceLocator"]
