"""생성(extdocs)·드리프트 검사(extdocs-check) 테스트."""

from __future__ import annotations

import re
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import build_notes, notes_tool
from extdocs import SKIP_MESSAGE, main
from extdocs_common import (
    TOOL_DIR,
    Area,
    ExtdocsError,
    Finding,
    LintRule,
    SymbolResolver,
    collect,
    load_data,
    member_src_paths,
)
from extdocs_docs import (
    allowed_rules,
    check_links,
    expand_globs,
    public_lint,
    rule_applies,
    run_docs_checks,
)
from extdocs_generate import Generator, write_plan
from extdocs_points import check_points
from extdocs_testkit import Repo, language_rule, other_lint_rules, tool_data

HOOKS_SNIPPET = """\
Use it to add work that runs after a note is saved.

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
        f"## note-kind\n\n{todo}", "## note-kind\n\nUse it to add a note kind plugin."
    )
    text = text.replace(f"## note-hooks\n\n{todo}", f"## note-hooks\n\n{HOOKS_SNIPPET}")
    assert todo not in text
    page.write_text(text, encoding="utf-8")
    return page


def write_area_pages(repo: Repo) -> None:
    """``areas.yaml``의 영역 페이지 중 아직 없는 것을 제목만 있는 파일로 만든다."""
    for area in tool_data().areas:
        page = repo.root / "docs/extending" / area.file
        if not page.exists():
            page.write_text(f"# {area.title}\n", encoding="utf-8")


@pytest.fixture
def documented(repo: Repo) -> Repo:
    (repo.root / "docs/extending").mkdir(parents=True)
    generate(repo, scaffold=True)
    fill_guides(repo)
    write_area_pages(repo)
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
        ("`../../specs/` 아래를 본다", "public-internal-doc-link"),
        ("specs/agent-console/tasks.md 참고", "public-internal-doc-link"),
        ("규칙은 CLAUDE.md에 있다", "public-internal-config"),
        ("설정은 .claude/agents에 둔다", "public-internal-config"),
        ("[규칙](../../CLAUDE.md)을 따른다", "public-internal-config"),
        ("이 저장소의 `CLAUDE.md`를 따른다", "public-internal-config"),
        ('# 환경 메모(CLAUDE.md "고정·환경 메모")', "public-internal-config"),
        ("확장 지점 X14를 더한다", "public-design-id"),
        ("포트 모양(X25): 문서", "public-design-id"),
        ("요구사항 R8.6 참고", "public-design-id"),
        ("결정 K33-19에 따라", "public-design-id"),
        ("(R0·R10.4)", "public-design-id"),
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
    found = public_lint(tmp_path, [path], other_lint_rules(), warning=False)
    assert rule in {f.code for f in found}


def test_public_lint_clean_text(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text(
        "# 제목\n\n`uv run poe extdocs` 후 `examples/extensions/README.md`를 본다. 버전 0.14.1.\n",
        encoding="utf-8",
    )
    assert public_lint(tmp_path, [path], other_lint_rules(), warning=False) == []


@pytest.mark.parametrize(
    "line",
    [
        # 제품이 읽고 쓰는 Claude Code 파일(파일 이름이 데이터)
        "CLI 세션 `~/.claude/projects`(읽기 전용)",
        "프로젝트 `.claude/` 설정을 가져온다",
        "`CLAUDE.md`에 이어 붙인다",
        ">>> plan.paths  # ['.claude/agents/pl.md']",
        '"command": "./.claude/hooks/check.sh --strict"',
        "path_exists=lambda p: p == '/srv/me/.claude/.credentials.json'",
        "| `writes` | `${CLAUDE_CONFIG_DIR}/.credentials.json` |",
        "CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1",
        # API 경로·제품이 만드는 폴더
        "`GET /sdd/specs/{id}`",
        "demo specs/demo",
        # 요구사항 id 모양의 예제 데이터(코드 안)
        "`test_R1_login` → `R1`, `R10`·`R1.2` 안의 `R1`은 아님",
        "k8s·X-ray·R2D2·0X1F",
    ],
)
def test_public_lint_product_terms_pass(tmp_path: Path, line: str) -> None:
    path = tmp_path / "doc.md"
    path.write_text(f"# 제목\n\n{line}\n", encoding="utf-8")
    assert public_lint(tmp_path, [path], other_lint_rules(), warning=False) == []


def test_design_id_ignores_code_fences(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text(
        '# 제목\n\n```python\nresult = ["R1", "X2"]\n```\n\n요구사항 R1을 본다.\n',
        encoding="utf-8",
    )
    found = public_lint(tmp_path, [path], other_lint_rules(), warning=False)
    assert [(f.code, f.where) for f in found] == [("public-design-id", "doc.md:7")]


def test_allow_marker_skips_named_rule_on_that_line(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text(
        "# 제목\n\n"
        "내보내기는 CLAUDE.md를 쓴다. <!-- extdocs:allow internal-config -->\n"
        "규칙은 CLAUDE.md에 있다. <!-- extdocs:allow design-id -->\n"
        "작업 5.2R.3과 CLAUDE.md <!-- extdocs:allow internal-config, task-number -->\n",
        encoding="utf-8",
    )
    found = public_lint(tmp_path, [path], other_lint_rules(), warning=False)
    assert [(f.code, f.where) for f in found] == [("public-internal-config", "doc.md:4")]
    assert allowed_rules("x <!-- extdocs:allow a b,c -->") == {"a", "b", "c"}


ENGLISH_DOC = """\
# Product

