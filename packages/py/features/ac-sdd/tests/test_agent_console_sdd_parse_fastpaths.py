"""파싱 빠른 길(성능 기준 §6R.14를 맞추려고 둔 것)이 원래 동작과 같은지: 한 줄 본문 =
`textwrap.dedent`, 빈 줄 건너뛰기, 파싱 동안 순환 GC 멈춤과 되돌림."""

from __future__ import annotations

import gc
import textwrap
from collections.abc import Iterator, Mapping

import pytest

from agent_console_sdd import effective_syntax, parse_spec
from agent_console_sdd.testing import sample_spec


@pytest.mark.parametrize(
    "body_line",
    ["  본문", "\t본문 줄", "    깊게 \t들여 쓴 줄  ", "  \t  섞인 들여쓰기", "  - 하위 목록 줄"],
)
def test_one_line_body_equals_dedent(body_line: str) -> None:
    files = {"tasks.md": f"- [ ] T1 작업\n{body_line}\n- [ ] T2 다음\n", "requirements.md": ""}
    index = parse_spec(sample_spec(), files, effective_syntax())
    assert [t.key for t in index.tasks] == ["T1", "T2"]
    assert index.tasks[0].body == textwrap.dedent(body_line).strip("\n")


def test_multi_line_body_still_dedents_common_margin() -> None:
    files = {"tasks.md": "- [ ] T1 작업\n    첫 줄\n      둘째 줄\n", "requirements.md": ""}
    index = parse_spec(sample_spec(), files, effective_syntax())
    assert index.tasks[0].body == "첫 줄\n  둘째 줄"


def test_blank_lines_never_become_requirements() -> None:
    files = {"requirements.md": "\n\n**R1** 첫 요구\n\r\n\n**R2** 둘째\n\n", "tasks.md": ""}
    index = parse_spec(sample_spec(), files, effective_syntax())
    assert [(r.id, r.line) for r in index.requirements] == [("R1", 3), ("R2", 6)]


class _Files(Mapping[str, str]):
    """`get`이 불릴 때 GC 상태를 적는 문서 묶음(고장 내기 선택)."""

    def __init__(self, data: dict[str, str], *, fail: bool = False) -> None:
        self._data, self._fail = data, fail
        self.gc_during: list[bool] = []

    def __getitem__(self, key: str) -> str:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: str, default: object = None) -> str | None:  # type: ignore[override]
        self.gc_during.append(gc.isenabled())
        if self._fail:
            raise RuntimeError("읽기 실패")
        return self._data.get(key)


@pytest.fixture
def gc_state() -> Iterator[None]:
    was = gc.isenabled()
    yield
    if was:
        gc.enable()
    else:
        gc.disable()


@pytest.mark.usefixtures("gc_state")
def test_parse_pauses_gc_and_restores_it() -> None:
    gc.enable()
    files = _Files({"tasks.md": "- [ ] T1 작업\n", "requirements.md": "**R1** 요구\n"})
    index = parse_spec(sample_spec(), files, effective_syntax())
    assert [t.key for t in index.tasks] == ["T1"]
    assert files.gc_during
    assert not any(files.gc_during)  # 파싱하는 동안 꺼짐
    assert gc.isenabled()  # 끝나면 되돌림

    broken = _Files({"tasks.md": ""}, fail=True)
    with pytest.raises(RuntimeError):
        parse_spec(sample_spec(), broken, effective_syntax())
    assert gc.isenabled()  # 예외에도 되돌림


@pytest.mark.usefixtures("gc_state")
def test_parse_leaves_disabled_gc_disabled() -> None:
    gc.disable()
    parse_spec(sample_spec(), {"tasks.md": "- [ ] T1 작업\n"}, effective_syntax())
    assert not gc.isenabled()
