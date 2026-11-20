"""줄 머리 낱말 상태(`TaskSyntax.status_pattern`·`status_format`·`field_format`, 6R.32).

체크 칸 대신 `- TODO: 결제`·`1. DONE 배포`처럼 줄 머리 낱말로 상태를 쓰는 사용자가 코드를
고치지 않고 문법 데이터만으로 읽고(parse) 고칠(patch) 수 있는지 본다. 기본 문법에는
`status_pattern`이 없으므로 기본 동작은 그대로다(기존 테스트가 그대로 통과).
"""

from __future__ import annotations

import random
from typing import Any

import pytest

from agent_console_conditions import builtin_operators
from agent_console_contracts.constants import ErrorCodes, KnownIssueCodes
from agent_console_contracts.sdd import (
    KnownSyntaxSources,
    SddSettings,
    SpecIndex,
    SpecRules,
    SpecSyntax,
)
from agent_console_sdd import (
    DEFAULT_FIELD_FORMAT,
    TaskPatchError,
    check_rules,
    compile_syntax,
    effective_syntax,
    find_task,
    load_default_syntax,
    parse_spec,
    patch_task,
    split_lines,
)
from agent_console_sdd.testing import (
    DEFAULT_NAMES,
    RENAMED_NAMES,
    RENAMED_SYNTAX,
    sample_files,
    sample_spec,
)

D, S, P = KnownSyntaxSources.DEFAULT, KnownSyntaxSources.SETTINGS, KnownSyntaxSources.SPEC
DOCS = [{"id": "t", "title": "작업", "file": "t.md", "roles": ["tasks"]}]

# `- TODO: 결제 [owner: be]` 형식(사용자가 만드는 문법 데이터의 예 — 패키지 데이터가 아니다).
COLON_TASK: dict[str, Any] = {
    "list_item": "bullet",
    "status_pattern": r"^(?P<status>[A-Z]+):\s+",
    "status_format": "{marker}: ",
    "statuses": [
        {"id": "todo", "marker": "TODO"},
        {"id": "doing", "marker": "DOING"},
        {"id": "done", "marker": "DONE", "done": True},
    ],
}
COLON = compile_syntax(effective_syntax(SpecRules.model_validate({"syntax": {"task": COLON_TASK}})))


def _parse(text: str, syntax: Any = COLON) -> SpecIndex:
    return parse_spec(sample_spec(*DOCS), {"t.md": text}, syntax)


def _rows(index: SpecIndex) -> list[tuple[object, ...]]:
    return [(t.key, t.id, t.status, t.title, t.fields, t.dependencies) for t in index.tasks]


def _codes(index: SpecIndex) -> list[str]:
    return sorted(i.code for i in index.issues)


# ---------------------------------------------------------------- 읽기


def test_colon_word_format() -> None:
    text = (
        "## 1단계\n"
        "- TODO: 결제 [owner: be]\n"
        "- DONE: 1.2 배포 [owner: ops] [depends: —]\n"
        "- DOING: 1.3 검증 [depends: 1.2]\n"
        "- 1.4 상태 없음 [depends: 1.3]\n"
        "- WAIT: 1.5 모르는 낱말\n"
        "  - TODO: 1.6 하위 작업\n"
        "```\n- TODO: 9.9 코드 안\n```\n"
    )
    index = _parse(text)
    assert _rows(index) == [
        ("@t:1", None, "todo", "결제", {"owner": "be"}, []),
        ("1.2", "1.2", "done", "배포", {"owner": "ops", "depends": "—"}, []),
        ("1.3", "1.3", "doing", "검증", {"depends": "1.2"}, ["1.2"]),
        ("1.4", "1.4", "todo", "상태 없음", {"depends": "1.3"}, ["1.3"]),  # 안 맞음 = 첫 상태
        ("1.5", "1.5", "todo", "모르는 낱말", {}, []),
        ("1.6", "1.6", "todo", "하위 작업", {}, []),
    ]
    by_key = {t.key: t for t in index.tasks}
    assert by_key["1.3"].ready is True  # 의존 1.2가 끝남
    assert (index.stages[0].done, index.stages[0].total) == (1, 6)
    # 묶음은 맞았는데 모르는 낱말 → sdd.unknown_status_marker(첫 상태로 봄).
    unknown = [i for i in index.issues if i.code == KnownIssueCodes.SDD_UNKNOWN_STATUS_MARKER]
    assert [(i.line, i.details) for i in unknown] == [(6, {"marker": "WAIT"})]
    assert "줄 머리 상태" in unknown[0].message
    assert by_key["1.5"].issues == unknown
    assert _codes(index) == [KnownIssueCodes.SDD_UNKNOWN_STATUS_MARKER]


