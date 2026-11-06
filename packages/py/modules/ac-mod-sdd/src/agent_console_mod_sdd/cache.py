"""파싱 캐시(design §6R.16 위험 7): 공간·스펙·정의 버전·문서 본문 해시·유효 문법이 같으면 다시
파싱하지 않는다.

작업 목록·계획·추적은 읽을 때마다 문서 원문에서 만든다(K6R-3). 큰 작업 문서에서 화면이 같은 스펙을
여러 번 부르므로(보기·작업·계획·추적) 결과를 보관한다. 키에 본문 해시가 들어가 사람·에이전트가
파일을 직접 고쳐도 바로 다시 파싱한다. 저장하지 않는 메모리 캐시이고 상한(LRU)이 있다.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any

from agent_console_contracts.sdd import EffectiveSyntax, SpecIndex
from agent_console_sdd import (
    CompiledSyntax,
    LoadedSpec,
    SpecRepository,
    compile_syntax,
    parse_spec,
)

type CacheKey = tuple[str, str, str, tuple[tuple[str, str | None], ...], str]


def syntax_fingerprint(syntax: EffectiveSyntax) -> str:
    """유효 문법의 지문(같은 문법 = 같은 값)."""
    text = json.dumps(syntax.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _digest(data: bytes | None) -> str | None:
    return None if data is None else hashlib.sha256(data).hexdigest()


class ParseCache:
    """스펙 파싱 결과 LRU 캐시(스레드 안전).

    Args:
        max_entries: 보관할 결과 수. 0이면 보관하지 않는다.

    >>> cache = ParseCache(1)
    >>> cache.stats()
    {'hits': 0, 'misses': 0, 'entries': 0}
    """

    def __init__(self, max_entries: int) -> None:
        self._max = max(0, max_entries)
        self._items: OrderedDict[CacheKey, SpecIndex] = OrderedDict()
        self._compiled: OrderedDict[str, CompiledSyntax] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def stats(self) -> dict[str, int]:
        """맞음·빗나감 수와 보관 수(테스트·진단용)."""
        with self._lock:
            return {"hits": self.hits, "misses": self.misses, "entries": len(self._items)}

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._compiled.clear()

    def compiled(self, syntax: EffectiveSyntax, fingerprint: str) -> CompiledSyntax:
        """유효 문법 → 컴파일한 문법(정규식 컴파일 결과를 같은 지문끼리 나눠 쓴다)."""
        with self._lock:
            found = self._compiled.get(fingerprint)
            if found is not None:
                self._compiled.move_to_end(fingerprint)
                return found
        made = compile_syntax(syntax)
        if self._max:
            with self._lock:
                self._compiled[fingerprint] = made
                while len(self._compiled) > self._max:
                    self._compiled.popitem(last=False)
        return made

    def get(self, key: CacheKey) -> SpecIndex | None:
        with self._lock:
            found = self._items.get(key)
            if found is None:
                self.misses += 1
                return None
            self.hits += 1
            self._items.move_to_end(key)
            return found

    def put(self, key: CacheKey, index: SpecIndex) -> None:
        if not self._max:
            return
        with self._lock:
            self._items[key] = index
            self._items.move_to_end(key)
            while len(self._items) > self._max:
                self._items.popitem(last=False)


class CachedSpecRepository(SpecRepository):
    """파싱 캐시를 쓰는 ``SpecRepository``(``load``만 바꾼다 — 보기·목록·작업 고치기가 함께 쓴다).

    캐시에서 나온 ``SpecIndex``는 공유 값이다. 호출자는 고치지 말고 ``model_copy(update=…)``로
    새 값을 만든다.

    Args:
        cache: 공유 캐시(모듈 하나에 하나).
        space_key: 캐시 키의 공간 부분(공간 이름, 단독 루트는 빈 문자열).
        kwargs: ``SpecRepository`` 인자 그대로.
    """

    def __init__(self, *args: Any, cache: ParseCache, space_key: str = "", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.cache = cache
        self.space_key = space_key
        self._max_tasks_value: int | None = kwargs.get("max_tasks")
        self._timeout_value: float | None = kwargs.get("timeout_ms")

    def load(self, spec_id: str) -> LoadedSpec:
        stored = self.get(spec_id)
        spec = stored.spec
        files: Mapping[str, bytes | None] = self._files(self.spec_kind, spec_id, spec.documents)
        syntax = self.syntax(spec)
        fingerprint = syntax_fingerprint(syntax)
        compiled = self.cache.compiled(syntax, fingerprint)
        key: CacheKey = (
            self.space_key,
            spec_id,
            stored.version_hash,
            tuple(sorted((name, _digest(data)) for name, data in files.items())),
            fingerprint,
        )
        index = self.cache.get(key)
        if index is None:
            index = parse_spec(
                spec,
                dict(files),
                compiled,
                max_tasks=self._max_tasks_value,
                timeout_ms=self._timeout_value,
            )
            self.cache.put(key, index)
        return LoadedSpec(stored, spec, dict(files), syntax, compiled, index)


__all__ = ["CachedSpecRepository", "ParseCache", "syntax_fingerprint"]
