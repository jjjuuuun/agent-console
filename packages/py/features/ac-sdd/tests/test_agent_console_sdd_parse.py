"""스펙 문서 파싱(design §6R.1.3, 6R.10 완료 기준)."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator

from agent_console_contracts.sdd import SddSettings, SpecIndex, SpecRules, SpecSyntax
from agent_console_sdd import effective_syntax, find_task, merge_syntax, parse_spec
from agent_console_sdd.testing import (
    RENAMED_NAMES,
    RENAMED_SYNTAX,
    render_tasks,
    sample_files,
    sample_spec,
)


def _parse(files: dict[str, str] | None = None, **kw: object) -> SpecIndex:
    return parse_spec(sample_spec(), files or sample_files(), effective_syntax(), **kw)  # type: ignore[arg-type]


def _codes(index: SpecIndex) -> list[str]:
    return sorted(i.code for i in index.issues)


def test_tasks_md_style_excerpt() -> None:
    index = _parse()
    keys = [t.key for t in index.tasks]
    # 코드 블록·인용 안, 역할 없는 문서(설계)의 체크 칸은 작업이 아니다.
    assert keys == ["6R.1", "6R.2", "6R.3", "6R.4", "6R.10", "6R.11", "6R.12"]
    t = {t.key: t for t in index.tasks}
    assert t["6R.1"].dependencies == []  # "—" = 없음
    assert t["6R.1"].status == "done"
    assert t["6R.1"].body == "- 하는 일: 설계 문서.\n- 완료 기준: 승인."
    assert t["6R.3"].dependencies == ["6R.1", "6R.2"]
    # 범위 a~b = 문서 순서상 그 사이 전부(뒤 낱말 "전부"는 무시).
    assert t["6R.12"].dependencies == ["6R.1", "6R.2", "6R.3", "6R.4", "6R.10", "6R.11"]
    assert t["6R.3"].requirements == ["R6.1", "R6.2", "R6.3"]  # 요구 범위도 문서 순서
    assert t["6R.10"].fields == {
        "owner": "backend-lead",
        "req": "R6.1, R6.2, R0.1",
        "depends": "6R.3, 6R.4",
    }
    assert t["6R.10"].title == "`ac-sdd` 핵심: 문법"
    assert [k for k, v in t.items() if v.ready] == ["6R.3", "6R.4"]
    assert t["6R.1"].line == 7
    assert t["6R.1"].document == "tasks"
    assert len(t["6R.1"].line_hash) == 16

    assert [r.id for r in index.requirements] == ["R0", "R0.1", "R6", "R6.1", "R6.2", "R6.3"]
    assert index.requirements[1].title == "아무것도 하드코딩하지 않는다."
    stages = [(s.id, s.done, s.total) for s in index.stages]
    assert stages == [("Phase 6R — SDD", 2, 4), ("묶음 2 — 라이브러리", 0, 3)]
    assert t["6R.10"].stage is not None
    assert t["6R.10"].stage.id == "묶음 2 — 라이브러리"
    docs = {d.id: d for d in index.documents}
    assert docs["tasks"].tasks == 7
    assert docs["requirements"].requirements == 6
    assert docs["design"].exists
    assert docs["design"].tasks == 0
    assert docs["design"].content_hash
    assert index.issues == []
    assert find_task(index, "6R.11") is t["6R.11"]
    assert find_task(index, "없음") is None


def _normalized(index: SpecIndex, status_map: dict[str, str]) -> Iterator[tuple[object, ...]]:
    for t in index.tasks:
        yield (
            t.key,
            t.title,
            status_map.get(t.status, t.status),
            tuple(t.dependencies),
            tuple(t.requirements),
            t.ready,
            t.stage.title if t.stage else None,
            t.body,
            tuple(t.fields),
        )


def test_renamed_syntax_gives_same_result() -> None:
    """R0: 필드·상태·단계·구분자 이름을 모두 바꾼 문법 데이터로 같은 결과."""
    base = _parse()
    files = sample_files(RENAMED_NAMES)
    syntax = effective_syntax(
        SpecRules(syntax=SpecSyntax.model_validate(RENAMED_SYNTAX)),
        SddSettings(include_default_syntax=False),
    )
    renamed = parse_spec(sample_spec(), files, syntax)
    assert renamed.issues == []
    field_map = {"owner": "who", "req": "needs", "depends": "after"}
    want = [
        (*row[:-1], tuple(field_map[str(f)] for f in row[-1]))  # type: ignore[attr-defined]
        for row in _normalized(base, {"todo": "open", "done": "closed"})
    ]
    assert list(_normalized(renamed, {})) == want
    assert [(s.id, s.done, s.total) for s in renamed.stages] == [
        ("Phase 6R", 2, 4),
        ("묶음 2", 0, 3),
    ]
    assert [r.id for r in renamed.requirements] == [r.id for r in base.requirements]


def test_default_off_gives_no_tasks_and_syntax_missing() -> None:
    syntax = effective_syntax(settings=SddSettings(include_default_syntax=False))
    index = parse_spec(sample_spec(), sample_files(), syntax)
    assert index.tasks == []
    assert _codes(index) == ["sdd.syntax_missing"]
    assert index.issues[0].severity == "info"
    # 문서 목록·해시는 그대로(문서 편집·상태는 동작).
    assert all(d.exists and d.content_hash for d in index.documents)


def test_issue_codes() -> None:
    text = (
        "## 단계\n"
        "- [ ] 1.1 하나 [depends: 9.9]\n"
        "- [?] 1.2 모르는 글자 [depends: 1.1~8.8]\n"
        "- [ ] 1.1 같은 id\n"
        "- [ ] 2.1 순환 [depends: 2.2] [req: R1, Z9]\n"
        "- [ ] 2.2 순환 [depends: 2.1]\n"
        "- [ ] 3.1 자기 자신 [depends: 3.1]\n"
    )
    files = sample_files()
    files["tasks.md"] = text
    index = _parse(files)
    by_key = {t.key: t for t in index.tasks}
    assert list(by_key) == ["1.1", "1.2", "@tasks:3", "2.1", "2.2", "3.1"]
    assert [i.code for i in by_key["1.1"].issues] == ["sdd.unknown_dependency"]
    assert by_key["1.1"].issues[0].details == {"ref": "9.9"}
    assert by_key["1.1"].ready  # 모르는 의존은 막지 않는다(이슈로 보임)
    assert [i.code for i in by_key["1.2"].issues] == [
        "sdd.unknown_status_marker",
        "sdd.range_unresolved",
    ]
    assert by_key["1.2"].status == "todo"
    assert [i.code for i in by_key["@tasks:3"].issues] == ["sdd.duplicate_task_id"]
    assert by_key["@tasks:3"].id == "1.1"
    assert [i.code for i in by_key["2.1"].issues] == [
        "sdd.unknown_requirement",
        "sdd.unknown_requirement",
        "sdd.dependency_cycle",
    ]
    assert by_key["2.1"].requirements == ["R1", "Z9"]
    assert by_key["2.2"].issues[0].details == {"cycle": ["2.1", "2.2"]}
    assert by_key["3.1"].issues[0].code == "sdd.dependency_cycle"
    assert all(i.line and i.document == "tasks" for i in index.issues)
    # 작업 이슈는 색인 이슈에도 모두 있다.
    assert len(index.issues) == sum(len(t.issues) for t in index.tasks)


def test_missing_document_and_no_requirement_docs() -> None:
    files = sample_files()
    del files["requirements.md"]
    index = _parse(files)
    assert _codes(index) == ["sdd.document_missing"]  # 요구 문서가 없으면 요구 확인을 하지 않는다
    missing = next(d for d in index.documents if d.id == "requirements")
    assert not missing.exists
    assert missing.content_hash is None
    assert index.issues[0].details == {"document_id": "requirements", "file": "requirements.md"}


def test_bytes_crlf_tabs_and_nesting() -> None:
    text = (
        "## A\r\n\r\n- [ ] 1 하나\r\n\t- [x] 1.1 안쪽\r\n  본문 줄\r\n"
        "- [ ] 2 둘 [depends: 1.1]  \r\n"
    )
    files = {"t.md": text.encode("utf-8")}
    docs = [{"id": "t", "title": "T", "file": "t.md", "roles": ["tasks"]}]
    index = parse_spec(sample_spec(*docs), files, effective_syntax())
    assert [(t.key, t.line, t.status) for t in index.tasks] == [
        ("1", 3, "todo"),
        ("1.1", 4, "done"),
        ("2", 6, "todo"),
    ]
    assert "1.1 안쪽" in index.tasks[0].body
    assert index.tasks[2].ready
    assert "\r" not in index.tasks[0].body


def test_max_depth_and_list_kinds() -> None:
    text = "- [ ] 1 위\n  - [ ] 1.1 아래\n1. 2 번호 항목\n- 3 글머리 항목\n"
    docs = [{"id": "t", "title": "T", "file": "t.md", "roles": ["tasks"]}]
    spec = sample_spec(*docs)

    def keys(task: dict[str, object]) -> list[str]:
        syntax = merge_syntax(("d", effective_syntax().syntax), ("s", {"task": task}))
        return [t.key for t in parse_spec(spec, {"t.md": text}, syntax).tasks]

    assert keys({}) == ["1", "1.1"]
    assert keys({"max_depth": 1}) == ["1"]
    assert keys({"list_item": "ordered"}) == ["2"]
    assert keys({"list_item": "bullet"}) == ["1", "1.1", "3"]


def test_limits_timeout_and_too_many() -> None:
    ticks = iter(range(0, 10_000_000, 1))
    index = _parse(timeout_ms=0.5, clock=lambda: next(ticks))
    assert "sdd.parse_timeout" in _codes(index)
    assert index.tasks == []
    limited = _parse(max_tasks=3)
    assert [t.key for t in limited.tasks] == ["6R.1", "6R.2", "6R.3"]
    assert "sdd.too_many_tasks" in _codes(limited)


def test_template_and_document_list_inputs() -> None:
    spec = sample_spec()
    index = parse_spec(spec.documents, sample_files(), effective_syntax())
    assert len(index.tasks) == 7


def test_import_does_not_pull_runtime_or_server() -> None:
    code = (
        "import sys, agent_console_sdd, agent_console_sdd.testing;"
        "bad=[m for m in sys.modules if m.split('.')[0] in {"
        "'agent_console_runtime','agent_console_runs','agent_console_projects',"
        "'agent_console_server','fastapi'}];"
        "print(bad); sys.exit(1 if bad else 0)"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout + done.stderr


def test_render_tasks_template_is_used() -> None:
    assert "[who: pl]" in render_tasks(RENAMED_NAMES)