def test_ordered_word_format() -> None:
    syntax = effective_syntax(
        SpecRules.model_validate(
            {
                "syntax": {
                    "task": {
                        "list_item": "ordered",
                        "status_pattern": r"^(?P<status>TODO|DONE)\s+",
                        "statuses": [
                            {"id": "todo", "marker": "TODO"},
                            {"id": "done", "marker": "DONE", "done": True},
                        ],
                    }
                }
            }
        )
    )
    text = "1. DONE 배포\n2. TODO 2.1 검증 [owner: qa]\n3) 설명만\n- DONE 글머리는 작업 아님\n"
    index = parse_spec(sample_spec(*DOCS), {"t.md": text}, syntax)
    assert _rows(index) == [
        ("@t:1", None, "done", "배포", {}, []),
        ("2.1", "2.1", "todo", "검증", {"owner": "qa"}, []),
        ("@t:3", None, "todo", "설명만", {}, []),
    ]
    assert index.issues == []


def test_status_word_in_the_middle_is_cut_out() -> None:
    """정규식이 본문 가운데·끝에 맞아도 그 범위만 떼고 id·필드·제목을 읽고, 그 범위만 고친다."""
    syntax = compile_syntax(
        effective_syntax(
            SpecRules.model_validate(
                {
                    "syntax": {
                        "task": {
                            **COLON_TASK,
                            "status_pattern": r"\s+\((?P<status>TODO|DONE)\)\s*$",
                        }
                    }
                }
            )
        )
    )
    text = "- 1.1 결제 [owner: be] (DONE)\n"
    index = _parse(text, syntax)
    assert _rows(index) == [("1.1", "1.1", "done", "결제", {"owner": "be"}, [])]
    task = index.tasks[0]
    out = patch_task(text, task, syntax=syntax, status="todo", fields={"owner": "qa"})
    assert out == "- 1.1 결제 [owner: qa] (TODO)\n"
    # 줄 끝 상태 뒤에 필드를 덧붙이면 상태를 다시 읽을 수 없다 → 고치지 않고 거부.
    with pytest.raises(TaskPatchError) as err:
        patch_task(text, task, syntax=syntax, fields={"due": "11/30"})
    assert err.value.code == ErrorCodes.VALIDATION_FAILED
    assert err.value.details == {"reason": "status_lost"}


def test_checkbox_wins_over_word_in_bullet_mode() -> None:
    index = _parse("- [x] 1 체크 칸 [owner: a]\n- DONE: 2 낱말\n", _with_checkbox_markers())
    assert [(t.key, t.status) for t in index.tasks] == [("1", "done"), ("2", "done")]


def _with_checkbox_markers() -> Any:
    task = {
        **COLON_TASK,
        "statuses": [
            {"id": "todo", "marker": ["TODO", " "]},
            {"id": "done", "marker": ["DONE", "x"], "done": True},
        ],
    }
    return compile_syntax(effective_syntax(SpecRules.model_validate({"syntax": {"task": task}})))


