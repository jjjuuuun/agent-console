"""생성(extdocs)·드리프트 검사(extdocs-check) 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest
from extdocs import SKIP_MESSAGE, main
from extdocs_common import TOOL_DIR, Finding, SymbolResolver, collect, member_src_paths
from extdocs_docs import check_links, public_lint, run_docs_checks
from extdocs_generate import Generator, write_plan
from extdocs_points import check_points
from extdocs_testkit import Repo, tool_data

HOOKS_SNIPPET = """\
노트를 저장한 뒤 할 일을 더할 때 쓴다.

```python
>>> 1 + 1
2
```
"""


def generate(repo: Repo, *, scaffold: bool = False) -> dict[str, str]:
    data = tool_data()
    col = collect(repo.root, data)
    resolver = SymbolResolver(member_src_paths(col.members))
    _, facts = check_points(repo.root, col, data, resolver, tool_dir=TOOL_DIR)
    planned = Generator(col, facts, data, resolver).plan(repo.root, scaffold=scaffold)
    write_plan(repo.root, planned)
    return planned


def docs_check(repo: Repo) -> list[Finding]:
    data = tool_data()
    col = collect(repo.root, data)
    resolver = SymbolResolver(member_src_paths(col.members))
    return run_docs_checks(repo.root, col, data, resolver, tool_dir=TOOL_DIR)


def errors(findings: list[Finding], allowed: tuple[str, ...] = ()) -> list[str]:
    return sorted(f.code for f in findings if f.is_error(allowed))


def fill_guides(repo: Repo) -> Path:
    """스캐폴드한 절의 todo 표지를 손글로 바꾼다."""
    page = repo.root / "docs/extending/memory.md"
    text = page.read_text(encoding="utf-8")
    todo = str(tool_data().text["todo_text"])
    text = text.replace(
        f"## note-kind\n\n{todo}", "## note-kind\n\n노트 종류 플러그인을 더할 때 쓴다."
    )
    text = text.replace(f"## note-hooks\n\n{todo}", f"## note-hooks\n\n{HOOKS_SNIPPET}")
    assert todo not in text
    page.write_text(text, encoding="utf-8")
    return page


@pytest.fixture
def documented(repo: Repo) -> Repo:
    (repo.root / "docs/extending").mkdir(parents=True)
    generate(repo, scaffold=True)
    fill_guides(repo)
    generate(repo)
    return repo


def test_no_docs_folder_skips(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(repo.root), "docs"]) == 0
    assert SKIP_MESSAGE in capsys.readouterr().out


def test_documented_repo_passes(documented: Repo) -> None:
    assert errors(docs_check(documented)) == []
    page = (documented.root / "docs/extending/memory.md").read_text(encoding="utf-8")
    assert "<!-- extdocs:facts note-kind -->" in page
    assert "plain (agent-console-notes)" in page  # 기본 구현 = 그룹에 등록된 이름 → 배포
    ref = (documented.root / "docs/extending/reference.md").read_text(encoding="utf-8")
    assert "`agent_console.note_kinds`" in ref
    assert "`notes.hooks`" in ref
    index = (documented.root / "examples/extensions/README.md").read_text(encoding="utf-8")
    assert "example-notes" in index
    assert "note-kind" in index


def test_generation_is_deterministic(documented: Repo) -> None:
    first = generate(documented)
    second = generate(documented)
    assert first == second
    for content in first.values():
        assert "\r" not in content
        assert str(documented.root) not in content


def test_stale_generated_section_fails(documented: Repo) -> None:
    m = documented.mod("notes")
    documented.package(
        "ac-more",
        "agent-console-more",
        entry_points=f'[project.entry-points."agent_console.note_kinds"]\nfancy = "{m}:NoteKind"\n',
    )
    found = docs_check(documented)
    assert errors(found) == ["generated-stale", "generated-stale"]  # 영역 페이지 + reference.md
    generate(documented)
    assert errors(docs_check(documented)) == []


def test_todo_marker_fails(documented: Repo) -> None:
    page = documented.root / "docs/extending/memory.md"
    page.write_text(
        page.read_text(encoding="utf-8") + "\n<!-- extdocs:todo -->\n", encoding="utf-8"
    )
    found = docs_check(documented)
    assert errors(found) == ["guide-todo"]
    assert errors(found, ("guides",)) == []


def test_scaffold_leaves_todo(repo: Repo) -> None:
    (repo.root / "docs/extending").mkdir(parents=True)
    generate(repo, scaffold=True)
    found = errors(docs_check(repo))
    assert "guide-todo" in found
    assert "guide-empty" in found


def test_missing_guide_section_fails(documented: Repo) -> None:
    page = documented.root / "docs/extending/memory.md"
    text = page.read_text(encoding="utf-8").replace("## note-hooks", "## renamed")
    page.write_text(text, encoding="utf-8")
    found = errors(docs_check(documented))
    assert "guide-missing" in found


def test_broken_anchor_and_link_fail(documented: Repo) -> None:
    page = documented.root / "docs/extending/memory.md"
    page.write_text(
        page.read_text(encoding="utf-8")
        + "\n[a](#no-such)\n[b](reference.md#nope)\n[c](missing.md)\n[d](#note-kind)\n"
        + "[e](https://example.org/x)\n`[f](#in-code)`\n",
        encoding="utf-8",
    )
    found = errors(docs_check(documented))
    assert found.count("anchor-broken") == 2
    assert found.count("link-broken") == 1


@pytest.mark.parametrize(
    ("line", "rule"),
    [
        ("자세한 내용은 [설계](../../specs/x/design.md)를 본다.", "public-internal-doc-link"),
        ("docs/design/ux.md 참고", "public-internal-doc-link"),
        ("규칙은 CLAUDE.md에 있다", "public-internal-config"),
        ("설정은 .claude/agents에 둔다", "public-internal-config"),
        ("design §8R.2 참고", "public-design-section"),
        ("작업 5.2R.104에서 바뀌었다", "public-task-number"),
        ("작업 8R.4a에서 채운다", "public-task-number"),
        ("경로 /home/user/agent-console", "public-local-path"),
        ("경로 /mnt/" + "c/Users/x", "public-local-path"),
        ("경로 C:" + "\\" + "Users\\user", "public-local-path"),
        ("문의 someone@example.com", "public-email"),
    ],
)
def test_public_lint_rules(tmp_path: Path, line: str, rule: str) -> None:
    path = tmp_path / "doc.md"
    path.write_text(f"# 제목\n\n{line}\n", encoding="utf-8")
    found = public_lint(tmp_path, [path], tool_data().lint_rules, warning=False)
    assert rule in {f.code for f in found}


def test_public_lint_clean_text(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text(
        "# 제목\n\n`uv run poe extdocs` 후 `examples/extensions/README.md`를 본다. 버전 0.14.1.\n",
        encoding="utf-8",
    )
    assert public_lint(tmp_path, [path], tool_data().lint_rules, warning=False) == []


def test_public_lint_in_example_readme_fails(documented: Repo) -> None:
    readme = documented.root / "examples/extensions/example-notes/README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\n(design §3)\n", encoding="utf-8")
    assert errors(docs_check(documented)) == ["public-design-section"]


def test_report_mode_only_warns(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text("design §1\n", encoding="utf-8")
    assert main(["--root", str(tmp_path), "docs", "--report", "README.md"]) == 0
    out = capsys.readouterr().out
    assert "경고 [public-design-section]" in out


def test_doctest_failure_fails(documented: Repo) -> None:
    page = documented.root / "docs/extending/memory.md"
    page.write_text(
        page.read_text(encoding="utf-8").replace(">>> 1 + 1\n2", ">>> 1 + 1\n3"), encoding="utf-8"
    )
    assert errors(docs_check(documented)) == ["doctest-failed"]


def _add_validated_snippet(repo: Repo, body: str) -> None:
    m = repo.mod("notes")
    repo.write(
        f"packages/py/features/ac-notes/src/{m}/rules.py",
        "from pydantic import BaseModel, ConfigDict\n\n\n"
        "class Inner(BaseModel):\n    model_config = ConfigDict(extra='allow')\n    name: str\n\n\n"
        "class Rules(BaseModel):\n    limit: int\n    inner: Inner\n",
    )
    page = repo.root / "docs/extending/memory.md"
    page.write_text(
        page.read_text(encoding="utf-8")
        + f"\n```yaml extdocs:validate={m}.rules:Rules\n{body}```\n",
        encoding="utf-8",
    )


def test_validated_snippet_passes(documented: Repo) -> None:
    _add_validated_snippet(documented, "limit: 3\ninner:\n  name: a\n")
    assert errors(docs_check(documented)) == []


def test_validated_snippet_invalid_fails(documented: Repo) -> None:
    _add_validated_snippet(documented, "limit: many\ninner:\n  name: a\n")
    assert errors(docs_check(documented)) == ["snippet-invalid"]


def test_validated_snippet_unknown_key_fails(documented: Repo) -> None:
    _add_validated_snippet(documented, "limit: 3\ninner:\n  name: a\n  nmae: typo\n")
    assert errors(docs_check(documented)) == ["snippet-unknown-keys"]


def test_snippet_example_needs_checked_block(documented: Repo) -> None:
    page = documented.root / "docs/extending/memory.md"
    page.write_text(
        page.read_text(encoding="utf-8").replace(">>> 1 + 1\n2\n", "print(2)\n"), encoding="utf-8"
    )
    found = docs_check(documented)
    assert errors(found) == ["snippet-missing"]
    assert errors(found, ("examples",)) == []


def test_orphan_facts_fails(documented: Repo) -> None:
    page = documented.root / "docs/extending/memory.md"
    page.write_text(
        page.read_text(encoding="utf-8")
        + "\n<!-- extdocs:facts gone-point -->\n<!-- /extdocs:facts -->\n",
        encoding="utf-8",
    )
    assert errors(docs_check(documented)) == ["facts-orphan"]


def test_cli_generate_and_check(documented: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    root = str(documented.root)
    assert main(["--root", root, "generate"]) == 0  # 저장소 설정(계약 표 포함)으로 다시 생성
    assert main(["--root", root, "docs"]) == 0
    (documented.root / "docs/extending/reference.md").write_text("old\n", encoding="utf-8")
    assert main(["--root", root, "docs"]) == 1
    assert "generated-stale" in capsys.readouterr().out
    assert main(["--root", root, "generate"]) == 0
    assert main(["--root", root, "docs"]) == 0


def test_links_skip_code(tmp_path: Path) -> None:
    path = tmp_path / "a.md"
    path.write_text("# A\n\n```md\n[x](missing.md)\n```\n\n`[y](nope.md)`\n", encoding="utf-8")
    assert check_links(tmp_path, [path]) == []
