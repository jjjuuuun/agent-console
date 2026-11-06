"""작업 줄 고치기(design §6R.1.4, 6R.10): parse → patch → parse 속성 테스트와 오류."""

from __future__ import annotations

import random

import pytest

from agent_console_contracts.sdd import SpecRules, SpecSyntax
from agent_console_sdd import (
    TaskChangedError,
    TaskPatchError,
    compile_syntax,
    effective_syntax,
    find_task,
    line_hash,
    merge_syntax,
    parse_spec,
    patch_task,
    split_lines,
)
from agent_console_sdd.testing import sample_spec

DOCS = [{"id": "t", "title": "작업", "file": "t.md", "roles": ["tasks"]}]
RULES = SpecRules.model_validate(
    {
        "task_statuses": [
            {"id": "todo", "marker": " "},
            {"id": "doing", "marker": "~"},
            {"id": "review", "marker": "?"},
            {"id": "done", "marker": ["x", "X"], "done": True},
        ]
    }
)
SYNTAX = compile_syntax(effective_syntax(RULES))


def _index(text: str):  # type: ignore[no-untyped-def]
    return parse_spec(sample_spec(*DOCS), {"t.md": text}, SYNTAX)


def test_patch_status_and_fields_keeps_other_bytes() -> None:
    text = (
        "# 작업\r\n"
        "- [ ] 1.0 부모\r\n"
        "\t- [ ] 1.1 하나 [owner: a]  [req: R1]\t \r\n"
        "  본문\r\n"
        "- [ ] 1.2 둘\n"
    )
    task = find_task(_index(text), "1.1")
    assert task is not None
    out = patch_task(
        text,
        task,
        syntax=SYNTAX,
        status="doing",
        fields={"owner": "b", "req": None, "due": "11/07", "nothing": None},
    )
    assert out == (
        "# 작업\r\n- [ ] 1.0 부모\r\n\t- [~] 1.1 하나 [owner: b] [due: 11/07]\t \r\n"
        "  본문\r\n- [ ] 1.2 둘\n"
    )
    again = find_task(_index(out), "1.1")
    assert again is not None
    assert again.status == "doing"
    assert again.fields == {"owner": "b", "due": "11/07"}
    # 바뀐 것이 없으면 원문 그대로.
    assert patch_task(out, again, syntax=SYNTAX, status="doing", fields={"owner": "b"}) == out
    # 같은 상태의 다른 표시 문자(X)는 바꾸지 않는다.
    upper = "- [X] 1 끝\n"
    done = _index(upper).tasks[0]
    assert patch_task(upper, done, syntax=SYNTAX, status="done") == upper


def test_line_hash_conflict() -> None:
    text = "- [ ] 1 하나\n- [ ] 2 둘\n"
    task = _index(text).tasks[0]
    # 다른 줄을 고친 원문은 통과한다.
    other = text.replace("2 둘", "2 둘 고침")
    assert patch_task(other, task, syntax=SYNTAX, status="done").startswith("- [x] 1 하나\n")
    # 같은 줄을 고친 원문은 충돌.
    changed = text.replace("1 하나", "1 하나 고침")
    with pytest.raises(TaskChangedError) as err:
        patch_task(changed, task, syntax=SYNTAX, status="done")
    assert err.value.code == "sdd.task_changed"
    assert err.value.current.text == "- [ ] 1 하나 고침"
    assert err.value.current.line_hash == line_hash("- [ ] 1 하나 고침\n")
    # 줄이 사라졌다.
    with pytest.raises(TaskChangedError):
        patch_task("", task, syntax=SYNTAX, status="done")


def test_patch_errors() -> None:
    text = "- [ ] 1 하나\n"
    task = _index(text).tasks[0]
    with pytest.raises(TaskPatchError) as err:
        patch_task(text, task, syntax=SYNTAX, status="nope")
    assert err.value.code == "sdd.unknown_state"
    with pytest.raises(TaskPatchError) as err:
        patch_task(text, task, syntax=SYNTAX, fields={"owner": "a\nb"})
    assert err.value.code == "validation_failed"
    with pytest.raises(TaskPatchError) as err:  # 다시 읽을 수 없는 값(] 포함)
        patch_task(text, task, syntax=SYNTAX, fields={"owner": "a]b"})
    assert err.value.code == "validation_failed"
    assert not isinstance(err.value, TaskChangedError)