def test_renamed_word_syntax_gives_same_result() -> None:
    """R0: 체크 칸 표본을 줄 머리 낱말로 바꾸고 필드·상태·구분자 이름을 모두 바꿔도 같은 결과."""
    base = parse_spec(sample_spec(), sample_files(), effective_syntax())

    files = sample_files(RENAMED_NAMES)
    files["tasks.md"] = (
        files["tasks.md"].replace("- [v] ", "- 닫힘 > ").replace("- [.] ", "- 열림 > ")
    )
    task = {
        **RENAMED_SYNTAX["task"],
        "list_item": "bullet",
        "max_depth": 1,  # 글머리 모드: 들여쓴 본문 목록은 작업이 아니다(체크 칸 표본과 같게)
        "status_pattern": r"^(?P<status>열림|닫힘)\s*>\s+",
        "status_format": "{marker} > ",
        "statuses": [
            {"id": "open", "marker": "열림"},
            {"id": "closed", "marker": "닫힘", "done": True},
        ],
    }
    syntax = effective_syntax(
        SpecRules(syntax=SpecSyntax.model_validate({**RENAMED_SYNTAX, "task": task})),
        SddSettings(include_default_syntax=False),
    )
    renamed = parse_spec(sample_spec(), files, syntax)
    assert renamed.issues == []
    status_map = {"todo": "open", "done": "closed"}
    field_map = {
        DEFAULT_NAMES["owner"]: "who",
        DEFAULT_NAMES["req"]: "needs",
        DEFAULT_NAMES["depends"]: "after",
    }
    want = [
        (
            t.key,
            t.title,
            status_map[t.status],
            t.dependencies,
            t.requirements,
            t.ready,
            t.body,
            [field_map[f] for f in t.fields],
        )
        for t in base.tasks
    ]
    got = [
        (t.key, t.title, t.status, t.dependencies, t.requirements, t.ready, t.body, list(t.fields))
        for t in renamed.tasks
    ]
    assert got == want

    # 이름을 바꾼 문법으로도 상태 없는 줄 → status_format, 필드 덧붙이기 → 패키지 기본 모양.
    text = "- 1 새 작업\n"
    t0 = parse_spec(sample_spec(*DOCS), {"t.md": text}, syntax).tasks[0]
    out = patch_task(text, t0, syntax=syntax, status="closed", fields={"who": "qa"})
    assert out == "- 닫힘 > 1 새 작업 [who: qa]\n"


# ---------------------------------------------------------------- 고치기


def test_patch_replaces_only_status_group() -> None:
    text = "  - TODO:  1.2 배포 [owner: ops]\t\r\n"
    task = _parse(text).tasks[0]
    out = patch_task(text, task, syntax=COLON, status="done")
    assert out == "  - DONE:  1.2 배포 [owner: ops]\t\r\n"
    assert _parse(out).tasks[0].status == "done"
    # 같은 상태면 그대로.
    assert patch_task(out, _parse(out).tasks[0], syntax=COLON, status="done") == out


def test_patch_inserts_status_format_when_no_status() -> None:
    text = "- 1.4 상태 없음 [depends: —]\n"
    task = _parse(text).tasks[0]
    assert task.status == "todo"
    out = patch_task(text, task, syntax=COLON, status="doing")
    assert out == "- DOING: 1.4 상태 없음 [depends: —]\n"
    again = _parse(out).tasks[0]
    assert (again.key, again.status, again.title, again.fields) == (
        "1.4",
        "doing",
        "상태 없음",
        {"depends": "—"},
    )


def test_status_format_omitted_uses_package_default() -> None:
    task_syntax = {**COLON_TASK, "status_pattern": r"^(?P<status>[A-Z]+):?\s+"}
    del task_syntax["status_format"]
    syntax = compile_syntax(
        effective_syntax(SpecRules.model_validate({"syntax": {"task": task_syntax}}))
    )
    assert syntax.status_format == "{marker} "
    text = "1. 번호 작업\n"
    syntax_ordered = compile_syntax(
        effective_syntax(
            SpecRules.model_validate({"syntax": {"task": {**task_syntax, "list_item": "ordered"}}})
        )
    )
    task = parse_spec(sample_spec(*DOCS), {"t.md": text}, syntax_ordered).tasks[0]
    assert patch_task(text, task, syntax=syntax_ordered, status="done") == "1. DONE 번호 작업\n"


