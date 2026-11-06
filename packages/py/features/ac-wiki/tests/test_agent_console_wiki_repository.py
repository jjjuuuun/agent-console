"""`WikiRepository`(7R.8, design §7R.1.2·§7R.6·§7R.18 Q1·Q9·Q13·Q19)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts.wiki import WikiAuthor, WikiIssue, WikiRulesDefinition
from agent_console_wiki import (
    InMemoryWikiHistory,
    LocalWikiPages,
    RulesDocument,
    ScanSearchIndex,
    WikiConflictError,
    WikiHistoryUnavailableError,
    WikiPageExistsError,
    WikiPageNotFoundError,
    WikiPathError,
    WikiRepository,
    WikiRepositoryLimits,
    WikiRuleRejectedError,
    WikiSecretPolicy,
    WikiSecretRejectedError,
    WikiTemplateNotFoundError,
    WikiTooLargeError,
    WikiVersionNotFoundError,
    compile_syntax,
    effective_syntax,
    merge_rules,
)
from agent_console_wiki.testing import FakeClock, MemoryWikiPages

AGENT = WikiAuthor(kind="agent", agent_id="writer", run_id="r1", root_run_id="root", label="기록꾼")
SYNTAX = compile_syntax(effective_syntax())


def _rules(**body: Any) -> Any:
    files = body.pop("files", {})
    rules = WikiRulesDefinition.model_validate(
        {"kind": "wiki-rules", "id": "r", "name": "r", **body}
    )
    return merge_rules(["r"], [RulesDocument("r", rules, files)])


RULES = _rules(
    write_rules=[
        {"id": "no-temp", "deny_patterns": [r"\bTODO\b"], "message": "임시 메모 금지"},
        {
            "id": "agents-cannot-delete",
            "when": {
                "all": [
                    {"path": "/change/op", "op": "eq", "value": "delete"},
                    {"path": "/author/kind", "op": "eq", "value": "agent"},
                ]
            },
            "message": "지울 수 없음",
        },
        {
            "id": "needs-source",
            "applies_to": ["decisions/**"],
            "require": {"all": [{"path": "/page/front_matter/source", "op": "exists"}]},
            "action": "warn",
            "message": "근거",
        },
    ],
    page_templates=[{"id": "d", "file": "d.md", "path": "decisions/{slug}"}],
    files={"d.md": "# {title}\n날짜: {date}\n"},
)


def _repo(
    pages: Any = None, *, history: Any = "mem", clock: FakeClock | None = None, **kw: Any
) -> WikiRepository:
    return WikiRepository(
        pages if pages is not None else MemoryWikiPages(),
        wiki_id="w",
        syntax=SYNTAX,
        rules=kw.pop("rules", RULES),
        history=InMemoryWikiHistory() if history == "mem" else history,
        clock=clock or FakeClock(),
        **kw,
    )


def test_write_read_view_and_history() -> None:
    repo = _repo()
    first = repo.write("index", "# 처음\n[[guide]]\n", message="시작")
    assert first.created
    assert first.version is not None
    assert first.version.op == "create"
    assert first.version.message == "시작"
    second = repo.write("guide", "# 안내\n[[index]]\n", author=AGENT)
    assert second.version is not None
    assert second.version.author.label == "기록꾼"  # 기록 시점 이름을 그대로
    view = repo.view("index")
    assert view.content_hash == first.content_hash
    assert [(link.raw, link.status) for link in view.links] == [("[[guide]]", "ok")]
    assert [b.path for b in view.backlinks] == ["guide"]
    assert view.page.updated_by is not None
    same = repo.write("index", "# 처음\n[[guide]]\n")
    assert not same.changed  # 같은 본문 = 새 버전 없음
    assert [v.version for v in repo.page_history("index").items] == [1]
    listing = repo.list_pages()
    assert [s.path for s in listing.items] == ["guide", "index"]
    assert listing.items[0].updated_by is not None
    assert listing.items[0].updated_by.kind == "agent"


def test_if_hash_and_create_only() -> None:
    repo = _repo()
    made = repo.write("a", "1")
    with pytest.raises(WikiPageExistsError):
        repo.write("a", "2", create_only=True)
    with pytest.raises(WikiConflictError) as caught:
        repo.write("a", "2", if_hash="0" * 64)
    assert caught.value.details["actual"] == made.content_hash
    with pytest.raises(WikiConflictError):
        repo.write("new", "x", if_hash=made.content_hash)
    assert repo.write("a", "2", if_hash=made.content_hash).changed
    with pytest.raises(WikiPathError):
        repo.write("../escape", "x")


def test_rules_reject_and_warn_on_write() -> None:
    repo = _repo()
    with pytest.raises(WikiRuleRejectedError) as caught:
        repo.write("a", "괜찮음\nTODO 남김\n")
    assert caught.value.code == "wiki.rule_rejected"
    assert caught.value.details["rule_id"] == "no-temp"
    assert caught.value.details["lines"] == [2]
    assert repo.current("a") is None
    warned = repo.write("decisions/x", "# 결정\n")
    assert [i.code for i in warned.issues] == ["wiki.rule_warning"]


def test_preview_matches_write_and_has_no_side_effects() -> None:
    search = ScanSearchIndex()
    history = InMemoryWikiHistory()
    repo = _repo(history=history, search=search)
    repo.write("a", "# A\n[[b]]\n")
    files_before = {f.file: f.mtime for f in repo.pages.list([".md"])}
    hashes_before = search.hashes()
    changes_before = len(history.changes(None, limit=100).items)

    ok = repo.preview("a", "# A2\n[[b]] [[a]]\n")
    assert not ok.would_reject
    assert ok.page.title == "A2"
    assert [link.status for link in ok.links] == ["broken", "ok"]
    bad_text = "x\nTODO\n"
    bad = repo.preview("new", bad_text)
    assert bad.would_reject
    assert [r.rule_id for r in bad.rule_results] == ["no-temp"]
    with pytest.raises(WikiRuleRejectedError) as caught:
        repo.write("new", bad_text)
    rejected = [i for i in bad.issues if i.severity == "error"]
    assert caught.value.details["issues"] == [i.model_dump(mode="json") for i in rejected]

    assert {f.file: f.mtime for f in repo.pages.list([".md"])} == files_before
    assert search.hashes() == hashes_before
    assert len(history.changes(None, limit=100).items) == changes_before
    big = _repo(limits=WikiRepositoryLimits(max_page_bytes=4))
    with pytest.raises(WikiTooLargeError):
        big.preview("a", "12345")


def test_secret_scan_per_author() -> None:
    repo = _repo(rules=None)
    secret = "메모\nAPI_KEY=sk-abcdefghijklmnop1234\n"
    with pytest.raises(WikiSecretRejectedError) as caught:
        repo.write("s", secret, author=AGENT)
    assert caught.value.lines == [2]
    warned = repo.write("s", secret)
    assert [i.code for i in warned.issues] == ["wiki.secret_suspect"]
    strict = _repo(rules=None, secrets=WikiSecretPolicy(modes={"user": "reject"}))
    with pytest.raises(WikiSecretRejectedError):
        strict.write("s", secret)


def test_size_and_count_limits() -> None:
    repo = _repo(limits=WikiRepositoryLimits(max_page_bytes=10, max_pages=2))
    with pytest.raises(WikiTooLargeError) as caught:
        repo.write("a", "x" * 11)
    assert caught.value.limit == "max_page_bytes"
    repo.write("a", "1")
    repo.write("b", "2")
    with pytest.raises(WikiTooLargeError) as count:
        repo.write("c", "3")
    assert count.value.limit == "max_pages"
    repo.write("a", "11")  # 있는 페이지 고치기는 된다


class _FrontMatterCheck:
    id = "fm"

    def check(self, subject: Mapping[str, Any], text: str) -> Sequence[WikiIssue]:
        if "owner" in subject["page"]["front_matter"]:
            return []
        return [WikiIssue(severity="error", code="example.missing", message="owner 필요")]


class _Broken:
    id = "boom"

    def check(self, subject: Mapping[str, Any], text: str) -> Sequence[WikiIssue]:
        raise RuntimeError("x")


def test_write_checks_x50() -> None:
    repo = _repo(rules=None, checks=[_FrontMatterCheck(), _Broken()])
    with pytest.raises(WikiRuleRejectedError) as caught:
        repo.write("a", "본문")
    assert caught.value.details["rule_id"] == "fm"
    ok = repo.write("a", "---\nowner: 나\n---\n본문")
    assert [(i.code, i.rule_id) for i in ok.issues] == [("wiki.rule_warning", "boom")]


def test_move_rewrites_backlinks_and_reports_conflicts(tmp_path: Path) -> None:
    pages = LocalWikiPages(tmp_path)
    repo = _repo(pages)
    repo.write("old", "# 옛\n[다른](sub/x.md)\n")
    repo.write("p1", "앞 [[old]] 뒤\r\n\t탭 그대로\n")
    repo.write("p2", "[[old|라벨]] 그리고 [[old#절]]\n")
    repo.write("sub/x", "[위로](../old.md)\n")
    repo.write("p3", "[[old]]\n")
    preview = repo.move("old", "new/place", dry_run=True)
    assert not preview.moved
    assert sorted(r.path for r in preview.rewritten) == ["new/place", "p1", "p2", "p3", "sub/x"]
    assert repo.current("old") is not None

    original = repo.move
    index_holder: dict[str, Any] = {}

    def racing_index() -> Any:
        built = WikiRepository.index(repo)
        if not index_holder:
            index_holder["done"] = True
            (tmp_path / "p3.md").write_text("[[old]] 그사이 고침\n", encoding="utf-8")
        return built

    repo.index = racing_index  # type: ignore[method-assign]
    result = original("old", "new/place", author=AGENT)
    assert result.moved
    assert result.conflicts == ["p3"]
    assert sorted(r.path for r in result.rewritten) == ["new/place", "p1", "p2", "sub/x"]
    assert (tmp_path / "p1.md").read_bytes() == "앞 [[new/place]] 뒤\r\n\t탭 그대로\n".encode()
    assert (tmp_path / "p2.md").read_text(encoding="utf-8") == (
        "[[new/place|라벨]] 그리고 [[new/place#절]]\n"
    )
    assert (tmp_path / "sub/x.md").read_text(encoding="utf-8") == "[위로](../new/place.md)\n"
    assert (tmp_path / "new/place.md").read_text(encoding="utf-8") == "# 옛\n[다른](../sub/x.md)\n"
    assert not (tmp_path / "old.md").exists()
    history = repo.page_history("old")
    assert history.items[0].op == "move_out"
    assert history.items[0].to == "new/place"
    moved_in = repo.page_history("new/place").items[0]
    assert (moved_in.op, moved_in.from_) == ("move_in", "old")
    assert repo.page_history("p1").items[0].author.agent_id == "writer"
    with pytest.raises(WikiPageExistsError):
        repo.move("p1", "p2")


def test_move_rejected_by_rule() -> None:
    no_agent_moves = _rules(
        write_rules=[
            {
                "id": "no-move",
                "when": {"all": [{"path": "/change/op", "op": "eq", "value": "move"}]},
                "message": "옮기기 금지",
            }
        ]
    )
    repo = _repo(rules=no_agent_moves)
    repo.write("a", "x")
    with pytest.raises(WikiRuleRejectedError):
        repo.move("a", "b")


def test_delete_restore_and_deleted_page_history() -> None:
    repo = _repo()
    repo.write("a", "v1")
    repo.write("a", "v2")
    with pytest.raises(WikiRuleRejectedError):
        repo.delete("a", author=AGENT)
    gone = repo.delete("a")
    assert gone.version is not None
    assert gone.version.op == "delete"
    with pytest.raises(WikiPageNotFoundError) as caught:
        repo.read("a")
    assert caught.value.has_history
    assert caught.value.details == {"path": "a", "has_history": True}
    assert [v.op for v in repo.page_history("a").items] == ["delete", "update", "create"]
    assert repo.version("a", 3)[1] == b"v2"  # 지우기 버전은 지우기 직전 본문
    restored = repo.restore("a", 1)
    assert restored.created
    assert restored.version is not None
    assert restored.version.op == "restore"
    assert repo.read("a").data == b"v1"
    with pytest.raises(WikiVersionNotFoundError):
        repo.version("a", 99)
    with pytest.raises(WikiPageNotFoundError) as none:
        repo.page_history("never")
    assert not none.value.has_history


def test_restore_checks_rules() -> None:
    history = InMemoryWikiHistory()
    loose = _repo(rules=None, history=history)
    loose.write("a", "TODO 옛 메모")
    loose.write("a", "깨끗")
    strict = _repo(history=history)
    with pytest.raises(WikiRuleRejectedError):
        strict.restore("a", 1)


def test_history_pruning_and_unavailable() -> None:
    repo = _repo(limits=WikiRepositoryLimits(max_versions_per_page=3))
    for n in range(6):
        repo.write("a", f"v{n}")
    page = repo.page_history("a")
    assert [v.version for v in page.items] == [6, 5, 1]
    assert page.pruned
    with pytest.raises(WikiVersionNotFoundError):
        repo.restore("a", 2)
    bare = _repo(history=None)
    bare.write("a", "x")
    with pytest.raises(WikiHistoryUnavailableError):
        bare.page_history("a")
    assert bare.scan().recorded is False


def test_external_changes_recorded_once(tmp_path: Path) -> None:
    pages = LocalWikiPages(tmp_path)
    repo = _repo(pages)
    repo.write("a", "앱에서 씀")
    (tmp_path / "a.md").write_text("밖에서 고침", encoding="utf-8")
    (tmp_path / "git.md").write_text("git으로 들어옴", encoding="utf-8")
    repo.write("gone", "곧 사라짐")
    (tmp_path / "gone.md").unlink()
    result = repo.scan()
    assert (result.external, result.imported, result.deleted) == (["a"], ["git"], ["gone"])
    again = repo.scan()
    assert (again.external, again.imported, again.deleted) == ([], [], [])
    ops = [v.op for v in repo.page_history("a").items]
    assert ops == ["external", "create"]
    assert repo.page_history("a").items[0].author.kind == "external"
    (tmp_path / "a.md").write_text("또 밖에서", encoding="utf-8")
    repo.view("a")  # 읽기도 외부 변경을 남긴다
    repo.view("a")
    assert [v.op for v in repo.page_history("a").items] == ["external", "external", "create"]
    (tmp_path / "a.md").write_text("세 번째", encoding="utf-8")
    repo.write("a", "앱에서 다시")
    assert [v.op for v in repo.page_history("a").items][:2] == ["update", "external"]


def test_failing_history_does_not_block_writes() -> None:
    class Broken(InMemoryWikiHistory):
        def record(self, entries: Any) -> Any:
            raise OSError("읽기 전용")

    repo = _repo(history=Broken())
    out = repo.write("a", "x")
    assert out.version is None
    assert [i.code for i in out.issues] == ["wiki.history_unavailable"]
    assert repo.read("a").data == b"x"


def test_search_index_follows_writes() -> None:
    search = ScanSearchIndex()
    repo = _repo(search=search)
    repo.write("a", "# 위키는 좋다\n")
    repo.write("b", "다른 글")
    assert [h.path for h in repo.search("위키").items] == ["a"]
    repo.move("a", "c")
    assert [h.path for h in repo.search("위키").items] == ["c"]
    repo.delete("c")
    assert repo.search("위키").items == []
    assert _repo(search=None).search("x").degraded


def test_graph_lint_link_text_and_templates() -> None:
    clock = FakeClock(start=1_762_473_600.0)  # 2025-11-07 UTC
    repo = _repo(clock=clock, home="index", limits=WikiRepositoryLimits(graph_max_nodes=2))
    repo.write("index", "# 시작\n[[a]] [[b]] [[없음]]\n")
    repo.write("a", "---\ntitle: 에이\n---\n")
    repo.write("b", "TODO 직접\n".replace("TODO", "todo"))
    graph = repo.graph("index", depth=1)
    assert graph.truncated
    assert len(graph.nodes) == 2
    report = repo.lint()
    assert any(i.code == "wiki.broken_link" for i in report.issues)
    assert repo.link_text("index", "a").text == "[[a|에이]]"
    assert repo.link_text("index", "b", label="비").text == "[[b|비]]"
    rendered = repo.render_template("d", title="API 버전")
    assert rendered.path == "decisions/api-버전"
    assert rendered.content.startswith("# API 버전\n날짜: 20")
    with pytest.raises(WikiTemplateNotFoundError):
        repo.render_template("nope")
