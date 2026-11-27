"""공용 픽스처: 대조가 통과하는 완전한 임시 저장소(문서에 들어가는 글은 영어 — 공개 문서 규칙)."""

from __future__ import annotations

from pathlib import Path

import pytest
from extdocs_testkit import MODULE_SOURCE, Repo


def notes_tool(repo: Repo) -> str:
    m = repo.mod("notes")
    return f"""\
[tool.agent-console]
internal-ports = [{{ port = "notes.store", reason = "Used only inside the notes module" }}]
internal-groups = [{{ group = "agent_console.server_modules", reason = "Not under test" }}]

[tool.agent-console.extension-points.note-kind]
title = "Note kind"
area = "memory"
summary = "Adds one more note kind"
registration = {{ kind = "entry-point", group = "{m}:NOTE_KINDS_GROUP" }}
interface = ["{m}:NoteKind"]
example = {{ kind = "package", path = "examples/extensions/example-notes" }}
guide = "memory.md#note-kind"

[tool.agent-console.extension-points.note-hooks]
title = "Note hooks"
area = "memory"
summary = "Adds work to run after a note is saved"
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
                f'"""Notes."""\nfrom {m}._plugins import NOTE_KINDS_GROUP\n\n\n'
                'class NoteKind:\n    """Note kind plugin."""\n\n\n'
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
