"""스펙 저장소(design §6R.1.2·§6R.1.4, §6R.18 Q4·Q8): 만들기·틀 독립·문서 본문·상태 전환·작업
고치기(줄 해시 충돌)·틀로 저장."""

from __future__ import annotations

import json
from typing import Any

import pytest

from agent_console_contracts.sdd import SpecDocument
from agent_console_sdd import (
    DocumentChangedError,
    DocumentExistsError,
    DocumentMissingError,
    SpecNotFoundError,
    TaskChangedError,
    TemplateExistsError,
    TransitionDeniedError,
    blank_documents,
    find_task,
    instantiate,
    line_hash,
    spec_to_template,
)
from agent_console_sdd.testing import TEST_SPEC_KIND, TEST_TEMPLATE_KIND, memory_repository
from agent_console_store import InMemoryDefinitionStore, VersionConflict

TEMPLATE: dict[str, Any] = {
    "kind": TEST_TEMPLATE_KIND,
    "id": "basic",
    "name": "요구 → 설계 → 작업",
    "description": "틀 설명",
    "documents": [
        {"id": "req", "title": "요구", "file": "req.md", "roles": ["requirements"]},
        {"id": "design", "title": "설계", "file": "design.md"},
        {"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]},
    ],
    "rules": {
        "document_states": [
            {"id": "draft"},
            {"id": "review"},
            {"id": "approved", "on_edit": {"to": "draft"}},
        ],
        "initial_document_state": "draft",
        "transitions": [
            {"from": "draft", "to": "review", "by": ["human", "run"]},
            {"from": "review", "to": "approved", "by": ["human"]},
            {"from": "*", "to": "draft", "by": ["human"]},
        ],
        "plugin_option": {"kept": True},
    },
    "content": {"file": "req.md"},
}
TASKS = "# 작업\n\n## 1단계\n\n- [ ] 1.1 뼈대 [owner: be]\n- [ ] 1.2 화면 [depends: 1.1]\n"


def _repo(**kw: Any) -> Any:
    repo = memory_repository(clock=lambda: 1000.0, **kw)
    created = repo.store.create(TEST_TEMPLATE_KIND, TEMPLATE)
    repo.store.write_files(
        TEST_TEMPLATE_KIND,
        "basic",
        {"req.md": b"**R1** a\n", "tasks.md": TASKS.encode()},
        expected_version=created.version_hash,
    )
    return repo


def test_create_from_template_is_independent() -> None:
    repo = _repo()
    stored = repo.create(name="Payments v2", template="basic")
    assert stored.id == "payments-v2"
    spec = stored.spec
    assert [d.id for d in spec.documents] == ["req", "design", "tasks"]
    assert all(d.state == "draft" for d in spec.documents)
    assert stored.document["rules"]["plugin_option"] == {"kept": True}  # 모르는 키 보존
    # 스펙 파일에 틀 id·종류가 없다(출처는 버전 메시지에만).
    assert "basic" not in json.dumps(stored.document)
    assert TEST_TEMPLATE_KIND not in json.dumps(stored.document)
    versions = repo.store.list_versions(TEST_SPEC_KIND, stored.id)
    assert any(f"{TEST_TEMPLATE_KIND}/basic @" in v.message for v in versions)
    files = repo.read_files(stored.id)
    assert files["tasks.md"] == TASKS.encode()
    assert files["design.md"] == b""  # 틀에 본문이 없던 문서는 빈 파일

    # 틀을 고쳐도 스펙은 그대로다.
    tpl = repo.get_template("basic")
    changed = dict(tpl.document, name="바뀐 틀", rules={})
    repo.store.save(TEST_TEMPLATE_KIND, changed, expected_version=tpl.version_hash)
    repo.store.write_files(
        TEST_TEMPLATE_KIND,
        "basic",
        {"tasks.md": b"- [ ] 9 other\n"},
        expected_version=repo.get_template("basic").version_hash,
    )
    again = repo.get(stored.id)
    assert again.document == stored.document
    assert repo.read_files(stored.id)["tasks.md"] == TASKS.encode()

    second = repo.create(name="Payments v2", template="basic")
    assert second.id == "payments-v2-2"
    with pytest.raises(SpecNotFoundError):
        repo.create(name="x", template="nope")


def test_blank_spec_uses_package_data_and_override() -> None:
    repo = _repo()
    stored = repo.create(name="빈 것", id="blank")
    assert [d.model_dump() for d in stored.spec.documents] == [
        d.model_dump() for d in blank_documents()
    ]
    assert stored.document.get("rules") is None
    custom = _repo(blank_documents=[SpecDocument(id="rfc", title="RFC", file="rfc.md")])
    other = custom.create(name="RFC 하나")
    assert other.id != ""  # 이름에 영문이 없으면 종류 이름에서 만든다
    assert [d.id for d in other.spec.documents] == ["rfc"]
    assert custom.read_files(other.id) == {"rfc.md": b""}
    korean = custom.create(name="한글만")
    assert korean.id == "test-spec"


def test_document_read_write_rules() -> None:
    repo = _repo()
    spec_id = repo.create(name="s", template="basic").id
    repo.store.delete_file(
        TEST_SPEC_KIND, spec_id, "design.md", expected_version=repo.get(spec_id).version_hash
    )
    with pytest.raises(DocumentMissingError) as missing:
        repo.read_document(spec_id, "design")
    assert missing.value.details == {"document_id": "design", "file": "design.md"}
    assert repo.read_files(spec_id)["design.md"] is None  # 읽기로 만들지 않는다
    _, made = repo.write_document(spec_id, "design", "# 설계\n", create_only=True)
    with pytest.raises(DocumentExistsError):
        repo.write_document(spec_id, "design", "x", create_only=True)
    with pytest.raises(DocumentChangedError):
        repo.write_document(spec_id, "design", "y", expected_hash="0" * 64)
    _, again = repo.write_document(
        spec_id, "design", "# 설계 v2\n", expected_hash=made.content_hash
    )
    assert repo.read_document(spec_id, "design").content_hash == again.content_hash
    with pytest.raises(SpecNotFoundError):
        repo.read_document(spec_id, "nope")


def test_transitions_by_and_on_edit() -> None:
    repo = _repo()
    spec_id = repo.create(name="s", template="basic").id
    with pytest.raises(TransitionDeniedError) as denied:
        repo.change_document_state(
            spec_id, "design", "approved", by="human"
        )  # draft → approved 없음
    assert denied.value.details["from"] == "draft"
    repo.change_document_state(spec_id, "design", "review", by="run", run_id="r-1")
    with pytest.raises(TransitionDeniedError) as by_mismatch:
        repo.change_document_state(spec_id, "design", "approved", by="run")  # 승인은 사람만
    assert by_mismatch.value.details["by"] == "run"
    stored = repo.change_document_state(spec_id, "design", "approved", by="human", note="ok")
    doc = stored.spec.documents[1]
    assert doc.state == "approved"
    assert doc.state_changed is not None
    assert (doc.state_changed.by, doc.state_changed.at, doc.state_changed.note) == (
        "human",
        1000.0,
        "ok",
    )
    with pytest.raises(VersionConflict):
        repo.change_document_state(spec_id, "design", "draft", by="human", expected_version="stale")
    # 승인된 문서 본문을 고치면 on_edit로 draft가 된다. 같은 본문을 다시 쓰면 그대로다.
    content = repo.read_document(spec_id, "design")
    stored, _ = repo.write_document(spec_id, "design", content.data)
    assert stored.spec.documents[1].state == "approved"
    stored, _ = repo.write_document(spec_id, "design", "바뀐 설계\n", by="agent")
    after = stored.spec.documents[1]
    assert after.state == "draft"
    assert after.state_changed is not None
    assert after.state_changed.by == "agent"


def test_task_patch_line_hash_rules() -> None:
    repo = _repo()
    spec_id = repo.create(name="s", template="basic").id
    task = find_task(repo.load(spec_id).index, "1.2")
    assert task is not None
    seen_hash = task.line_hash

    # 다른 줄(1.1)을 누가 고쳐도 1.2 고치기는 통과한다.
    other = TASKS.replace("[owner: be]", "[owner: qa]") + "- [ ] 1.3 새 작업\n"
    repo.write_document(spec_id, "tasks", other)
    result = repo.patch_task(spec_id, "1.2", expected_line_hash=seen_hash, status="done")
    assert result.task.status == "done"
    text = repo.read_document(spec_id, "tasks").text
    assert text == other.replace("- [ ] 1.2 화면", "- [x] 1.2 화면")
    assert result.content_hash == repo.read_document(spec_id, "tasks").content_hash
    assert result.version_hash == repo.get(spec_id).version_hash

    # 같은 줄이 바뀌었으면 409(최신 줄 포함), 원문은 그대로.
    with pytest.raises(TaskChangedError) as changed:
        repo.patch_task(spec_id, "1.2", expected_line_hash=seen_hash, status="todo")
    current = changed.value.current
    assert current.text == "- [x] 1.2 화면 [depends: 1.1]"
    assert current.line_hash == line_hash(current.text)
    assert changed.value.code == "sdd.task_changed"
    assert repo.read_document(spec_id, "tasks").text == text
    with pytest.raises(TaskChangedError) as gone:
        repo.patch_task(spec_id, "9.9", expected_line_hash=seen_hash, status="done")
    assert gone.value.current.line_hash is None


def test_task_patch_retries_once_on_definition_conflict() -> None:
    repo = _repo()
    spec_id = repo.create(name="s", template="basic").id
    task = find_task(repo.load(spec_id).index, "1.1")
    assert task is not None
    store = repo.store
    real = store.write_files
    calls = {"n": 0}

    def racing(kind: str, id: str, changes: Any, **kw: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:  # 다른 쪽이 먼저 다른 줄을 저장했다
            current = store.get(kind, id).version_hash
            real(kind, id, {"design.md": b"concurrent\n"}, expected_version=current)
        return real(kind, id, changes, **kw)

    store.write_files = racing
    result = repo.patch_task(spec_id, "1.1", expected_line_hash=task.line_hash, status="done")
    store.write_files = real
    assert result.task.status == "done"
    assert calls["n"] == 2  # 첫 시도(그 사이 다른 쪽 저장 → 충돌) + 다시 시도
    assert repo.read_document(spec_id, "design").data == b"concurrent\n"


def test_save_as_template_policies_and_independence() -> None:
    repo = _repo()
    spec_id = repo.create(name="source-spec", template="basic").id
    repo.change_document_state(spec_id, "design", "review", by="human")
    library = InMemoryDefinitionStore([repo.store.kind_info(TEST_TEMPLATE_KIND)])

    first = repo.save_as_template(spec_id, name="My Template", target=library)
    assert (first.template_id, first.status) == ("my-template", "created")
    saved = library.get(TEST_TEMPLATE_KIND, "my-template").document
    assert all("state" not in d and "state_changed" not in d for d in saved["documents"])
    assert spec_id not in json.dumps(saved)
    files = {
        f.path: library.read_file(TEST_TEMPLATE_KIND, "my-template", f.path)
        for f in library.list_files(TEST_TEMPLATE_KIND, "my-template")
    }
    assert files == {"req.md": b"", "design.md": b"", "tasks.md": b""}

    with pytest.raises(TemplateExistsError):
        repo.save_as_template(spec_id, name="My Template", target=library)
    renamed = repo.save_as_template(
        spec_id, name="My Template", on_conflict="rename", target=library
    )
    assert (renamed.template_id, renamed.status) == ("my-template-2", "renamed")
    over = repo.save_as_template(
        spec_id, name="My Template", include_content=True, on_conflict="overwrite", target=library
    )
    assert over.status == "overwritten"
    assert library.read_file(TEST_TEMPLATE_KIND, "my-template", "tasks.md") == TASKS.encode()

    local = repo.save_as_template(spec_id, name="here", id="here")  # 기본 = 같은 공간
    assert local.template_id in repo.template_ids()
    summaries = {s.id: s for s in repo.template_summaries()}
    assert summaries["basic"].documents[0].id == "req"


def test_pure_conversions() -> None:
    draft = instantiate(TEMPLATE, {"req.md": b"r"}, kind="k", id="new", name="새 스펙")
    assert draft.document["kind"] == "k"
    assert draft.document["id"] == "new"
    assert draft.files == {"req.md": b"r", "design.md": b"", "tasks.md": b""}
    assert draft.document["content"] == {"file": "req.md"}
    spec_doc = dict(draft.document)
    spec_doc["documents"][0]["state_changed"] = {"by": "human", "at": 1}
    back = spec_to_template(
        spec_doc, {"req.md": b"r"}, kind="t", id="t1", name="틀", include_content=True
    )
    assert back.files == {"req.md": b"r", "design.md": b"", "tasks.md": b""}
    assert all("state" not in d for d in back.document["documents"])


def test_view_and_summaries() -> None:
    repo = _repo()
    spec_id = repo.create(name="s", template="basic", description="설명").id
    view = repo.view(spec_id)
    assert view.directory == spec_id
    assert [s.id for s in view.task_statuses] == ["todo", "done"]
    assert [s.label for s in view.document_states] == ["draft", "review", "approved"]
    assert len(view.index.tasks) == 2
    nested = memory_repository(directory=".agent-console/specs/")
    assert nested.spec_directory("x") == ".agent-console/specs/x"
    [summary] = repo.summaries()
    assert summary.tasks_total == 2
    assert summary.ready == 1
    assert summary.tasks_done == 0
    assert summary.task_counts == {"todo": 2}
    assert summary.current_stage is not None
    assert summary.current_stage.id == "1단계"
    assert summary.documents[0].state == "draft"
    assert summary.description == "설명"
    repo.delete(spec_id)
    assert repo.summaries() == []
    with pytest.raises(SpecNotFoundError):
        repo.delete(spec_id)


def test_template_store_separate_from_spec_store() -> None:
    """틀 저장소를 따로 주면 틀 목록·틀에서 만들기·틀로 저장이 그 저장소를 쓴다(6R.13)."""
    library = _repo().store
    repo = memory_repository(clock=lambda: 1000.0)
    split = type(repo)(
        repo.store,
        spec_kind=TEST_SPEC_KIND,
        template_kind=TEST_TEMPLATE_KIND,
        template_store=library,
    )
    assert split.template_ids() == ["basic"]
    assert repo.store.list_ids(TEST_TEMPLATE_KIND) == []
    stored = split.create(name="From library", template="basic")
    assert split.store.list_ids(TEST_SPEC_KIND) == [stored.id]
    assert library.list_ids(TEST_SPEC_KIND) == []
    saved = split.save_as_template(stored.id, name="Copy")
    assert saved.template_id in library.list_ids(TEST_TEMPLATE_KIND)
    assert repo.store.list_ids(TEST_TEMPLATE_KIND) == []


def test_template_create_save_delete() -> None:
    """6R.20a: 빈 틀 만들기 → 저장(If-Match, 본문 그대로) → 지우기. 만든 스펙은 틀과 독립."""
    from agent_console_store import AlreadyExists

    repo = memory_repository()
    made = repo.create_template(name="새 틀", taken=["spec-template-x"])
    tpl = made.template
    assert (tpl.documents, tpl.rules.document_states) == ([], None)
    assert made.id == repo.template_ids()[0]
    again = repo.create_template(name="새 틀")
    assert again.id != made.id  # 이름이 같으면 -2
    with pytest.raises(AlreadyExists):
        repo.create_template(name="x", id=made.id)
    assert repo.create_template(name="v", taken=["v"]).id == "v-2"

    store = repo.template_store
    with_file = store.write_file(
        TEST_TEMPLATE_KIND, made.id, "req.md", b"# req\n", expected_version=made.version_hash
    )
    doc = {**with_file.document, "documents": [{"id": "req", "title": "요구", "file": "req.md"}]}
    with pytest.raises(VersionConflict):
        repo.save_template(doc, expected_version="stale")
    saved = repo.save_template(doc, expected_version=with_file.version_hash, message="규칙")
    assert [d.id for d in saved.template.documents] == ["req"]
    assert repo.template_files(made.id) == {"req.md": b"# req\n"}

    spec = repo.create(name="S", template=made.id)
    repo.delete_template(made.id, expected_version=saved.version_hash)
    assert made.id not in repo.template_ids()
    assert repo.get(spec.id).spec.documents[0].id == "req"
    with pytest.raises(SpecNotFoundError):
        repo.delete_template(made.id)
