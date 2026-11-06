"""위키 zip 내보내기·가져오기(7R.8, design §7R.13·§7R.18 Q16)."""

from __future__ import annotations

import io
import zipfile
from typing import Any

import pytest

from agent_console_contracts.wiki import WikiRulesDefinition
from agent_console_safe_zip import ZipLimits
from agent_console_wiki import (
    InMemoryWikiHistory,
    RulesDocument,
    WikiRepository,
    WikiZipFormatError,
    compile_syntax,
    effective_syntax,
    export_zip,
    import_zip,
    merge_rules,
)
from agent_console_wiki.testing import FakeClock, MemoryWikiPages

RULES = merge_rules(
    ["r"],
    [
        RulesDocument(
            "r",
            WikiRulesDefinition.model_validate(
                {
                    "kind": "wiki-rules",
                    "id": "r",
                    "name": "r",
                    "write_rules": [{"id": "no-temp", "deny_patterns": ["TODO"]}],
                }
            ),
        )
    ],
)


def _repo() -> WikiRepository:
    return WikiRepository(
        MemoryWikiPages(),
        wiki_id="w",
        syntax=compile_syntax(effective_syntax()),
        rules=RULES,
        history=InMemoryWikiHistory(),
        clock=FakeClock(),
    )


def _zip(entries: list[tuple[Any, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for info, data in entries:
            archive.writestr(info, data)
    return buffer.getvalue()


def test_export_import_round_trip() -> None:
    source = _repo()
    source.write("index", "# 시작\n[[a/b]]\n")
    source.write("a/b", "본문\r\n")
    data = export_zip(source)
    assert data == export_zip(source)  # 같은 페이지면 같은 바이트
    target = _repo()
    result = import_zip(target, data)
    assert [(i.path, i.status) for i in result.items] == [("a/b", "created"), ("index", "created")]
    assert target.read("a/b").data == "본문\r\n".encode()
    assert target.page_history("index").items[0].op == "import"
    assert target.page_history("index").items[0].author.kind == "system"


def test_policies_and_dry_run() -> None:
    repo = _repo()
    repo.write("a", "기존")
    data = _zip([("a.md", "새 본문".encode()), ("b.md", b"b"), ("note.txt", b"x")])
    dry = import_zip(repo, data, policy="overwrite", dry_run=True)
    assert dry.dry_run
    assert [(i.path, i.status) for i in dry.items] == [
        ("a", "overwritten"),
        ("b", "created"),
        ("note.txt", "skipped"),
    ]
    assert repo.read("a").data == "기존".encode()
    assert repo.current("b") is None
    skipped = import_zip(repo, data, policy="skip")
    assert [(i.path, i.status) for i in skipped.items][:2] == [("a", "skipped"), ("b", "created")]
    renamed = import_zip(repo, data, policy="rename")
    assert [(i.path, i.status, i.to) for i in renamed.items][:2] == [
        ("a", "renamed", "a-2"),
        ("b", "renamed", "b-2"),
    ]
    over = import_zip(repo, data, policy="overwrite")
    assert over.items[0].status == "overwritten"
    assert repo.read("a").data == "새 본문".encode()
    assert repo.page_history("a").items[0].op == "update"
    with pytest.raises(ValueError, match="정책"):
        import_zip(repo, data, policy="merge")  # type: ignore[arg-type]


@pytest.mark.filterwarnings("ignore:Duplicate name")
def test_path_attacks_rules_and_duplicates_are_rejected_per_item() -> None:
    link = zipfile.ZipInfo("link.md")
    link.external_attr = 0o120777 << 16
    data = _zip(
        [
            ("../escape.md", b"x"),
            ("/abs.md", b"x"),
            ("C:/drive.md", b"x"),
            (".hidden/a.md", b"x"),
            ("con.md", b"x"),
            (link, b"target"),
            ("ok.md", b"fine"),
            ("ok.md", b"again"),
            ("temp.md", b"TODO later"),
        ]
    )
    repo = _repo()
    result = import_zip(repo, data)
    status = [(i.path, i.status, i.issues[0].code if i.issues else None) for i in result.items]
    assert status[:3] == [
        ("../escape.md", "rejected", "wiki.invalid_path"),
        ("/abs.md", "rejected", "wiki.invalid_path"),
        ("C:/drive.md", "rejected", "wiki.invalid_path"),
    ]
    assert ("link.md", "rejected", "wiki.invalid_path") in status
    assert (".hidden/a.md", "rejected", "wiki.invalid_path") in status
    assert ("con.md", "rejected", "wiki.invalid_path") in status
    assert ("ok", "created", None) in status
    assert ("ok", "rejected", "wiki.page_exists") in status
    assert ("temp", "rejected", "wiki.rule_rejected") in status
    assert [f.file for f in repo.pages.list([".md"])] == ["ok.md"]
    assert repo.read("ok").data == b"fine"


def test_archive_limits_write_nothing() -> None:
    data = _zip([("a.md", b"x" * 100), ("b.md", b"y" * 100)])
    repo = _repo()
    result = import_zip(repo, data, limits=ZipLimits(max_total_bytes=150))
    assert result.items == []
    assert [(i.code, i.details["limit"]) for i in result.issues] == [
        ("wiki.too_large", "max_total_bytes")
    ]
    assert repo.pages.list([".md"]) == []
    with pytest.raises(WikiZipFormatError):
        import_zip(repo, b"not a zip")