**English** | [한국어](README.ko.md)

Install it first. Then read the guide.

```python
>>> print("저장했습니다")
저장했습니다
```

The server returns `프로젝트` as the label.
한국어 문장이 남았다.
A sentence with 한글 inside. <!-- extdocs:allow korean-prose -->
"""


def test_korean_prose_rule_finds_hangul_outside_code(tmp_path: Path) -> None:
    """영어 문서: 코드 펜스·인라인 코드·언어 전환 줄·허용 표시 줄 밖 한글만 잡는다."""
    path = tmp_path / "README.md"
    path.write_text(ENGLISH_DOC, encoding="utf-8")
    found = public_lint(tmp_path, [path], [language_rule()], warning=False)
    assert [(f.code, f.where) for f in found] == [("public-korean-prose", "README.md:13")]
    assert "한국어 문장이 남았다" in found[0].message


def test_korean_prose_rule_skips_korean_copies(tmp_path: Path) -> None:
    """한국어 사본(``*.ko.md``)은 대상 밖이다(폴더 안이어도)."""
    for rel in ["README.ko.md", "docs/DEVELOPMENT.ko.md"]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(
            "# 개발 방식\n\n[English](DEVELOPMENT.md) | **한국어**\n", encoding="utf-8"
        )
    files = [tmp_path / "README.ko.md", tmp_path / "docs/DEVELOPMENT.ko.md"]
    assert public_lint(tmp_path, files, [language_rule()], warning=False) == []


def test_korean_prose_is_an_error_in_repo_settings(
    documented: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    """저장소 규칙: 영어 문서의 한글은 오류(경고 아님), 한국어 사본 ``*.ko.md``는 대상 밖."""
    assert language_rule().warning is False
    root = str(documented.root)
    assert main(["--root", root, "generate"]) == 0  # 저장소 설정(계약 표 포함)으로 다시 생성
    assert main(["--root", root, "docs"]) == 0  # 영어 픽스처는 저장소 규칙 그대로 통과
    (documented.root / "README.ko.md").write_text("# 제품\n\n한국어 사본이다.\n", encoding="utf-8")
    assert main(["--root", root, "docs"]) == 0
    (documented.root / "README.md").write_text(
        "# Product\n\n**English** | [한국어](README.ko.md)\n\n한국어 문장이 남았다.\n",
        encoding="utf-8",
    )
    capsys.readouterr()
    assert main(["--root", root, "docs"]) == 1
    out = capsys.readouterr().out
    assert "오류 [public-korean-prose] README.md:5" in out
    assert "README.ko.md" not in out


@pytest.mark.parametrize(
    ("line", "skipped"),
    [
        ("**English** | [한국어](README.ko.md)", True),
        ("[English](DEVELOPMENT.md) | **한국어**", True),
        ("**English** | [한국어](USAGE.ko.md) | [日本語](USAGE.ja.md)", True),
        ("**English** | [한국어](README.ko.md) 그리고 더", False),
        ("[한국어](README.ko.md)", False),
        ("| **이름** | [한국어](x.md) |", False),
    ],
)
def test_language_switch_line(line: str, skipped: bool) -> None:
    rule = language_rule()
    assert rule.skip_line is not None
    assert bool(rule.skip_line.search(line)) is skipped


def test_lint_rule_file_scope_and_severity(tmp_path: Path) -> None:
    """``files``·``exclude_files``는 파일 범위, ``warning``은 늘 경고(호출이 오류 모드여도)."""
    for rel in ["docs/a.md", "docs/a.ko.md", "other/b.md"]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("TODO here\n", encoding="utf-8")
    rule = LintRule(
        "todo",
        "todo",
        re.compile("TODO"),
        files=("docs/**/*.md",),
        exclude_files=("**/*.ko.md",),
        warning=True,
    )
    assert rule_applies(rule, "docs/a.md")
    assert not rule_applies(rule, "docs/a.ko.md")
    assert not rule_applies(rule, "other/b.md")
    files = sorted(tmp_path.rglob("*.md"))
    found = public_lint(tmp_path, files, [rule], warning=False)
    assert [(f.where, f.warning) for f in found] == [("docs/a.md:1", True)]
    assert errors(found) == []
    strict = replace(rule, warning=False)
    assert errors(public_lint(tmp_path, files, [strict], warning=False)) == ["public-todo"]


def test_lint_rule_data_fields(tmp_path: Path) -> None:
    """``public_lint.yaml``의 선택 칸을 읽고, 모르는 severity는 데이터 형식 오류다."""
    tool = tmp_path / "tool"
    shutil.copytree(TOOL_DIR, tool, ignore=shutil.ignore_patterns("py_tests", "*cache*", "*.py"))
    (tool / "public_lint.yaml").write_text(
        "rules:\n"
        "  - {id: a, message: m, pattern: x, files: docs/*.md, exclude_files: [x.ko.md],"
        " skip_line: '^#', severity: warning}\n",
        encoding="utf-8",
    )
    (rule,) = load_data(tool).lint_rules
    assert (rule.files, rule.exclude_files, rule.warning) == (("docs/*.md",), ("x.ko.md",), True)
    assert rule.skip_line is not None
    assert rule.skip_line.pattern == "^#"
    (tool / "public_lint.yaml").write_text(
        "rules:\n  - {id: a, message: m, pattern: x, severity: fatal}\n", encoding="utf-8"
    )
    with pytest.raises(ExtdocsError, match="severity"):
        load_data(tool)


def test_public_lint_targets_include_root_docs() -> None:
    """영어 기본 + 한국어 사본 루트 문서(README·USAGE·DEVELOPMENT)는 공개 가능 린트 대상이다."""
    globs = set(tool_data().settings["public_lint_globs"])
    for name in [
        "README.md",
        "README.ko.md",
        "USAGE.md",
        "USAGE.ko.md",
        "docs/DEVELOPMENT.md",
        "docs/DEVELOPMENT.ko.md",
    ]:
        assert name in globs


def test_expand_globs_prunes_skipped_and_hidden_dirs(tmp_path: Path) -> None:
    for rel in [
        "packages/a/README.md",
        "packages/a/node_modules/dep/README.md",
        "packages/a/.venv/lib/README.md",
        "packages/b/c/README.md",
        "packages/b/c/notes.md",
        "README.md",
    ]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x\n", encoding="utf-8")
    found = expand_globs(tmp_path, ["packages/**/README.md", "README.md", "missing.md"])
    assert [p.relative_to(tmp_path).as_posix() for p in found] == [
        "README.md",
        "packages/a/README.md",
        "packages/b/c/README.md",
    ]
    assert expand_globs(tmp_path, ["packages/*/README.md"]) == [tmp_path / "packages/a/README.md"]


DATA_POINT = """
[tool.agent-console.extension-points.note-defaults]
title = "Note defaults"
area = "memory"
summary = "Replaces the note defaults with data"
registration = {{ kind = "data", path = "data/notes.json" }}
example = {{ kind = "snippet", note = "notes data in the user settings" }}
guide = "memory.md#note-defaults"
"""


def test_generated_sentences_skip_empty_values(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    build_notes(repo, tool=notes_tool(repo) + DATA_POINT.format())
    (repo.root / "docs/extending").mkdir(parents=True)
    page = generate(repo, scaffold=True)["docs/extending/memory.md"]
    section = page.split("extdocs:facts note-defaults")[1]
    assert "- Registration: Uses the package data `data/notes.json`." in section
    assert "  - snippet: notes data in the user settings\n" in section
    assert "Keys that turn it off: ." not in page
    assert "— —" not in page
    assert "- Turning it off or removing it: Remove the data to drop only that item." in section


def test_public_lint_in_example_readme_fails(documented: Repo) -> None:
    readme = documented.root / "examples/extensions/example-notes/README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\n(design §3)\n", encoding="utf-8")
    assert errors(docs_check(documented)) == ["public-design-section"]


def test_public_lint_in_root_readme_fails(documented: Repo) -> None:
    """루트 README도 공개 가능 린트 대상이다(저장소 설정 ``public_lint_globs``, 8R 검토 F-6)."""
    readme = documented.root / "README.md"
    readme.write_text("# Product\n\nFollow the steps below to install.\n", encoding="utf-8")
    assert errors(docs_check(documented)) == []
    readme.write_text("# Product\n\nChanged in task 5.2R.3.\n", encoding="utf-8")
    assert errors(docs_check(documented)) == ["public-task-number"]


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


def test_link_to_unwritten_area_page_is_guides_category(documented: Repo) -> None:
    """지도가 영역 페이지보다 먼저 생겨도 --allow-missing guides에서 경고, 다른 깨진 링크는 오류."""
    page = documented.root / "docs/extending/README.md"
    area_file = tool_data().areas[0].file
    (documented.root / "docs/extending" / area_file).unlink()
    page.write_text(f"# 지도\n\n[영역]({area_file})\n", encoding="utf-8")
    findings = [f for f in docs_check(documented) if f.code in ("link-broken", "area-page-missing")]
    assert [f.missing for f in findings] == ["guides", "guides"]
    assert errors(findings) == ["area-page-missing", "link-broken"]
    assert errors(findings, ("guides",)) == []
    page.write_text("# 지도\n\n[없음](no-such-page.md)\n", encoding="utf-8")
    assert errors(docs_check(documented), ("guides",)).count("link-broken") == 1


def test_doctest_blocks_share_names_within_a_file(tmp_path: Path) -> None:
    """한 파일의 ``>>>`` 블록은 같은 이름 공간이다(앞 블록에서 만든 이름을 뒤 블록이 쓴다)."""
    from extdocs_docs import run_doctests

    page = tmp_path / "a.md"
    page.write_text(
        "# A\n\n```python\n>>> base = 40\n\n```\n\n글\n\n```python\n>>> base + 2\n42\n\n```\n",
        encoding="utf-8",
    )
    assert run_doctests(tmp_path, [page], SymbolResolver([])) == []


def test_area_page_file_must_exist(documented: Repo) -> None:
    """areas.yaml의 ``file``이 문서 폴더에 없으면 오류(선언이 없는 영역도), guides에서 경고."""
    area = tool_data().areas[0]
    assert "area-page-missing" not in errors(docs_check(documented))
    (documented.root / "docs/extending" / area.file).unlink()
    findings = [f for f in docs_check(documented) if f.code == "area-page-missing"]
    assert len(findings) == 1
    assert findings[0].where.endswith(f"areas.yaml [{area.id}]")
    assert f"docs/extending/{area.file}" in findings[0].message
    assert errors(findings) == ["area-page-missing"]
    assert errors(findings, ("guides",)) == []


def test_area_with_wrong_file_name_fails(documented: Repo) -> None:
    """``file``을 없는 이름으로 바꾸면(문서는 그대로) 검사가 잡는다."""
    base = tool_data()
    areas = (Area(base.areas[0].id, base.areas[0].title, "no-such-area.md"), *base.areas[1:])
    data = replace(base, areas=areas)
    col = collect(documented.root, data)
    resolver = SymbolResolver(member_src_paths(col.members))
    findings = run_docs_checks(documented.root, col, data, resolver, tool_dir=TOOL_DIR)
    missing = [f for f in findings if f.code == "area-page-missing"]
    assert [f.message for f in missing] == [
        "영역 페이지 파일이 없습니다: docs/extending/no-such-area.md"
    ]


def test_builtin_distribution_list_renders_folder_and_distribution(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from extdocs_common import Member

    members = [Member("agent-console-cap", tmp_path / "ac-cap", {})]
    gen = Generator.__new__(Generator)
    gen.col = SimpleNamespace(members=members)  # type: ignore[assignment]
    decl = SimpleNamespace(point=SimpleNamespace(builtin=["agent-console-cap", "agent-console-x"]))
    assert gen.builtins(decl) == [  # type: ignore[arg-type]
        "ac-cap (agent-console-cap)",
        "agent-console-x (agent-console-x)",
    ]
