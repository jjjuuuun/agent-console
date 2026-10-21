"""두 JSON 문서 비교(design §2R.9): jsonpatch(RFC 6902) 패치 → 사람이 읽는 변경 목록.

jsonpatch의 패치는 **차례로 적용**하는 형식이라 경로가 중간 상태 기준이다(앞에서 목록 원소를 지우면
뒤 경로의 번호가 당겨진다). 화면은 경로를 "그 버전 문서"에서 찾아 이름을 붙이므로, 여기서는 패치를
직접 적용하며 목록 원소마다 원래 위치를 따라가 경로를 **원래 문서 기준**으로 바꾼다:

- ``remove``: 이전 문서(`before`) 기준 경로.
- ``add``: 이후 문서(`after`) 기준 경로.
- ``replace``: 이전 문서 기준 경로(이전 문서에 없던 원소 안이면 이후 문서 기준).

jsonpatch의 ``move``는 ``remove`` + ``add``로, ``copy``는 ``add``로 바꾼다.

비밀 위치(호출자가 문서별 JSON Pointer로 넘긴다)는 비교 전에 내용 해시를 담은 표식으로 바꿔 둔다.
그래서 비밀 값이 바뀐 것은 알 수 있지만 결과에는 값 대신 ``mask``만 나온다. 표식 원문(해시)도
결과에 나오지 않는다.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

import jsonpatch  # type: ignore[import-untyped]

from agent_console_settings._pointer import (
    MISSING,
    PointerError,
    get_at,
    join_pointer,
    set_at,
    split_pointer,
)

__all__ = [
    "DEFAULT_SECRET_MASK",
    "DigestChange",
    "DocumentChange",
    "diff_digests",
    "diff_documents",
]

type ChangeOp = Literal["add", "remove", "replace"]

DEFAULT_SECRET_MASK = "***"
"""비밀 위치 값 대신 내보내는 문자열."""

_SEAL_PREFIX = "\x00agent-console-secret:"


@dataclass(frozen=True, slots=True)
class DocumentChange:
    """문서 변경 하나.

    Attributes:
        op: ``add`` | ``remove`` | ``replace``.
        path: RFC 6901 JSON Pointer(``remove``·``replace`` = 이전 문서 기준,
            ``add`` = 이후 문서 기준).
        before: 이전 값(``add``면 ``MISSING``).
        after: 새 값(``remove``면 ``MISSING``).
        secret: 이 위치 자체가 비밀이라 ``before``·``after``가 가린 값(``mask``)이다.
            값 안쪽 일부만 비밀이면 False이고 그 부분만 ``mask``로 바뀌어 있다.
    """

    op: ChangeOp
    path: str
    before: Any = MISSING
    after: Any = MISSING
    secret: bool = False


@dataclass(frozen=True, slots=True)
class DigestChange:
    """해시로만 비교한 항목(본문 파일 등) 하나. 한쪽이 None이면 추가·삭제."""

    path: str
    before: str | None
    after: str | None


def diff_digests(before: Mapping[str, str], after: Mapping[str, str]) -> list[DigestChange]:
    """`{경로: 해시}` 두 개를 비교한다(경로 순). 해시가 같은 항목은 빠진다."""
    out: list[DigestChange] = []
    for path in sorted(set(before) | set(after)):
        old, new = before.get(path), after.get(path)
        if old != new:
            out.append(DigestChange(path, old, new))
    return out


def diff_documents(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    before_secrets: Iterable[str] = (),
    after_secrets: Iterable[str] = (),
    mask: str = DEFAULT_SECRET_MASK,
) -> list[DocumentChange]:
    """두 문서의 변경 목록(jsonpatch가 만든 순서).

    Args:
        before: 이전 문서(JSON 객체). 바꾸지 않는다.
        after: 이후 문서(JSON 객체). 바꾸지 않는다.
        before_secrets: 이전 문서의 비밀 위치(JSON Pointer). 없는 위치·잘못된 포인터는 무시한다.
        after_secrets: 이후 문서의 비밀 위치.
        mask: 비밀 값 대신 쓸 값.

    Returns:
        `DocumentChange` 목록. 두 문서가 같으면 빈 목록.
    """
    sealed_before = _seal(before, before_secrets)
    sealed_after = _seal(after, after_secrets)
    ops: list[dict[str, Any]] = jsonpatch.make_patch(sealed_before, sealed_after).patch
    tracker = _Tracker(sealed_before)
    for op in ops:
        tracker.apply(op)
    return [_reveal(rec, mask) for rec in tracker.finish()]


# ---------------------------------------------------------------- 비밀 표식


def _seal(document: Mapping[str, Any], pointers: Iterable[str]) -> Any:
    doc: Any = copy.deepcopy(dict(document))
    # 바깥 위치를 먼저 바꾸면 안쪽 위치는 문자열 안이라 건너뛴다(어느 순서든 값은 새지 않는다).
    for pointer in sorted(set(pointers), key=len):
        try:
            value = get_at(doc, pointer)
            if value is MISSING:
                continue
            doc = set_at(doc, pointer, _seal_token(value)) if pointer else _seal_token(value)
        except PointerError:
            continue
    return doc


def _seal_token(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return _SEAL_PREFIX + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_sealed(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(_SEAL_PREFIX)


def _unseal(value: Any, mask: str) -> Any:
    if _is_sealed(value):
        return mask
    if isinstance(value, dict):
        return {k: _unseal(v, mask) for k, v in value.items()}
    if isinstance(value, list):
        return [_unseal(v, mask) for v in value]
    return value


# ---------------------------------------------------------------- 경로 추적


class _Slot:
    """목록 원소 하나(또는 루트)의 원래 위치(이전 문서)와 마지막 위치(이후 문서)."""

    __slots__ = ("after", "before")

    def __init__(self, before: str | None) -> None:
        self.before = before
        self.after: str | None = None


@dataclass
class _Record:
    op: ChangeOp
    slot: _Slot
    suffix: tuple[str, ...]
    before: Any = MISSING
    after: Any = MISSING
    path: str | None = field(default=None)


def _shadow(value: Any, before: str | None) -> Any:
    """값과 같은 모양의 그림자: 객체 → {키: 그림자}, 목록 → [(슬롯, 그림자)], 그 밖 → None."""
    if isinstance(value, dict):
        return {
            k: _shadow(v, None if before is None else join_pointer(before, k))
            for k, v in value.items()
        }
    if isinstance(value, list):
        out = []
        for i, v in enumerate(value):
            ptr = None if before is None else join_pointer(before, i)
            out.append((_Slot(ptr), _shadow(v, ptr)))
        return out
    return None


class _Tracker:
    """패치를 차례로 적용하며 각 연산 위치의 원래 경로를 기록한다."""

    def __init__(self, document: Any) -> None:
        self.root = _Slot("")
        self.doc: Any = copy.deepcopy(document)
        self.shadow: Any = _shadow(self.doc, "")
        self.records: list[_Record] = []

    # ---- 위치 찾기
    def _parent(self, pointer: str) -> tuple[Any, Any, _Slot, tuple[str, ...], str]:
        tokens = split_pointer(pointer)
        node, shadow, slot = self.doc, self.shadow, self.root
        suffix: tuple[str, ...] = ()
        for token in tokens[:-1]:
            if isinstance(node, list):
                index = int(token)
                slot, shadow = shadow[index]
                node, suffix = node[index], ()
            else:
                node, shadow, suffix = node[token], shadow[token], (*suffix, token)
        return node, shadow, slot, suffix, tokens[-1]

    def _remove(self, pointer: str) -> Any:
        node, shadow, slot, suffix, last = self._parent(pointer)
        if isinstance(node, list):
            index = int(last)
            own, _ = shadow.pop(index)
            value = node.pop(index)
            self.records.append(_Record("remove", own, (), before=value))
        else:
            value = node.pop(last)
            shadow.pop(last)
            self.records.append(_Record("remove", slot, (*suffix, last), before=value))
        return value

    def _add(self, pointer: str, value: Any) -> None:
        if pointer == "":
            self._replace(pointer, value)
            return
        node, shadow, slot, suffix, last = self._parent(pointer)
        if isinstance(node, list):
            index = len(node) if last == "-" else int(last)
            own = _Slot(None)
            node.insert(index, copy.deepcopy(value))
            shadow.insert(index, (own, _shadow(value, None)))
            self.records.append(_Record("add", own, (), after=value))
            return
        if last in node:  # 있는 키에 add = 교체(RFC 6902 4.1)
            self._replace(pointer, value)
            return
        node[last] = copy.deepcopy(value)
        shadow[last] = _shadow(value, None)
        self.records.append(_Record("add", slot, (*suffix, last), after=value))

    def _replace(self, pointer: str, value: Any) -> None:
        if pointer == "":
            self.records.append(_Record("replace", self.root, (), before=self.doc, after=value))
            self.doc = copy.deepcopy(value)
            self.shadow = _shadow(self.doc, None)
            return
        node, shadow, slot, suffix, last = self._parent(pointer)
        if isinstance(node, list):
            index = int(last)
            own = shadow[index][0]
            self.records.append(_Record("replace", own, (), before=node[index], after=value))
            node[index] = copy.deepcopy(value)
            shadow[index] = (own, _shadow(value, None))
        else:
            self.records.append(
                _Record("replace", slot, (*suffix, last), before=node[last], after=value)
            )
            node[last] = copy.deepcopy(value)
            shadow[last] = _shadow(value, None)

    def apply(self, op: Mapping[str, Any]) -> None:
        kind = op["op"]
        if kind == "add":
            self._add(op["path"], op["value"])
        elif kind == "remove":
            self._remove(op["path"])
        elif kind == "replace":
            self._replace(op["path"], op["value"])
        elif kind == "move":
            self._add(op["path"], self._remove(op["from"]))
        elif kind == "copy":
            self._add(op["path"], copy.deepcopy(get_at(self.doc, op["from"])))
        # "test"는 바꾸는 것이 없다.

    # ---- 마무리
    def _mark_after(self, shadow: Any, pointer: str) -> None:
        if isinstance(shadow, dict):
            for key, child in shadow.items():
                self._mark_after(child, join_pointer(pointer, key))
        elif isinstance(shadow, list):
            for index, (slot, child) in enumerate(shadow):
                here = join_pointer(pointer, index)
                slot.after = here
                self._mark_after(child, here)

    def finish(self) -> list[_Record]:
        """원래 경로를 채운 기록(경로를 정할 수 없는 기록 = 더하고 다시 지운 것은 뺀다)."""
        self.root.after = ""
        self._mark_after(self.shadow, "")
        out: list[_Record] = []
        for rec in self.records:
            before = None if rec.slot.before is None else join_pointer(rec.slot.before, *rec.suffix)
            after = None if rec.slot.after is None else join_pointer(rec.slot.after, *rec.suffix)
            if rec.op == "remove":
                rec.path = before
            elif rec.op == "add":
                rec.path = after
            else:
                rec.path = before if before is not None else after
            if rec.path is not None:
                out.append(rec)
        return out


def _reveal(rec: _Record, mask: str) -> DocumentChange:
    secret = _is_sealed(rec.before) or _is_sealed(rec.after)
    before = rec.before if rec.before is MISSING else _unseal(rec.before, mask)
    after = rec.after if rec.after is MISSING else _unseal(rec.after, mask)
    if secret:
        before = before if before is MISSING else mask
        after = after if after is MISSING else mask
    assert rec.path is not None
    return DocumentChange(rec.op, rec.path, before=before, after=after, secret=secret)