def test_status_format_that_cannot_be_read_back_is_rejected() -> None:
    task_syntax = {**COLON_TASK, "status_format": "{marker}- "}  # 정규식이 다시 읽지 못함
    syntax = compile_syntax(
        effective_syntax(SpecRules.model_validate({"syntax": {"task": task_syntax}}))
    )
    text = "- 1 하나\n"
    task = _parse(text, syntax).tasks[0]
    with pytest.raises(TaskPatchError) as err:
        patch_task(text, task, syntax=syntax, status="done")
    assert err.value.code == ErrorCodes.VALIDATION_FAILED


def test_field_format_from_syntax_data_and_argument_wins() -> None:
    task_syntax = {
        **COLON_TASK,
        "field_pattern": r"\((?P<key>\w+)=(?P<value>[^)]*)\)",
        "field_format": "({key}={value})",
    }
    syntax = compile_syntax(
        effective_syntax(SpecRules.model_validate({"syntax": {"task": task_syntax}}))
    )
    text = "- TODO: 1 하나 (owner=a)\n"
    task = _parse(text, syntax).tasks[0]
    assert task.fields == {"owner": "a"}
    out = patch_task(text, task, syntax=syntax, fields={"due": "11/30"})
    assert out == "- TODO: 1 하나 (owner=a) (due=11/30)\n"
    # 인자를 주면 인자가 먼저다.
    out2 = patch_task(
        text, task, syntax=syntax, fields={"due": "x"}, field_format="({key}= {value})"
    )
    assert out2 == "- TODO: 1 하나 (owner=a) (due= x)\n"
    # 사용자 모양의 모르는 자리·중괄호는 글자 그대로(str.format 오류가 나지 않는다).
    braces = {**task_syntax, "field_format": "({key}={value}){0}"}
    syntax_b = compile_syntax(
        effective_syntax(SpecRules.model_validate({"syntax": {"task": braces}}))
    )
    assert patch_task(text, task, syntax=syntax_b, fields={"due": "y"}).endswith("(due=y){0}\n")


# ---------------------------------------------------------------- 속성 테스트(고정 시드)

_WORDS = ["TODO", "DOING", "DONE", None, None]
_WORD_OF = {"todo": "TODO", "doing": "DOING", "done": "DONE"}
_EOLS = ["\n", "\r\n"]


def _random_doc(rng: random.Random) -> str:
    out: list[str] = []
    n = 0
    for _ in range(rng.randint(1, 25)):
        eol = rng.choice(_EOLS)
        roll = rng.random()
        if roll < 0.1:
            out.append(f"## 단계 {rng.randint(1, 9)}{eol}{eol}")
            continue
        if roll < 0.15:
            out.append(f"```{eol}- TODO: 99.{n} 코드 안{eol}```{eol}")
            continue
        n += 1
        indent = rng.choice(["", "", "  ", "\t", "    "]) if out else ""
        word = rng.choice(_WORDS)
        head = f"{word}:{rng.choice([' ', '  ', chr(9)])}" if word else ""
        fields = []
        for name in rng.sample(["owner", "req", "depends", "x-note"], rng.randint(0, 3)):
            value = rng.choice(["a", "R1, R2", "—", "1.1~1.3", "값 있음"])
            fields.append(f"[{name}:{rng.choice(['', ' ', '  '])}{value}]")
        tail = rng.choice(["", " ", "\t", "  "])
        title = rng.choice(["제목", "Title with `code`", "긴 제목 하나 둘 셋"])
        task_id = f"{n}.{rng.randint(0, 3)} " if rng.random() < 0.8 else ""
        out.append(f"{indent}- {head}{task_id}{title} {' '.join(fields)}{tail}{eol}")
        if rng.random() < 0.3:
            out.append(f"{indent}  본문 {n}{rng.choice(_EOLS)}")
    return "".join(out)


