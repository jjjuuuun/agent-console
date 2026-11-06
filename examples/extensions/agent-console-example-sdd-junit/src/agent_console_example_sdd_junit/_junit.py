"""JUnit XML 읽기(표준 라이브러리 `xml.etree`).

JUnit 결과 파일에는 DTD가 필요 없으므로 `<!DOCTYPE`·`<!ENTITY`가 든 파일은 거부한다(엔티티 확장
공격 방지). 루트는 `<testsuites>`나 `<testsuite>` 모두 되고, 안에 든 모든 `<testcase>`를 읽는다.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

__all__ = ["JUnitError", "TestCase", "parse_junit"]

_FORBIDDEN = (b"<!doctype", b"<!entity")


class JUnitError(ValueError):
    """JUnit XML로 읽을 수 없다(문법 오류·DTD 포함)."""


@dataclass(frozen=True, slots=True)
class TestCase:
    """테스트 케이스 하나.

    Attributes:
        outcome: `passed`·`failed`·`error`·`skipped`.
        attributes: `<testcase>` 속성(예: `classname`·`name`).
        at: 그 테스트 묶음의 `timestamp`(UNIX 초, 없거나 틀리면 None).
    """

    __test__ = False  # pytest가 테스트 클래스로 모으지 않게

    outcome: str
    attributes: Mapping[str, str] = field(default_factory=dict)
    at: float | None = None


def _timestamp(value: str | None) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _outcome(case: ET.Element) -> str:
    tags = {child.tag for child in case}
    if "error" in tags:
        return "error"
    if "failure" in tags:
        return "failed"
    if "skipped" in tags:
        return "skipped"
    return "passed"


def _cases(node: ET.Element, at: float | None) -> Iterator[TestCase]:
    if node.tag == "testsuite":
        at = _timestamp(node.get("timestamp")) or at
    for child in node:
        if child.tag == "testcase":
            yield TestCase(outcome=_outcome(child), attributes=dict(child.attrib), at=at)
        elif child.tag in ("testsuite", "testsuites"):
            yield from _cases(child, at)


def parse_junit(data: bytes, *, limit: int | None = None) -> list[TestCase]:
    """JUnit XML 바이트 → 테스트 케이스 목록(문서 순서).

    Args:
        data: 파일 내용.
        limit: 최대 케이스 수(넘는 것은 버린다).

    Raises:
        JUnitError: XML 문법 오류, DTD·엔티티 선언 포함, 루트가 `testsuites`·`testsuite`가 아님.
    """
    lowered = data.lower()
    if any(mark in lowered for mark in _FORBIDDEN):
        raise JUnitError("DTD·엔티티 선언이 든 파일은 읽지 않습니다")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise JUnitError(f"XML 문법 오류: {exc}") from None
    if root.tag not in ("testsuites", "testsuite"):
        raise JUnitError(f"JUnit 결과가 아닙니다(루트 {root.tag!r})")
    out: list[TestCase] = []
    for case in _cases(root, None):
        if limit is not None and len(out) >= limit:
            break
        out.append(case)
    return out
