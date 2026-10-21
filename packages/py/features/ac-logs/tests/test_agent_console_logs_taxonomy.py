from pathlib import Path

from agent_console_contracts.logs import LogTaxonomy
from agent_console_logs import load_default_taxonomy, load_taxonomy, merge_taxonomy


def test_default_taxonomy_marks_error_danger() -> None:
    tax = load_default_taxonomy()
    assert tax.categories["error"].tone == "danger"
    dangers = [cid for cid, c in tax.categories.items() if c.tone == "danger"]
    assert dangers == ["error"]


def test_missing_or_empty_taxonomy_is_empty(tmp_path: Path) -> None:
    assert load_default_taxonomy(tmp_path / "none.yaml") == LogTaxonomy()
    (tmp_path / "e.yaml").write_text("", encoding="utf-8")
    assert load_default_taxonomy(tmp_path / "e.yaml") == LogTaxonomy()
    assert merge_taxonomy(None, None) == LogTaxonomy()


def test_merge_overrides_set_fields_only() -> None:
    base = load_taxonomy("categories: {a: {label: A, tone: danger, color: red}}\norder: [a]")
    over = load_taxonomy("categories: {a: {label: AA}, b: {label: B}}")
    merged = merge_taxonomy(base, over)
    assert merged.categories["a"].label == "AA"
    assert merged.categories["a"].tone == "danger"
    assert merged.categories["a"].color == "red"
    assert merged.categories["b"].label == "B"
    assert merged.order == ["a"]
    assert merge_taxonomy(base, load_taxonomy("order: [b]")).order == ["b"]
