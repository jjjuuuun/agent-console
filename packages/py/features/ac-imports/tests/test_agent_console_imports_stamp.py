"""요청 `project` → 가져온 정의의 범위 필드(design §UX-P.2, 5.2R.31). 생략 = 공용(지금과 같음)."""

from __future__ import annotations

from agent_console_contracts import (
    ConflictPolicy,
    ImportCandidate,
    ImportRequest,
    ImportSelection,
    ImportSourceDescriptor,
)
from agent_console_imports import (
    SCOPE_FIELD,
    ImportItem,
    ImportService,
    ScanResult,
    request_stamp,
)
from agent_console_imports.testing import MemoryDefinitionWriter


class _Two:
    descriptor = ImportSourceDescriptor(id="mem", title="메모리")

    def scan(self) -> ScanResult:
        def item(cid: str, kind: str, doc: dict[str, object]) -> ImportItem:
            cand = ImportCandidate(id=cid, path=cid, kind=kind, name=cid, suggested_id=cid)
            return ImportItem(cand, doc)

        return ScanResult(
            root=None,
            items=[
                item("a", "agent", {"name": "A", "project": "from-source"}),
                item("r", "resource", {"type": "instruction", "name": "R", "config": {}}),
            ],
        )


def _request(project: str | None = None, policy: ConflictPolicy = "skip") -> ImportRequest:
    picks = [ImportSelection(candidate_id=c, on_conflict=policy) for c in ("a", "r")]
    return ImportRequest(source="mem", items=picks, project=project)


def test_request_project_is_stamped_on_written_items() -> None:
    store = MemoryDefinitionWriter()
    result = ImportService([_Two()], store).apply(_request("app"))
    assert [i.action for i in result.items] == ["created", "created"]
    assert store.documents[("agent", "a")][SCOPE_FIELD] == "app"
    assert store.documents[("resource", "r")][SCOPE_FIELD] == "app"


def test_without_project_documents_are_unchanged() -> None:
    store = MemoryDefinitionWriter()
    ImportService([_Two()], store).apply(_request())
    assert store.documents[("agent", "a")][SCOPE_FIELD] == "from-source"
    assert SCOPE_FIELD not in store.documents[("resource", "r")]


def test_rename_and_overwrite_stamp_skip_does_not() -> None:
    store = MemoryDefinitionWriter()
    service = ImportService([_Two()], store)
    service.apply(_request())
    skipped = service.apply(_request("app"))
    assert {i.action for i in skipped.items} == {"skipped"}
    assert SCOPE_FIELD not in store.documents[("resource", "r")]
    renamed = service.apply(_request("app", "rename"))
    assert [i.target_id for i in renamed.items] == ["a-2", "r-2"]
    assert store.documents[("resource", "r-2")][SCOPE_FIELD] == "app"
    service.apply(_request("p2", "overwrite"))
    assert store.documents[("agent", "a")][SCOPE_FIELD] == "p2"


def test_explicit_stamp_wins_and_none_removes() -> None:
    req = _request("app")
    assert request_stamp(req) == {"project": "app"}
    assert request_stamp(req, {"project": None, "id": "x", "labels": ["l"]}) == {
        "project": None,
        "labels": ["l"],
    }
    store = MemoryDefinitionWriter()
    ImportService([_Two()], store).apply(req, stamp={"project": None})
    assert SCOPE_FIELD not in store.documents[("agent", "a")]
