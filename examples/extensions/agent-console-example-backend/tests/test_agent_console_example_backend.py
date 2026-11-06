"""대본 백엔드 ``example.scripted``: entry point 로딩, 능력 선언, 규칙 고르기, 흘리기·취소, 설치자
설정 훅, 세션 기록·이어 쓰기·보관·복원, 이벤트에 경로·비밀 값이 없음.

설치 없이 실행한다(pytest 설정 ``pythonpath = ["src"]``). entry point는 ``EntryPoint`` 객체를 직접
만들어 로더에 넘긴다(설치했을 때 로더가 찾는 것과 같은 값).
"""

from __future__ import annotations

import json
import tomllib
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts import Agent, ErrorCodes, KnownSessionStates
from agent_console_example_backend import (
    BACKEND_ID,
    SESSION_MISSING_CODE,
    ScriptedBackend,
    ScriptOptions,
    session_key,
)
from agent_console_runtime import (
    BACKENDS_GROUP,
    AgentRequest,
    BackendHostContext,
    CancelToken,
    ConfigurableBackend,
    ExecutionBackend,
    Registries,
    SecretResolver,
    SessionArchiveCapable,
    SessionRef,
    copy_files,
    load_registries,
    session_archive_of,
)
from agent_console_runtime.testing_sink import ValidatingSink

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
VALUE = "agent_console_example_backend:ScriptedBackend"
SECRET = "sekret-value-zz9"
SCRIPT: dict[str, Any] = {
    "rules": [
        {"contains": "안녕", "reply": "반가워요, $agent_name입니다"},
        {"contains": "Status", "reply": "상태: 정상 ($turn번째)", "ignore_case": False},
    ],
    "default_reply": "받음: $prompt",
}


def agent(options: dict[str, Any] | None = None, **extra: Any) -> Agent:
    body = {"id": "bot", "name": "봇", "backend": BACKEND_ID, "backend_options": options or SCRIPT}
    return Agent.model_validate({**body, **extra})


def request(prompt: str, **extra: Any) -> AgentRequest:
    return AgentRequest(agent=agent(), prompt=prompt, **extra)


def ids() -> Any:
    counter = iter(range(1, 1000))
    return lambda: f"s{next(counter)}"


def configured(options: dict[str, Any], workspace: Path | None = None) -> ScriptedBackend:
    host = BackendHostContext(workspace_dir=workspace)
    return ScriptedBackend.from_options(
        options, secrets=SecretResolver([]), environ={"TOKEN": SECRET}, host=host
    )


async def run(backend: ScriptedBackend, req: AgentRequest) -> tuple[Any, ValidatingSink]:
    sink = ValidatingSink()
    result = await backend.run(req, sink, CancelToken())
    return result, sink


# ------------------------------------------------------------------ 등록·능력


def test_entry_point_declared_and_loads() -> None:
    eps = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["entry-points"]
    assert eps[BACKENDS_GROUP] == {BACKEND_ID: VALUE}

    registries = Registries()
    reports = load_registries(
        registries, entry_points=[EntryPoint(name=BACKEND_ID, value=VALUE, group=BACKENDS_GROUP)]
    )
    assert [(r.key, r.status) for r in reports] == [(BACKEND_ID, "loaded")]
    backend = registries.backends.get(BACKEND_ID)
    assert isinstance(backend, ExecutionBackend)
    assert isinstance(backend, ConfigurableBackend)
    assert isinstance(backend, SessionArchiveCapable)
    assert backend.descriptor.id == BACKEND_ID

    removed = Registries()  # 제거 = entry point 없음
    load_registries(removed, entry_points=[])
    assert BACKEND_ID not in removed.backends


def test_capabilities_follow_install_options(tmp_path: Path) -> None:
    plain = ScriptedBackend()
    caps = plain.descriptor.capabilities
    assert (caps.streaming, caps.cancel, caps.resume) == (True, True, False)
    assert (caps.tools, caps.subagents, caps.host_tools, caps.status, caps.probe) == (
        False,
        False,
        False,
        False,
        False,
    )
    assert session_archive_of(plain) is None  # 기록 폴더가 없으면 보관 능력 없음

    recording = configured({"session_dir": str(tmp_path)})
    assert recording.descriptor.capabilities.resume is True
    assert session_archive_of(recording) is not None
    # 에이전트 대본 스키마가 디스크립터 데이터로 나간다(설정 화면이 이것으로 폼을 그린다).
    assert recording.descriptor.config_schema == ScriptOptions.model_json_schema()


async def test_models_are_install_data() -> None:
    backend = configured({"models": [{"id": "script-1", "title": "대본 1"}]})
    assert [m.id for m in await backend.list_models()] == ["script-1"]
    assert await ScriptedBackend().list_models() == []


# ------------------------------------------------------------------ 실행