@pytest.mark.parametrize("seed", range(120))
def test_parse_patch_parse_property(seed: int) -> None:
    rng = random.Random(seed)
    text = _random_doc(rng)
    before = _parse(text)
    assert not [i for i in before.issues if i.code == KnownIssueCodes.SDD_PARSE_TIMEOUT]
    if not before.tasks:
        return
    target = rng.choice(before.tasks)
    status = rng.choice([None, "todo", "doing", "done"])
    names = ["owner", "req", "depends", "new-field"]
    fields: dict[str, str | None] = {
        name: rng.choice([None, "b", "R3, R4", "6R.1"]) for name in rng.sample(names, 2)
    }
    out = patch_task(text, target, syntax=COLON, status=status, fields=fields)

    old_lines, new_lines = split_lines(text), split_lines(out)
    assert len(old_lines) == len(new_lines)
    for i, (a, b) in enumerate(zip(old_lines, new_lines, strict=True)):
        if i != target.line - 1:
            assert a == b  # 바꾼 줄 밖 바이트 불변
    a, b = old_lines[target.line - 1], new_lines[target.line - 1]
    assert a[len(a.rstrip("\r\n")) :] == b[len(b.rstrip("\r\n")) :]  # 줄바꿈 종류 그대로
    assert b[: len(b) - len(b.lstrip(" \t"))] == a[: len(a) - len(a.lstrip(" \t"))]  # 들여쓰기

    after = _parse(out)
    assert [t.key for t in after.tasks] == [t.key for t in before.tasks]
    for old, new in zip(before.tasks, after.tasks, strict=True):
        if old.key != target.key:
            assert (old.status, old.fields, old.line_hash) == (
                new.status,
                new.fields,
                new.line_hash,
            )
            continue
        assert new.status == (status or old.status)
        assert new.title == old.title
        want = dict(old.fields)
        for key, value in fields.items():
            if value is None:
                want.pop(key, None)
            else:
                want[key] = value
        assert new.fields == want
    # 상태만 바꾸면 그 줄에서도 상태 낱말 범위 밖 바이트는 그대로다(없으면 본문 앞에 status_format).
    if status is not None:
        only = patch_task(text, target, syntax=COLON, status=status)
        ao, bo = old_lines[target.line - 1], split_lines(only)[target.line - 1]
        new_word = _WORD_OF[status]
        old_word = next(
            (w for w in _WORD_OF.values() if ao.lstrip(" \t-").startswith(w + ":")), None
        )
        if old_word is not None:
            start = ao.index(old_word)
            assert bo == ao[:start] + new_word + ao[start + len(old_word) :]
        else:
            assert bo == ao.replace("- ", f"- {new_word}: ", 1)


# ---------------------------------------------------------------- 문법 검사·기본값


def test_default_syntax_has_no_status_pattern_and_formats_are_data() -> None:
    default = load_default_syntax()
    assert default.task is not None
    assert default.task.status_pattern is None
    assert default.task.status_format == "{marker} "
    assert default.task.field_format == DEFAULT_FIELD_FORMAT
    eff = effective_syntax()
    compiled = compile_syntax(eff)
    assert compiled.status_pattern is None
    assert compiled.issues == []
    assert eff.sources["/task/status_format"] == D
    assert eff.sources["/task/field_format"] == D
    # 기본 문법을 꺼도 고쳐 쓰기 모양은 패키지 데이터 값.
    off = compile_syntax(effective_syntax(settings=SddSettings(include_default_syntax=False)))
    assert (off.status_format, off.field_format) == ("{marker} ", DEFAULT_FIELD_FORMAT)
    # 새 키도 층마다 출처가 남는다.
    layered = effective_syntax(
        SpecRules.model_validate({"syntax": {"task": {"status_pattern": r"^(?P<status>\w+)\s"}}}),
        SddSettings.model_validate({"syntax": {"task": {"status_format": "{marker}: "}}}),
    )
    assert layered.sources["/task/status_pattern"] == P
    assert layered.sources["/task/status_format"] == S
    assert layered.sources["/task/field_format"] == D


