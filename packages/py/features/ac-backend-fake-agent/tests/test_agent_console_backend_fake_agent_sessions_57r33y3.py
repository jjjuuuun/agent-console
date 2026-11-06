"""5.7R.33y3 X38: fake 백엔드 세션 기록 흉내(``session_dir``)와 보관·복원."""

from __future__ import annotations

from pathlib import Path

from agent_console_backend_fake_agent import (
    FAKE_SESSION_MISSING_CODE,
    FakeBackend,
    fake_session_key,
)
from agent_console_backend_fake_agent.testing import ValidatingSink
from agent_console_contracts import Agent, KnownSessionStates
from agent_console_runtime import (
    AgentRequest,
    BackendHostContext,
    CancelToken,
    SecretResolver,
    SessionRef,
    copy_files,
)


def _agent() -> Agent:
    return Agent(
        id="a1",
        name="에이전트",
        backend="fake-agent",
        backend_options={"default": {"response": "ok"}},
    )


def _request(cwd: Path, session: str | None = None) -> AgentRequest:
    ref = SessionRef(backend="fake-agent", session_id=session) if session else None
    return AgentRequest(agent=_agent(), prompt="p", cwd=str(cwd), session=ref)


async def test_default_has_no_session_files_or_archive(tmp_path: Path) -> None:
    backend = FakeBackend(ids=lambda: "s1")
    assert backend.session_archive() is None
    result = await backend.run(_request(tmp_path, "old"), ValidatingSink(), CancelToken())
    assert result.status == "succeeded"  # 지금 동작 그대로(세션 기록 없이 이어 감)


async def test_session_dir_records_and_resume_needs_file(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    cwd = tmp_path / "project"
    backend = FakeBackend(ids=lambda: "s1", session_dir=root)
    first = await backend.run(_request(cwd), ValidatingSink(), CancelToken())
    assert first.status == "succeeded"
    file = root / fake_session_key(str(cwd)) / "s1.jsonl"
    assert file.is_file()
    again = await backend.run(_request(cwd, "s1"), ValidatingSink(), CancelToken())
    assert again.status == "succeeded"
    assert len(file.read_text(encoding="utf-8").splitlines()) == 2
    missing = await backend.run(_request(cwd, "s9"), ValidatingSink(), CancelToken())
    assert missing.status == "failed"
    assert missing.error is not None
    assert missing.error.code == FAKE_SESSION_MISSING_CODE


async def test_other_workspace_continues_from_archive_copy(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    a = FakeBackend(ids=lambda: "s1", session_dir=tmp_path / "a")
    b = FakeBackend(ids=lambda: "zz", session_dir=tmp_path / "b")
    await a.run(_request(cwd), ValidatingSink(), CancelToken())
    ref = SessionRef(backend="fake-agent", session_id="s1")
    archive_a, archive_b = a.session_archive(), b.session_archive()
    assert archive_a is not None
    assert archive_b is not None
    assert archive_b.status(ref, cwd=cwd) == KnownSessionStates.MISSING
    failed = await b.run(_request(cwd, "s1"), ValidatingSink(), CancelToken())
    assert failed.status == "failed"
    saved = tmp_path / "saved"
    copy_files(archive_a.files(ref, cwd=cwd) or [], saved)
    assert archive_b.restore(saved, ref, cwd=cwd) is True
    resumed = await b.run(_request(cwd, "s1"), ValidatingSink(), CancelToken())
    assert resumed.status == "succeeded"
    assert resumed.session is not None
    assert resumed.session.session_id == "s1"


def test_from_options_resolves_relative_session_dir(tmp_path: Path) -> None:
    backend = FakeBackend.from_options(
        {"session_dir": ".state/fake-sessions"},
        secrets=SecretResolver([]),
        environ={},
        host=BackendHostContext(workspace_dir=tmp_path),
    )
    archive = backend.session_archive()
    assert archive is not None
    assert getattr(archive, "root", None) == tmp_path / ".state" / "fake-sessions"
