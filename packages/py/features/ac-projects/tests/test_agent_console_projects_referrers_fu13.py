"""FU.13: 거꾸로 참조 ``find_referrers`` — 종류 이름 없이 주입한 참조 추출로 쓰는 곳을 찾는다."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from agent_console_contracts import KnownIssueCodes
from agent_console_projects import (
    REFERRERS_UNAVAILABLE_MESSAGE,
    find_referrers,
)


def _uses(kind: str, document: Mapping[str, Any]) -> list[tuple[str, str]]:
    """시험용 참조 추출: 문서의 ``uses``가 ``[종류, id]`` 목록(종류 이름을 고정하지 않는다)."""
    return [(str(k), str(i)) for k, i in document.get("uses", [])]


def test_finds_every_kind_that_uses_target_in_document_order() -> None:
    docs = [
        (("zz-team", "t1"), {"uses": [["zz-agent", "a"], ["zz-res", "r"]]}),
        (("zz-team", "t2"), {"uses": [["zz-agent", "b"]]}),
        (("zz-note", "n"), {"uses": [["zz-agent", "a"], ["zz-agent", "a"]]}),
        (("zz-team", "t1"), {"uses": [["zz-agent", "a"]]}),  # 같은 키가 또 와도 한 번
    ]
    scan = find_referrers(("zz-agent", "a"), docs, _uses)
    assert scan.checked is True
    assert scan.keys == (("zz-team", "t1"), ("zz-note", "n"))
    assert scan.warnings == ()


def test_same_id_in_other_kind_is_not_a_reference() -> None:
    docs = [(("zz-team", "t"), {"uses": [["zz-res", "a"]]})]
    assert find_referrers(("zz-agent", "a"), docs, _uses).keys == ()


def test_self_reference_is_skipped() -> None:
    docs = [(("zz-team", "t"), {"uses": [["zz-team", "t"]]})]
    assert find_referrers(("zz-team", "t"), docs, _uses).keys == ()


def test_extractor_error_skips_only_that_document() -> None:
    def flaky(kind: str, document: Mapping[str, Any]) -> list[tuple[str, str]]:
        if document.get("broken"):
            raise ValueError("bad document")
        return _uses(kind, document)

    docs: list[tuple[tuple[str, str], Mapping[str, Any]]] = [
        (("zz-team", "bad"), {"broken": True}),
        (("zz-team", "ok"), {"uses": [["zz-agent", "a"]]}),
    ]
    assert find_referrers(("zz-agent", "a"), docs, flaky).keys == (("zz-team", "ok"),)


def test_without_extractor_documents_are_not_read_and_info_is_reported() -> None:
    read: list[str] = []

    def documents() -> Iterator[tuple[tuple[str, str], Mapping[str, Any]]]:
        read.append("read")
        yield ("zz-team", "t"), {"uses": [["zz-agent", "a"]]}

    scan = find_referrers(("zz-agent", "a"), documents(), None)
    assert read == []  # 참조 추출이 없으면 문서를 읽지 않는다
    assert scan.checked is False
    assert scan.keys == ()
    [issue] = scan.warnings
    assert issue.code == KnownIssueCodes.PROJECT_REFERENCES_UNAVAILABLE
    assert issue.severity == "info"
    assert issue.details == {"kind": "zz-agent", "id": "a"}
    assert issue.message


def test_unavailable_message_is_data() -> None:
    scan = find_referrers(
        ("zz-agent", "a"), [], None, messages={REFERRERS_UNAVAILABLE_MESSAGE: "바꾼 문구"}
    )
    assert scan.warnings[0].message == "바꾼 문구"