def test_default_checkbox_behaviour_unchanged_with_word_lines() -> None:
    """기본 문법(체크 칸)은 낱말 줄을 작업으로 읽지 않는다."""
    index = parse_spec(
        sample_spec(*DOCS), {"t.md": "- TODO: 1 낱말\n- [ ] 2 체크\n"}, effective_syntax()
    )
    assert [(t.key, t.status, t.title) for t in index.tasks] == [("2", "todo", "체크")]


def _check(task: dict[str, Any]) -> list[Any]:
    ops = {op.descriptor.id: op for op in builtin_operators()}
    return check_rules({"syntax": {"task": task}}, operators=ops)


def test_check_warns_when_status_pattern_is_ignored() -> None:
    no_group = _check({**COLON_TASK, "status_pattern": r"^(TODO|DONE):\s+"})
    assert [(i.code, i.severity, i.path, i.details) for i in no_group] == [
        (
            KnownIssueCodes.SDD_STATUS_PATTERN_IGNORED,
            "warning",
            "/syntax/task/status_pattern",
            {"reason": "no_status_group", "source": P},
        )
    ]
    with_checkbox = _check({"list_item": "checkbox", "status_pattern": r"^(?P<status>TODO)\s+"})
    assert [(i.code, i.details["reason"]) for i in with_checkbox] == [
        (KnownIssueCodes.SDD_STATUS_PATTERN_IGNORED, "checkbox")
    ]
    bad = _check({**COLON_TASK, "status_pattern": r"(?P<status>"})
    assert [i.code for i in bad] == [KnownIssueCodes.SDD_INVALID_PATTERN]
    assert _check(COLON_TASK) == []
    # 쓰지 않는 정규식이면 체크 칸 목록 동작 그대로(낱말 줄은 작업이 아님).
    syntax = compile_syntax(
        effective_syntax(
            SpecRules.model_validate(
                {"syntax": {"task": {"status_pattern": r"^(?P<status>TODO)\s+"}}}
            )
        )
    )
    assert syntax.status_pattern is None
    index = _parse("- TODO 1 낱말\n- [x] 2 체크\n", syntax)
    assert [(t.key, t.status) for t in index.tasks] == [("2", "done")]
    assert _codes(index) == [KnownIssueCodes.SDD_STATUS_PATTERN_IGNORED]


def test_word_format_large_document_relaxed() -> None:
    """§6R.14 relaxed: 작업 3,000개 낱말 형식도 작업량을 그대로 읽는다(벽시계 단언 없음)."""
    lines = ["# 작업\n"]
    for i in range(3000):
        word = "DONE" if i < 1000 else "TODO"
        deps = f"T{i - 1}" if i else "—"
        lines.append(f"- {word}: T{i} 작업 {i} [owner: team-{i % 7}] [depends: {deps}]\n")
    syntax = compile_syntax(
        effective_syntax(SpecRules.model_validate({"syntax": {"task": COLON_TASK}})),
        regex_timeout=600.0,  # 벽시계에 기대지 않는다(test_agent_console_sdd_perf와 같음)
    )
    index = _parse("".join(lines), syntax)
    assert len(index.tasks) == 3000
    assert sum(t.status == "done" for t in index.tasks) == 1000
    assert index.issues == []
    task = find_task(index, "T2500")
    assert task is not None
    out = patch_task("".join(lines), task, syntax=syntax, status="done")
    assert "- DONE: T2500 작업 2500" in out