def test_bullet_without_checkbox_gets_one() -> None:
    syntax = merge_syntax(
        ("d", effective_syntax().syntax),
        ("s", SpecSyntax.model_validate({"task": {"list_item": "bullet"}})),
    )
    text = "- 1 체크 칸 없음\n"
    task = parse_spec(sample_spec(*DOCS), {"t.md": text}, syntax).tasks[0]
    assert task.status == "todo"
    out = patch_task(text, task, syntax=syntax, status="done")
    assert out == "- [x] 1 체크 칸 없음\n"
    assert parse_spec(sample_spec(*DOCS), {"t.md": out}, syntax).tasks[0].status == "done"


# ---------------------------------------------------------------- 속성 테스트(고정 시드)

_MARKERS = [" ", "~", "?", "x", "X"]
_EOLS = ["\n", "\r\n"]


def _random_doc(rng: random.Random) -> str:
    out: list[str] = []
    n = 0
    for _ in range(rng.randint(1, 25)):
        eol = rng.choice(_EOLS)
        roll = rng.random()
        if roll < 0.1:
            out.append(f"## 단계 {rng.randint(1, 9)}{eol}")
            out.append(eol)
            continue
        if roll < 0.15:
            out.append(f"```{eol}- [ ] 99.{n} 코드 안{eol}```{eol}")
            continue
        n += 1
        indent = rng.choice(["", "", "  ", "\t", "    "]) if out else ""
        fields = []
        for name in rng.sample(["owner", "req", "depends", "x-note"], rng.randint(0, 3)):
            value = rng.choice(["a", "R1, R2", "—", "1.1~1.3", "값 있음"])
            fields.append(f"[{name}:{rng.choice(['', ' ', '  '])}{value}]")
        tail = rng.choice(["", " ", "\t", "  "])
        title = rng.choice(["제목", "Title with `code`", "긴 제목 하나 둘 셋"])
        out.append(
            f"{indent}- [{rng.choice(_MARKERS)}] {n}.{rng.randint(0, 3)} {title} "
            f"{' '.join(fields)}{tail}{eol}"
        )
        if rng.random() < 0.3:
            out.append(f"{indent}  본문 {n}{rng.choice(_EOLS)}")
    return "".join(out)


@pytest.mark.parametrize("seed", range(120))
def test_parse_patch_parse_property(seed: int) -> None:
    rng = random.Random(seed)
    text = _random_doc(rng)
    before = _index(text)
    if not before.tasks:
        return
    target = rng.choice(before.tasks)
    status = rng.choice(["todo", "doing", "review", "done"])
    names = ["owner", "req", "depends", "new-field"]
    fields: dict[str, str | None] = {
        name: rng.choice([None, "b", "R3, R4", "6R.1"]) for name in rng.sample(names, 2)
    }
    out = patch_task(text, target, syntax=SYNTAX, status=status, fields=fields)

    old_lines, new_lines = split_lines(text), split_lines(out)
    assert len(old_lines) == len(new_lines)
    for i, (a, b) in enumerate(zip(old_lines, new_lines, strict=True)):
        if i != target.line - 1:
            assert a == b  # 바꾼 줄 밖 바이트 불변
    a, b = old_lines[target.line - 1], new_lines[target.line - 1]
    assert a[len(a.rstrip("\r\n")) :] == b[len(b.rstrip("\r\n")) :]  # 줄바꿈 종류 그대로
    assert b[: len(b) - len(b.lstrip(" \t"))] == a[: len(a) - len(a.lstrip(" \t"))]  # 들여쓰기

    after = _index(out)
    assert [t.key for t in after.tasks] == [t.key for t in before.tasks]
    for old, new in zip(before.tasks, after.tasks, strict=True):
        if old.key != target.key:
            assert (old.status, old.fields, old.line_hash) == (
                new.status,
                new.fields,
                new.line_hash,
            )
            # 본문이 바뀌는 것은 고친 줄이 그 작업의 하위 목록일 때뿐이다.
            if a.strip() not in old.body:
                assert old.body == new.body
            continue
        assert new.status == status
        assert new.title == old.title
        assert new.body == old.body
        expected = dict(old.fields)
        for name, value in fields.items():
            if value is None:
                expected.pop(name, None)
            else:
                expected[name] = value
        assert new.fields == expected
