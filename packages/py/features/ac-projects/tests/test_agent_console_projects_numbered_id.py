"""등록 id의 겹치면 ``-n`` 규칙은 ``agent_console_numbered_id`` 하나다(사본 없음, 동작 같음)."""

from __future__ import annotations

from collections.abc import Collection

import pytest

from agent_console_projects import MAX_ID_LENGTH, registration_id, suggest_project_id


def _before(manifest_id: str, taken_ids: Collection[str]) -> str:
    """합치기 전 구현(비교 기준)."""
    taken = {t.casefold() for t in taken_ids}
    if manifest_id.casefold() not in taken:
        return manifest_id
    n = 2
    while True:
        suffix = f"-{n}"
        candidate = manifest_id[: MAX_ID_LENGTH - len(suffix)] + suffix
        if candidate.casefold() not in taken:
            return candidate
        n += 1


LONG = "a" * MAX_ID_LENGTH


@pytest.mark.parametrize(
    ("manifest_id", "taken"),
    [
        ("app", []),
        ("app", ["App"]),
        ("app", ["app", "APP-2", "app-3"]),
        ("App", ["app"]),
        (LONG, [LONG]),
        (LONG, [LONG, "a" * (MAX_ID_LENGTH - 2) + "-2"]),
        ("x" * (MAX_ID_LENGTH - 1), ["x" * (MAX_ID_LENGTH - 1), "x" * (MAX_ID_LENGTH - 3) + "-2"]),
        ("p", [f"p-{n}" for n in range(2, 12)] + ["p"]),
    ],
)
def test_registration_id_same_as_before(manifest_id: str, taken: list[str]) -> None:
    found = registration_id(manifest_id, taken)
    assert found == _before(manifest_id, taken)
    assert len(found) <= MAX_ID_LENGTH


def test_suggest_project_id_uses_same_rule() -> None:
    assert suggest_project_id("/w/payments", taken_ids=["Payments"], flavor="posix") == (
        "payments-2"
    )
