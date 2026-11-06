"""공용 픽스처: 대조가 통과하는 완전한 임시 저장소."""

from __future__ import annotations

from pathlib import Path

import pytest
from extdocs_testkit import MODULE_SOURCE, Repo


def notes_tool(repo: Repo) -> str:
    m = repo.mod("notes")
    return f"""\
[tool.agent-console]
internal-ports = [{{ port = "notes.store", reason = "노트 모듈 안에서만 쓴다" }}]
internal-groups = [{{ group = "agent_console.server_modules", reason = "시험 대상 아님" }}]

[tool.agent-console.extension-points.note-kind]
title = "노트 종류"
area = "memory"
summary = "노트 종류를 하나 더한다"
registration = {{ kind = "entry-point", group = "{m}:NOTE_KINDS_GROUP" }}
interface = ["{m}:NoteKind"]
example = {{ kind = "package", path = "examples/extensions/example-notes" }}
guide = "memory.md#note-kind"

[tool.agent-console.extension-points.note-hooks]
title = "노트 훅"
area = "memory"
summary = "노트 저장 뒤에 할 일을 더한다"
registration = {{ kind = "port", port = "{m}.module:HOOKS" }}
example = {{ kind = "snippet" }}
guide = "memory.md#note-hooks"
"""


def build_notes(repo: Repo, *, tool: str | None = None, constant: str | None = None) -> None:
    m = repo.mod("notes")
    repo.package(
        "ac-notes",
        "agent-console-notes",
        files={
            f"{m}/__init__.py": (
                f'"""노트."""\nfrom {m}._plugins import NOTE_KINDS_GROUP\n\n\n'
                'class NoteKind:\n    """노트 종류 플러그인."""\n\n\n'
                '__all__ = ["NOTE_KINDS_GROUP", "NoteKind"]\n'
            ),
            f"{m}/_plugins.py": constant or 'NOTE_KINDS_GROUP = "agent_console.note_kinds"\n',
            f"{m}/module.py": MODULE_SOURCE,
        },
        entry_points=(
            '[project.entry-points."agent_console.server_modules"]\n'
            f'mod-notes = "{m}.module:module"\n\n'
            '[project.entry-points."agent_console.note_kinds"]\n'
            f'plain = "{m}:NoteKind"\n'
        ),
        tool=notes_tool(repo) if tool is None else tool,
    )
    repo.example("example-notes", ["note-kind"])


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    r = Repo(tmp_path)
    build_notes(r)
    return r