async def test_first_matching_rule_then_default() -> None:
    backend = ScriptedBackend(ids=ids())
    first, sink = await run(backend, request("안녕하세요"))
    assert (first.status, first.text) == ("succeeded", "반가워요, 봇입니다")
    assert [e.type for e in sink.events] == [
        "agent.session_started",
        "agent.text_delta",
        "agent.message",
        "agent.usage",
    ]
    assert first.session == SessionRef(backend=BACKEND_ID, session_id="s1")

    case, _ = await run(backend, request("status?"))  # ignore_case=False 규칙은 안 맞는다
    assert case.text == "받음: status?"
    exact, _ = await run(backend, request("Status?"))
    assert exact.text == "상태: 정상 (1번째)"


async def test_streams_in_chunks_and_cancels() -> None:
    backend = ScriptedBackend(chunk_chars=2)
    result, sink = await run(backend, request("abcde"))
    deltas = [e.payload["text"] for e in sink.events if e.type == "agent.text_delta"]
    assert "".join(deltas) == result.text == "받음: abcde"
    assert all(len(d) <= 2 for d in deltas)

    cancel = CancelToken()
    cancel.cancel("사용자")
    stopped = await backend.run(request("abcde"), ValidatingSink(), cancel)
    assert (stopped.status, stopped.text) == ("cancelled", "")


async def test_bad_script_is_a_failed_result() -> None:
    req = AgentRequest(agent=agent({"rules": [{"contains": ""}]}), prompt="x")
    result, sink = await run(ScriptedBackend(), req)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == ErrorCodes.VALIDATION_FAILED
    assert sink.events == []


def test_install_options_are_checked_without_values(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="nope") as caught:
        configured({"nope": SECRET})
    assert SECRET not in str(caught.value)
    with pytest.raises(ValueError, match="session_dir"):
        ScriptedBackend.from_options({"session_dir": "rel"}, secrets=SecretResolver([]), environ={})
    backend = configured({"session_dir": "rel"}, workspace=tmp_path)
    archive = session_archive_of(backend)
    assert archive is not None
    assert getattr(archive, "root", None) == tmp_path / "rel"


# ------------------------------------------------------------------ 세션 기록·보관


async def test_session_record_resume_and_missing(tmp_path: Path) -> None:
    work = tmp_path / "work"
    backend = configured({"session_dir": str(tmp_path / "sessions")})
    first, _ = await run(backend, request("Status", cwd=str(work)))
    assert first.text == "상태: 정상 (1번째)"
    assert first.session is not None
    again, _ = await run(backend, request("Status", cwd=str(work), session=first.session))
    assert (again.text, again.session) == ("상태: 정상 (2번째)", first.session)

    record = tmp_path / "sessions" / session_key(str(work)) / f"{first.session.session_id}.jsonl"
    lines = [json.loads(x) for x in record.read_text(encoding="utf-8").splitlines()]
    assert [x["turn"] for x in lines] == [1, 2]

    gone = SessionRef(backend=BACKEND_ID, session_id="nope")
    missing, sink = await run(backend, request("x", cwd=str(work), session=gone))
    assert missing.status == "failed"
    assert missing.error is not None
    assert missing.error.code == SESSION_MISSING_CODE
    assert sink.events == []

    other = SessionRef(backend="other-backend", session_id="x1")  # 다른 백엔드 세션은 새로 시작
    fresh, _ = await run(backend, request("x", cwd=str(work), session=other))
    assert fresh.status == "succeeded"
    assert fresh.session != other


async def test_archive_files_status_and_restore_elsewhere(tmp_path: Path) -> None:
    work = str(tmp_path / "work")
    source = configured({"session_dir": str(tmp_path / "a")})
    done, _ = await run(source, request("Status", cwd=work))
    assert done.session is not None
    archive = session_archive_of(source)
    assert archive is not None
    assert archive.status(done.session, cwd=work) == KnownSessionStates.AVAILABLE
    files = archive.files(done.session, cwd=work)
    assert files is not None
    assert [f.name for f in files] == [f"{done.session.session_id}.jsonl"]

    kept = tmp_path / "kept"  # 앱이 보관 폴더로 복사한다
    copy_files(files, kept)

    target = configured({"session_dir": str(tmp_path / "b")})  # 다른 앱(다른 기록 폴더)
    other = session_archive_of(target)
    assert other is not None
    assert other.status(done.session, cwd=work) == KnownSessionStates.MISSING
    assert other.restore(kept, done.session, cwd=work) is True
    resumed, _ = await run(target, request("Status", cwd=work, session=done.session))
    assert resumed.text == "상태: 정상 (2번째)"


async def test_events_carry_no_paths_or_secrets(tmp_path: Path) -> None:
    work = tmp_path / "work-zz8"
    sessions = tmp_path / "sessions-zz7"
    backend = configured({"session_dir": str(sessions)})
    req = AgentRequest(agent=agent(), prompt="안녕", cwd=str(work), run_folder=str(tmp_path))
    result, sink = await run(backend, req)
    dumped = json.dumps([e.model_dump(mode="json") for e in sink.events], ensure_ascii=False)
    dumped += result.model_dump_json()
    for value in (SECRET, str(tmp_path), "work-zz8", "sessions-zz7"):
        assert value not in dumped
