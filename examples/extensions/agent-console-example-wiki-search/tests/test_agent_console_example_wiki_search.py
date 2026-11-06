"""단위 시험: entry point 선언, 역색인 동작, 낱말 나누기 옵션(데이터), 틀린 옵션."""

from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path

import pytest

from agent_console_example_wiki_search import (
    BACKEND_ID,
    InvertedSearchIndex,
    default_options,
    index_factory,
    make_index,
)
from agent_console_wiki import SEARCH_INDEX_GROUP, WikiSearchIndex, new_search_registry
from agent_console_wiki import load_search_plugins as load
from agent_console_wiki.testing import make_search_document

ROOT = Path(__file__).resolve().parents[1]


def test_entry_point_declaration() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    table = data["project"]["entry-points"][SEARCH_INDEX_GROUP]
    assert table == {BACKEND_ID: "agent_console_example_wiki_search:index_factory"}


def test_loaded_through_the_library_loader() -> None:
    ep = importlib.metadata.EntryPoint(
        name=BACKEND_ID,
        value="agent_console_example_wiki_search:index_factory",
        group=SEARCH_INDEX_GROUP,
    )
    registry = new_search_registry()
    assert [r.status for r in load(registry, entry_points=[ep])] == ["loaded"]
    index = registry.get(BACKEND_ID)(None, {"case_insensitive": True})
    assert isinstance(index, WikiSearchIndex)
    assert index.id == BACKEND_ID
    assert index.degraded is False


def test_factory_ignores_root_and_makes_independent_indexes(tmp_path: Path) -> None:
    factory = index_factory()
    a, b = factory(tmp_path / "a", {}), factory(None, {})
    a.update([make_search_document("x", "공유되지 않는 본문")])
    assert a.search("본문").items
    assert b.search("본문").items == []
    assert not (tmp_path / "a").exists()  # 파일을 만들지 않는다


def test_marks_are_provided() -> None:
    index = make_index({})
    index.update([make_search_document("p", "앞 위키 뒤 wiki", title="제목")])
    hit = index.search("위키").items[0]
    assert [(m.start, m.end) for m in hit.marks] == [(2, 4)]


def test_removed_documents_leave_no_postings() -> None:
    index = make_index({})
    assert isinstance(index, InvertedSearchIndex)
    index.update([make_search_document("p", "고유낱말 공통")])
    index.remove(["p"])
    assert index.search("고유낱말").items == []
    assert index._postings == {}


def test_tokenizer_rules_are_data() -> None:
    defaults = default_options()
    assert defaults["tokenizers"]["whitespace"] == "\\S+"
    # 이름 표를 옵션으로 덮어쓰거나 정규식을 직접 줄 수 있다.
    # 모르는 이름(mod-wiki의 trigram 등)은 기본 규칙.
    doc = make_search_document("p", "alpha-beta gamma")
    for options in ({"tokenizer": "trigram"}, {"tokenizer": "word"}, {"token_pattern": r"[a-z]+"}):
        index = make_index(options)
        index.update([doc])
        assert [h.path for h in index.search("gamma").items] == ["p"]
    word = make_index({"tokenizer": "word"})
    word.update([doc])
    assert word.search("beta").items  # 낱말 안의 부분 일치
    assert word.search("a-b").items == []  # 낱말 경계에 걸친 질의는 놓친다(문서에 적음)
    whitespace = make_index({})
    whitespace.update([doc])
    assert whitespace.search("a-b").items


@pytest.mark.parametrize("pattern", ["(", ".*"])
def test_bad_token_pattern_is_rejected(pattern: str) -> None:
    with pytest.raises(ValueError, match="token_pattern"):
        make_index({"token_pattern": pattern})
