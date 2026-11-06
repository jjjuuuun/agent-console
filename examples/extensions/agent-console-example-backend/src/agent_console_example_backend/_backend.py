"""`ScriptedBackend`: 모델 없이 규칙 데이터(대본)로 답하는 결정적 실행 백엔드.

- 무엇을 답할지는 에이전트 정의의 `backend_options`(``ScriptOptions``)가 정한다: 규칙
  ``{contains, reply}`` 목록을 위에서부터 보고, 처음 맞는 규칙의 ``reply``를, 없으면
  ``default_reply``를 답한다. 답 문구는 ``$prompt``·``$agent_name``·``$model``·``$turn`` 자리표시를
  채운 글이다.
- 어떻게 동작할지는 설치자 설정 ``modules.options.mod-runs.backends."example.scripted"``
  (``InstallOptions``)가 정하고, 앱이 ``from_options`` 훅으로 넘긴다(앱은 키의 뜻을 모른다).
- ``session_dir``을 주면 실행마다 ``<session_dir>/<작업 폴더 키>/<세션>.jsonl``에 한 줄을 더하고,
  ``session_archive()``로 그 파일의 보관·복원을 준다(선택 능력). 이어 쓰는 요청인데 기록이 없으면
  실패한다.

이벤트에는 세션 id·백엔드 id·모델 id·답 글만 싣는다(작업 폴더·기록 폴더 경로·환경 값은 싣지 않는다).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from string import Template
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_console_contracts import (
    AgentMessagePayload,
    AgentSessionStartedPayload,
    AgentTextDeltaPayload,
    AgentUsagePayload,
    BackendCapabilities,
    BackendDescriptor,
    ErrorCodes,
    ErrorInfo,
    ModelInfo,
    UiHints,
    Usage,
)
from agent_console_runtime import (
    AgentRequest,
    AgentResult,
    BackendEventSink,
    BackendHostContext,
    CancelToken,
    JsonlFolderSessionArchive,
    SecretResolver,
    SessionArchive,
    SessionRef,
    safe_name,
)

BACKEND_ID = "example.scripted"
"""entry point 이름 = 백엔드 id."""

SESSION_MISSING_CODE = "example.session_missing"
"""이어 쓸 세션 기록이 없을 때 실패 코드(예제 고유 코드 — 화면은 원문 그대로 보인다)."""

SESSION_SUFFIX = ".jsonl"


class ScriptRule(BaseModel):
    """규칙 하나: 요청 글에 ``contains``가 들어 있으면 ``reply``로 답한다."""

    model_config = ConfigDict(extra="forbid")

    contains: str = Field(min_length=1, description="요청 글에 들어 있어야 하는 글.")
    reply: str = Field(description="답 문구($prompt·$agent_name·$model·$turn 자리표시).")
    ignore_case: bool = Field(default=True, description="대소문자를 가리지 않는다.")

    def matches(self, prompt: str) -> bool:
        if self.ignore_case:
            return self.contains.casefold() in prompt.casefold()
        return self.contains in prompt


class ScriptOptions(BaseModel):
    """에이전트 정의의 ``backend_options``(이 백엔드의 대본)."""

    model_config = ConfigDict(extra="forbid")

    rules: list[ScriptRule] = Field(default_factory=list, description="위에서부터 보는 규칙.")
    default_reply: str = Field(default="$prompt", description="맞는 규칙이 없을 때 답 문구.")

    def reply_for(self, prompt: str) -> str:
        """처음 맞는 규칙의 답 문구(자리표시를 채우기 전)."""
        return next((r.reply for r in self.rules if r.matches(prompt)), self.default_reply)


class InstallOptions(BaseModel):
    """설치자 설정 ``modules.options.mod-runs.backends."example.scripted"``."""

    model_config = ConfigDict(extra="forbid")

    models: list[ModelInfo] = Field(default_factory=list, description="모델 목록(이름표일 뿐).")
    session_dir: str | None = Field(
        default=None,
        description="세션 기록 폴더. 상대 경로는 앱 workspace 기준. 비우면 기록·보관 없음.",
    )
    chunk_chars: int = Field(
        default=0, ge=0, description="답을 이 글자 수씩 나눠 흘린다. 0이면 한 번에."
    )


def render(template: str, variables: Mapping[str, str]) -> str:
    """``$이름`` 자리표시를 채운다(모르는 이름은 그대로 둔다).

    >>> render("답: $prompt ($turn)", {"prompt": "안녕", "turn": "2"})
    '답: 안녕 (2)'
    """
    return Template(template).safe_substitute(variables)


def session_key(cwd: str) -> str:
    """작업 폴더 → 기록 키 폴더 이름(경로를 그대로 쓰지 않고 해시).

    >>> session_key("/work/a") == session_key("/work/a"), session_key("/w")[:2]
    (True, 'k-')
    """
    digest = hashlib.sha256(os.path.abspath(cwd).encode("utf-8")).hexdigest()
    return "k-" + digest[:24]


def scripted_session_archive(root: Path) -> JsonlFolderSessionArchive:
    """``root`` 아래 대본 세션 기록의 보관·복원(공용 구현에 키 함수만 준다)."""
    return JsonlFolderSessionArchive(root, session_key, suffix=SESSION_SUFFIX)


class ScriptedBackend:
    """규칙 데이터로 답하는 실행 백엔드(모델·네트워크 호출 없음).

    Args:
        models: ``list_models``가 돌려줄 목록.
        session_dir: 세션 기록 폴더(절대 경로). None이면 기록·보관·이어 쓰기 확인 없음.
        chunk_chars: 답을 나눠 흘릴 글자 수(0 = 한 번에).
        ids: 새 세션 id 생성기(테스트 주입용, 기본 uuid4).
    """

    def __init__(
        self,
        *,
        models: Iterable[ModelInfo | Mapping[str, Any]] = (),
        session_dir: Path | None = None,
        chunk_chars: int = 0,
        ids: Callable[[], str] | None = None,
    ) -> None:
        self._models = [ModelInfo.model_validate(m) for m in models]
        self._session_dir = session_dir
        self._chunk_chars = chunk_chars
        self._ids = ids or (lambda: uuid.uuid4().hex)
        self.descriptor = BackendDescriptor(
            id=BACKEND_ID,
            title="대본 백엔드(예제)",
            description="모델을 부르지 않고 에이전트 설정의 규칙대로 답합니다.",
            cost_note="모델을 부르지 않아 사용량이 들지 않습니다.",
            config_schema=ScriptOptions.model_json_schema(),
            ui_hints=UiHints(badge="예제"),
            capabilities=BackendCapabilities(
                streaming=True,
                cancel=True,
                # 이어 쓰기는 세션 기록이 있을 때만 뜻이 있다(설정에 따라 능력 선언이 바뀐다).
                resume=session_dir is not None,
            ),
        )

    @classmethod
    def from_options(
        cls,
        options: Mapping[str, Any],
        *,
        secrets: SecretResolver,
        environ: Mapping[str, str],
        host: BackendHostContext | None = None,
    ) -> ScriptedBackend:
        """설치자 설정으로 만든다(``ConfigurableBackend`` 훅).

        ``secrets``·``environ``은 쓰지 않는다(외부 호출이 없다). ``host.workspace_dir``는 상대
        ``session_dir``의 기준이다.

        Raises:
            ValueError: 모르는 키·잘못된 값(위치와 사유만, 값은 넣지 않는다).
        """
        try:
            parsed = InstallOptions.model_validate(dict(options))
        except ValidationError as exc:
            raise ValueError(f"대본 백엔드 설정 오류: {_problems(exc)}") from None
        session_dir: Path | None = None
        if parsed.session_dir:
            path = Path(parsed.session_dir).expanduser()
            if not path.is_absolute():
                if host is None or host.workspace_dir is None:
                    raise ValueError("session_dir: 상대 경로는 앱 workspace가 있어야 합니다")
                path = host.workspace_dir / path
            session_dir = path
        return cls(models=parsed.models, session_dir=session_dir, chunk_chars=parsed.chunk_chars)

    def session_archive(self) -> SessionArchive | None:
        """선택 능력(세션 기록 보관·복원): ``session_dir``이 있을 때만."""
        if self._session_dir is None:
            return None
        return scripted_session_archive(self._session_dir)

    async def list_models(self) -> list[ModelInfo]:
        return list(self._models)

    async def run(
        self, req: AgentRequest, sink: BackendEventSink, cancel: CancelToken
    ) -> AgentResult:
        """대본을 골라 이벤트를 내고 결과를 돌려준다. 대본 오류는 ``failed`` 결과로 돌려준다."""
        try:
            script = ScriptOptions.model_validate(req.agent.backend_options or {})
        except ValidationError as exc:
            return AgentResult(
                status="failed",
                error=ErrorInfo(
                    code=ErrorCodes.VALIDATION_FAILED,
                    message="대본 백엔드 설정(backend_options)이 올바르지 않습니다",
                    details={"problems": _problems(exc)},
                ),
            )
        resuming = req.session is not None and req.session.backend == BACKEND_ID
        session_id = req.session.session_id if req.session is not None and resuming else self._ids()
        session = SessionRef(backend=BACKEND_ID, session_id=session_id)

        turn = 1
        record = self._record(req.cwd, session_id)
        if record is not None:
            previous = await asyncio.to_thread(_count_lines, record)
            if resuming and previous is None:
                return AgentResult(
                    status="failed",
                    error=ErrorInfo(
                        code=SESSION_MISSING_CODE,
                        message="이어 쓸 세션 기록이 이 앱에 없습니다",
                        details={"session_id": session_id},
                    ),
                )
            turn = (previous or 0) + 1
            line = {"session_id": session_id, "turn": turn, "prompt": req.prompt}
            await asyncio.to_thread(_append_line, record, line)

        await sink.emit(
            "agent.session_started",
            AgentSessionStartedPayload(
                session_id=session_id, backend=BACKEND_ID, model=req.agent.model
            ),
        )
        variables = {
            "prompt": req.prompt,
            "agent_name": req.agent.name,
            "model": req.agent.model or "",
            "turn": str(turn),
        }
        text = render(script.reply_for(req.prompt), variables)
        message_id = f"{session_id}:{turn}"
        size = self._chunk_chars or max(len(text), 1)
        sent = ""
        for start in range(0, len(text), size):
            await asyncio.sleep(0)  # 취소가 끼어들 틈
            if cancel.cancelled:
                return AgentResult(status="cancelled", text=sent, session=session)
            chunk = text[start : start + size]
            await sink.emit(
                "agent.text_delta", AgentTextDeltaPayload(text=chunk, message_id=message_id)
            )
            sent += chunk
        if cancel.cancelled:
            return AgentResult(status="cancelled", text=sent, session=session)
        await sink.emit(
            "agent.message",
            AgentMessagePayload(role="assistant", text=text, message_id=message_id),
        )
        usage = Usage(input_tokens=0, output_tokens=0, cost_usd=0.0)
        await sink.emit("agent.usage", AgentUsagePayload(usage=usage, model=req.agent.model))
        return AgentResult(status="succeeded", text=text, usage=usage, session=session)

    def _record(self, cwd: str | None, session_id: str) -> Path | None:
        """이 세션의 기록 파일(``session_dir``·작업 폴더가 있고 이름이 안전할 때만)."""
        if self._session_dir is None or not cwd or not safe_name(session_id):
            return None
        return self._session_dir / session_key(cwd) / f"{session_id}{SESSION_SUFFIX}"


def _count_lines(path: Path) -> int | None:
    """기록 줄 수(파일이 없으면 None)."""
    try:
        with path.open("rb") as handle:
            return sum(1 for _ in handle)
    except FileNotFoundError:
        return None


def _append_line(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _problems(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or '(root)'}: {e['msg']}"
        for e in exc.errors(include_input=False, include_url=False)
    )


__all__ = [
    "BACKEND_ID",
    "SESSION_MISSING_CODE",
    "SESSION_SUFFIX",
    "InstallOptions",
    "ScriptOptions",
    "ScriptRule",
    "ScriptedBackend",
    "render",
    "scripted_session_archive",
    "session_key",
]
