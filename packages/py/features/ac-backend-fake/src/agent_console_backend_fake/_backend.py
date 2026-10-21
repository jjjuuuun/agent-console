"""`FakeBackend`: 모델 없이 설정 데이터대로 응답하는 결정적 실행 백엔드(X3)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_console_contracts import (
    AgentMessagePayload,
    AgentSessionStartedPayload,
    AgentSettings,
    AgentSubagentPayload,
    AgentTextDeltaPayload,
    AgentToolCallPayload,
    AgentToolResultPayload,
    AgentUsagePayload,
    BackendCapabilities,
    BackendDescriptor,
    BackendProbeResult,
    BackendReadiness,
    ErrorCodes,
    ErrorInfo,
    InteractionGrant,
    Issue,
    KnownResourceSlots,
    ModelInfo,
    ResourceBundle,
    UiHints,
    Usage,
    UsageRateLimitPayload,
)
from agent_console_runtime import (
    AgentRequest,
    AgentResult,
    BackendCheckContext,
    BackendEventSink,
    CancelToken,
    HostTool,
    InteractionRequest,
    InteractivePort,
    SecretResolver,
    SessionRef,
    SubagentResultListener,
    SubagentSpec,
    call_host_tool,
    preview,
)

from ._bundle import bundle_summary, mask_secret_refs
from ._config import (
    DEFAULT_OBSERVE_COLLECTORS,
    HOOK_PROBE_SWITCH,
    FakeBackendOptions,
    FakeDelegation,
    FakeHookProbe,
    FakeHostToolCall,
    FakeRateLimit,
    FakeRule,
    FakeToolCall,
    fake_config_schema,
    fill_template,
)

FAKE_BACKEND_ID = "fake"
"""기본 디스크립터 id(entry point 이름과 같다)."""

DEFAULT_DELEGATE_TOOL = "Agent"
"""기본 위임 도구 이름(claude-sdk가 쓰는 SDK 위임 도구 이름과 맞춘 기본값, 설정으로 바꾼다)."""

DEFAULT_RESOURCE_SLOTS: tuple[str, ...] = (
    KnownResourceSlots.INSTRUCTIONS,
    KnownResourceSlots.FILES,
    KnownResourceSlots.MCP_SERVERS,
    KnownResourceSlots.TOOLS,
    KnownResourceSlots.SKILLS,
    KnownResourceSlots.HOOKS,
    KnownResourceSlots.RULES,
)
"""기본으로 받는 실행 묶음 칸(알려진 칸 전부). fake는 요약만 하므로 어떤 칸도 받을 수 있다."""

DEFAULT_HOOK_PROBE_FOLDER = "hook-probe"
"""실행 폴더 아래 hook probe 기록 흉내 폴더 이름(claude-sdk와 같은 기본값, 설치자 설정)."""

HOOK_PROBE_NOTE_CODE = "observe.hook_probe_wrapped"
"""묶음 미리보기 "hook 감싸기 켜짐" 안내 코드(claude-sdk와 같은 코드를 흉내 낸다)."""

FAKE_READY_STATE = "always_ready"
"""fake 정적 점검 상태 이름(인증이 필요 없어 늘 준비됨, ux-overhaul §15.8)."""

COMPLETED_STATUS = "completed"
STOPPED_STATUS = "stopped"

UNKNOWN_HOST_TOOL_TEXT = "알 수 없는 도구: {tool}"
"""`host_tool_calls`의 도구가 요청(`AgentRequest.host_tools`)에 없을 때 오류 결과 문장."""


class HostCallStatus:
    """`$host_N_status` 값."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


def _default_ids() -> str:
    return uuid.uuid4().hex


class FakeInstallOptions(BaseModel):
    """설치자 설정(앱 설정 `backends.fake`) 형식. `FakeBackend.from_options`가 읽는다."""

    model_config = ConfigDict(extra="forbid")

    models: list[ModelInfo] = Field(default_factory=list, description="`list_models()` 목록.")
    rate_limits: list[FakeRateLimit] = Field(
        default_factory=list,
        description="실행마다 `agent.session_started` 직후 낼 `usage.rate_limit` 이벤트.",
    )
    resource_slots: list[str] | None = Field(
        default=None, description="`capabilities.resource_slots`. 없으면 알려진 칸 전부."
    )
    delegate_tool: str = Field(
        default=DEFAULT_DELEGATE_TOOL, min_length=1, description="위임 도구 호출 이벤트의 이름."
    )
    echo_hooks: bool = Field(
        default=False,
        description="실행 묶음 hooks 칸 항목마다 hook.started·hook.finished 이벤트를 흉내 낸다"
        "(명령은 실행하지 않는다, observe 규칙 없이도). 기본 꺼짐.",
    )
    observe_collectors: dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_OBSERVE_COLLECTORS),
        description="옛 관측 키 → 수집기 id(observe.collectors가 옛 키를 이긴다).",
    )
    hook_probe_folder: str = Field(
        default=DEFAULT_HOOK_PROBE_FOLDER,
        pattern=r"^[A-Za-z0-9_-][A-Za-z0-9._-]*$",
        description="실행 폴더 아래 hook probe 기록 흉내 폴더 이름.",
    )


@dataclass(frozen=True, slots=True)
class _Run:
    """한 실행의 공통 문맥."""

    sink: BackendEventSink
    cancel: CancelToken
    session_id: str
    variables: dict[str, str]
    subagents: dict[str, SubagentSpec]
    observe: Mapping[str, Any]
    collectors: Mapping[str, str] = field(default_factory=dict)
    probe: _ProbeWriter | None = None


class FakeBackend:
    """설정(`Agent.backend_options`, 형식 `FakeBackendOptions`)대로 응답하는 백엔드.

    같은 요청에는 같은 이벤트 순서와 결과를 낸다(세션 id는 `ids`, 시각은 `clock`으로 주입).
    방출 순서: `agent.session_started` → `usage.rate_limit`* → 관측(start)* → (`agent.tool_call` →
    `agent.tool_result`)* → 관측(tool)* → 위임* → 플랫폼 도구 호출* → `agent.text_delta`* →
    `agent.message` →
    관측(end)* → `agent.usage`. 관측(`hook.*`·`mcp.*` 등, 규칙 `observe`)은 요청의 관측 설정
    (`AgentRequest.observe`)에서 그 스위치가 켜졌을 때만 낸다.

    위임 하나(규칙 `delegate`): `agent.tool_call`(위임 도구) → `agent.subagent_started` →
    (`agent.tool_call` → `agent.tool_result`)* → `agent.message` → `agent.subagent_stopped` →
    `agent.tool_result`(위임 도구). 시작~종료 이벤트는 `actor=대상 actor`,
    `node_path=sink.child_path(대상)`(sink가 `child_path`를 가질 때, 없으면 위임자 경로)로 낸다.
    서브에이전트는 텍스트 델타를 내지 않는다(SDK와 같다). 위임 중 취소면 `agent.subagent_stopped
    {status: stopped}`(사용량·결과 없음)만 내고 위임 도구 결과는 내지 않는다(claude-sdk와 같다).

    Args:
        models: `list_models()`가 돌려줄 모델 목록(설정 데이터). 기본은 빈 목록.
        ids: 세션 id 생성기(테스트에서 고정).
        backend_id: 디스크립터 id(여러 개를 다른 이름으로 등록할 때).
        rate_limits: 실행마다 낼 `usage.rate_limit` 흉내(설정 데이터).
        resource_slots: 받는 실행 묶음 칸. 없으면 `DEFAULT_RESOURCE_SLOTS`.
        delegate_tool: 위임 도구 이름.
        clock: 현재 시각(초). `resets_in_seconds`와 위임 소요 시간 측정에 쓴다.
        echo_hooks: 참이면 묶음 `hooks` 칸 항목마다 `hook.started`·`hook.finished`를 흉내 낸다
            (명령은 실행하지 않는다, `simulated: true`). `observe.hook_probe`도 켜져 있으면 항목마다
            hook probe 기록 한 줄도 남긴다.
        observe_collectors: 옛 관측 키 → 수집기 id(`DEFAULT_OBSERVE_COLLECTORS`). 관측 규칙의
            스위치는 `observe.collectors[id].enabled`가 옛 키를 이긴다.
        hook_probe_folder: `observe.hook_probe` 기록 흉내 폴더(`run_folder` 아래).
    """

    def __init__(
        self,
        *,
        models: Iterable[ModelInfo | Mapping[str, Any]] = (),
        ids: Callable[[], str] = _default_ids,
        backend_id: str = FAKE_BACKEND_ID,
        rate_limits: Iterable[FakeRateLimit | Mapping[str, Any]] = (),
        resource_slots: Iterable[str] | None = None,
        delegate_tool: str = DEFAULT_DELEGATE_TOOL,
        clock: Callable[[], float] = time.time,
        echo_hooks: bool = False,
        observe_collectors: Mapping[str, str] | None = None,
        hook_probe_folder: str = DEFAULT_HOOK_PROBE_FOLDER,
    ) -> None:
        self._echo_hooks = echo_hooks
        self._collectors = dict(
            DEFAULT_OBSERVE_COLLECTORS if observe_collectors is None else observe_collectors
        )
        self._probe_folder = hook_probe_folder
        self._models = [ModelInfo.model_validate(m) for m in models]
        self._ids = ids
        self._rate_limits = [FakeRateLimit.model_validate(r) for r in rate_limits]
        self._delegate_tool = delegate_tool
        self._clock = clock
        slots = list(DEFAULT_RESOURCE_SLOTS if resource_slots is None else resource_slots)
        self.descriptor = BackendDescriptor(
            id=backend_id,
            title="Fake (결정적 응답)",
            description=(
                "체험용: 모델을 부르지 않고 설정한 규칙대로 응답합니다(테스트·데모·오프라인)."
            ),
            cost_note="모델을 부르지 않아 사용량이 들지 않습니다.",
            probe_cost_note="모델을 부르지 않아 비용이 들지 않습니다.",
            ui_hints=UiHints(badge="체험"),
            config_schema=fake_config_schema(),
            capabilities=BackendCapabilities(
                streaming=True,
                tools=True,
                resume=True,
                cancel=True,
                subagents=True,
                host_tools=True,
                resource_slots=slots,
                interactions=None,
                status=True,
                probe=True,
            ),
        )

    @classmethod
    def from_options(
        cls,
        options: Mapping[str, Any],
        *,
        secrets: SecretResolver,
        environ: Mapping[str, str],
    ) -> FakeBackend:
        """`ConfigurableBackend` 훅: 설치자 설정(`FakeInstallOptions`)으로 만든다.

        `secrets`·`environ`은 쓰지 않는다(외부 호출이 없다).

        Raises:
            ValueError: 모르는 키·잘못된 값(위치와 사유만, 값은 넣지 않는다).
        """
        try:
            parsed = FakeInstallOptions.model_validate(dict(options))
        except ValidationError as exc:
            raise ValueError(f"fake 백엔드 설정 오류: {_problems(exc)}") from None
        return cls(
            models=parsed.models,
            rate_limits=parsed.rate_limits,
            resource_slots=parsed.resource_slots,
            delegate_tool=parsed.delegate_tool,
            echo_hooks=parsed.echo_hooks,
            observe_collectors=parsed.observe_collectors,
            hook_probe_folder=parsed.hook_probe_folder,
        )

    def preview_notes(self, effective: AgentSettings, bundle: ResourceBundle) -> list[Issue]:
        """선택 훅(`ac-teams.PreviewNotes`): `observe.hook_probe`가 참이면 claude-sdk처럼 info
        "hook 감싸기 켜짐"을 낸다(fake는 감싸지 않고 기록만 흉내 낸다, `details.simulated`)."""
        observe = effective.observe
        if observe is None or observe.hook_probe is not True:
            return []
        items = bundle.slots.get(KnownResourceSlots.HOOKS)
        count = len(items) if isinstance(items, list) else 0
        return [
            Issue(
                severity="info",
                code=HOOK_PROBE_NOTE_CODE,
                message=f"hook 감싸기 켜짐(흉내): hook {count}개의 probe 기록을 흉내 냅니다",
                details={"hooks": count, "option": "observe.hook_probe", "simulated": True},
            )
        ]

    async def list_models(self) -> list[ModelInfo]:
        """생성 시 받은 모델 목록(복사본)."""
        return list(self._models)

    async def status(self, ctx: BackendCheckContext) -> BackendReadiness:
        """선택 능력(정적 점검): 인증이 필요 없어 늘 준비됨(``always_ready``, 톤 ok)."""
        return BackendReadiness(
            backend_id=ctx.backend_id,
            state=FAKE_READY_STATE,
            tone="ok",
            summary="준비됨 (인증 필요 없음)",
            short_summary="준비됨",
            checked_at=ctx.clock(),
        )

    async def probe(self, ctx: BackendCheckContext, timeout_s: float) -> BackendProbeResult:
        """선택 능력(연결 테스트): 지연 없이 성공한다(네트워크·키 없음)."""
        return BackendProbeResult(
            backend_id=ctx.backend_id,
            ok=True,
            latency_ms=0,
            message="연결됨 (모델을 부르지 않음)",
            details={"models": len(self._models)},
            finished_at=ctx.clock(),
        )

    async def run(
        self, req: AgentRequest, sink: BackendEventSink, cancel: CancelToken
    ) -> AgentResult:
        """규칙을 골라 이벤트를 내고 결과를 돌려준다. 설정 오류는 `failed` 결과로 돌려준다."""
        try:
            options = FakeBackendOptions.model_validate(req.agent.backend_options or {})
        except ValidationError as exc:
            return AgentResult(
                status="failed",
                error=ErrorInfo(
                    code=ErrorCodes.VALIDATION_FAILED,
                    message="fake 백엔드 설정(backend_options)이 올바르지 않습니다",
                    details={
                        "errors": exc.errors(
                            include_url=False, include_context=False, include_input=False
                        )
                    },
                ),
            )
        backend_id = self.descriptor.id
        session_id = (
            req.session.session_id
            if req.session is not None and req.session.backend == backend_id
            else self._ids()
        )
        session = SessionRef(backend=backend_id, session_id=session_id)
        rule = options.pick(req.prompt)
        message_id = f"{session_id}:msg"
        bundle = bundle_summary(req.bundle, self.descriptor.capabilities.resource_slots)
        variables = {
            "prompt": req.prompt,
            "agent_id": req.agent.id,
            "agent_name": req.agent.name,
            "model": req.agent.model or "",
            "session_id": session_id,
            "bundle": bundle,
            "cwd": req.cwd or "",
        }
        run = _Run(
            sink=sink,
            cancel=cancel,
            session_id=session_id,
            variables=variables,
            subagents={s.name: s for s in req.subagents},
            observe=req.observe,
            collectors=self._collectors,
            probe=self._probe_writer(req, session_id),
        )
        await sink.emit(
            "agent.session_started",
            AgentSessionStartedPayload(
                session_id=session_id, backend=backend_id, model=req.agent.model
            ),
        )
        for limit in self._rate_limits:
            await sink.emit("usage.rate_limit", self._rate_limit_payload(limit))
        if run.probe is None and req.observe.get(HOOK_PROBE_SWITCH) is True:
            await sink.emit(
                "log.warning",
                {
                    "message": "실행 폴더가 없어 hook probe 기록을 흉내 내지 않습니다",
                    "details": {"option": "observe.hook_probe"},
                },
            )
        if self._echo_hooks:
            await _echo_hooks(sink, req, self.descriptor.capabilities.resource_slots, run.probe)
        await _observe(run, rule, "start")
        if not await _tool_calls(run, rule.tool_calls, f"{session_id}:tool"):
            return _cancelled(session)
        await _observe(run, rule, "tool")
        for index, delegation in enumerate(rule.delegate, start=1):
            result = await self._delegate(run, index, delegation)
            if result is None:
                return _cancelled(session)
            variables[f"delegate_{index}"] = result
        appended = await _host_tool_calls(run, rule.host_tool_calls, req.host_tools)
        if appended is None:
            return _cancelled(session)
        for index, ask in enumerate(rule.ask, start=1):
            answer, status = await _ask(sink, req.interactions, ask, variables)
            variables[f"answer_{index}"] = answer
            variables[f"answer_{index}_status"] = status
            if cancel.cancelled:
                return _cancelled(session)

        text = rule.render(variables)
        if appended:
            text = "\n\n".join([text, *appended]) if text else "\n\n".join(appended)
        if options.echo_bundle:
            text = f"{text}\n\n{bundle}" if text else bundle
        delay = (rule.delay_ms if rule.delay_ms is not None else options.delay_ms) / 1000
        size = rule.chunk_chars or options.chunk_chars
        chunks = [text[i : i + size] for i in range(0, len(text), size)]
        sent: list[str] = []
        for chunk in chunks:
            if rule.fail is not None and len(sent) >= rule.fail.after_chunks:
                break
            if await _pause(delay, cancel):
                return _cancelled(session, "".join(sent))
            await sink.emit(
                "agent.text_delta", AgentTextDeltaPayload(text=chunk, message_id=message_id)
            )
            sent.append(chunk)
        if cancel.cancelled:
            return _cancelled(session, "".join(sent))

        usage = _usage(rule, req.prompt, "".join(sent))
        if rule.fail is not None:
            await _observe(run, rule, "end")
            await sink.emit("agent.usage", AgentUsagePayload(usage=usage, model=req.agent.model))
            return AgentResult(
                status="failed",
                text="".join(sent),
                usage=usage,
                session=session,
                error=ErrorInfo(code=rule.fail.code, message=rule.fail.message),
            )
        await sink.emit(
            "agent.message",
            AgentMessagePayload(
                role="assistant", text=text, message_id=message_id, structured=rule.structured
            ),
        )
        await _observe(run, rule, "end")
        await sink.emit("agent.usage", AgentUsagePayload(usage=usage, model=req.agent.model))
        return AgentResult(
            status="succeeded",
            text=text,
            structured=rule.structured,
            usage=usage,
            session=session,
        )

    def _probe_writer(self, req: AgentRequest, session_id: str) -> _ProbeWriter | None:
        if not req.run_folder or req.observe.get(HOOK_PROBE_SWITCH) is not True:
            return None
        return _ProbeWriter(
            folder=Path(req.run_folder) / self._probe_folder,
            session_id=session_id,
            context=dict(req.run_context),
            cwd=req.cwd,
            clock=self._clock,
        )

    def _rate_limit_payload(self, limit: FakeRateLimit) -> UsageRateLimitPayload:
        resets_at = limit.resets_at
        if limit.resets_in_seconds is not None:
            resets_at = self._clock() + limit.resets_in_seconds
        return UsageRateLimitPayload(
            window=limit.window,
            status=limit.status,
            utilization=limit.utilization,
            resets_at=resets_at,
            overage_status=limit.overage_status,
        )

    async def _delegate(self, run: _Run, index: int, item: FakeDelegation) -> str | None:
        """위임 하나를 흉내 낸다. 서브에이전트 결과 텍스트(대상이 없으면 "")를 돌려주고,
        취소되면 None."""
        if run.cancel.cancelled:
            return None
        sink = run.sink
        spec = run.subagents.get(item.to)
        task = item.render_prompt(run.variables)
        tool_use_id = f"{run.session_id}:delegate{index}"
        description = item.description if item.description is not None else ""
        if spec is not None and item.description is None:
            description = spec.description
        await sink.emit(
            "agent.tool_call",
            AgentToolCallPayload(
                tool_use_id=tool_use_id,
                name=self._delegate_tool,
                input={"subagent_type": item.to, "description": description, "prompt": task},
            ),
        )
        if spec is None:
            await sink.emit(
                "agent.tool_result",
                AgentToolResultPayload(
                    tool_use_id=tool_use_id,
                    is_error=True,
                    output_preview=f"알 수 없는 서브에이전트: {item.to}",
                ),
            )
            return ""

        started = self._clock()
        subagent_id = f"{run.session_id}:task{index}"
        actor = spec.actor
        path = _child_path(sink, spec.name)
        await sink.emit(
            "agent.subagent_started",
            AgentSubagentPayload(
                subagent_id=subagent_id,
                name=spec.name,
                tool_use_id=tool_use_id,
                task_preview=preview(task),
            ),
            actor=actor,
            node_path=path,
        )
        completed = await _tool_calls(
            run, item.tool_calls, f"{subagent_id}:tool", actor=actor, node_path=path
        )
        if not completed or await _pause(item.delay_ms / 1000, run.cancel):
            # claude-sdk와 같게(1R.10 QA): 취소로 닫는 위임은 상태만 싣고 사용량·결과를 꾸미지
            # 않으며, 위임 도구 결과(`agent.tool_result`)와 결과 알림도 내지 않는다.
            await sink.emit(
                "agent.subagent_stopped",
                AgentSubagentPayload(
                    subagent_id=subagent_id,
                    name=spec.name,
                    tool_use_id=tool_use_id,
                    status=STOPPED_STATUS,
                ),
                actor=actor,
                node_path=path,
            )
            return None
        text = item.render_response(
            {
                "prompt": task,
                "agent_id": actor or "",
                "agent_name": spec.name,
                "model": spec.model or "",
                "session_id": run.session_id,
                "bundle": bundle_summary(spec.bundle, self.descriptor.capabilities.resource_slots),
            }
        )
        await sink.emit(
            "agent.message",
            AgentMessagePayload(role="assistant", text=text, message_id=f"{subagent_id}:msg"),
            actor=actor,
            node_path=path,
        )
        status = item.status
        usage = item.usage
        tool_uses = len(item.tool_calls)
        duration_ms = max(int((self._clock() - started) * 1000), 0)
        total_tokens = len(task.split()) + len(text.split())
        if usage is not None:
            total_tokens = usage.total_tokens if usage.total_tokens is not None else total_tokens
            tool_uses = usage.tool_uses if usage.tool_uses is not None else tool_uses
            duration_ms = usage.duration_ms if usage.duration_ms is not None else duration_ms
        await sink.emit(
            "agent.subagent_stopped",
            AgentSubagentPayload(
                subagent_id=subagent_id,
                name=spec.name,
                tool_use_id=tool_use_id,
                status=status,
                usage=Usage(total_tokens=total_tokens),
                tool_uses=tool_uses,
                duration_ms=duration_ms,
                result_preview=preview(text),
            ),
            actor=actor,
            node_path=path,
        )
        await sink.emit(
            "agent.tool_result",
            AgentToolResultPayload(
                tool_use_id=tool_use_id,
                is_error=status != COMPLETED_STATUS,
                output_preview=preview(text) or "",
            ),
        )
        await _notify_result(sink, spec.name, text, status, actor, tool_use_id)
        return text


async def _host_tool_calls(
    run: _Run, calls: Sequence[FakeHostToolCall], tools: Sequence[HostTool]
) -> list[str] | None:
    """규칙의 플랫폼 도구 호출을 순서대로 한다(결정적, 하나씩).

    호출마다 `agent.tool_call` → (핸들러) → `agent.tool_result`를 내고 `$host_N`·`$host_N_status`를
    채운다. 응답 끝에 붙일 텍스트 목록을 돌려주고, 취소되면 None.
    """
    by_name = {t.name: t for t in tools}
    results: list[tuple[str, bool] | None] = []
    appended: list[str] = []
    for index, call in enumerate(calls, start=1):
        if run.cancel.cancelled:
            return None
        if call.when is not None:
            seen = call.when.after if call.when.after is not None else index - 1
            previous = results[seen - 1] if 1 <= seen < index else None
            if previous is None or not call.when.matches(*previous):
                results.append(None)
                run.variables[f"host_{index}"] = ""
                run.variables[f"host_{index}_status"] = HostCallStatus.SKIPPED
                continue
        tool_use_id = f"{run.session_id}:host{index}"
        arguments = fill_template(call.input, run.variables)
        await run.sink.emit(
            "agent.tool_call",
            AgentToolCallPayload(tool_use_id=tool_use_id, name=call.tool, input=arguments),
        )
        tool = by_name.get(call.tool)
        if tool is None:
            text, is_error = UNKNOWN_HOST_TOOL_TEXT.format(tool=call.tool), True
        else:
            outcome = await call_host_tool(
                tool, arguments if isinstance(arguments, dict) else {}, cancel=run.cancel
            )
            text, is_error = outcome.text, outcome.is_error
        if _is_cancelled(run.cancel):  # 핸들러를 기다리는 사이 취소됐을 수 있다
            run.variables[f"host_{index}_status"] = HostCallStatus.CANCELLED
            return None
        await run.sink.emit(
            "agent.tool_result",
            AgentToolResultPayload(
                tool_use_id=tool_use_id, is_error=is_error, output_preview=preview(text) or ""
            ),
        )
        results.append((text, is_error))
        run.variables[f"host_{index}"] = text
        run.variables[f"host_{index}_status"] = (
            HostCallStatus.FAILED if is_error else HostCallStatus.SUCCEEDED
        )
        if call.append and text:
            appended.append(text)
    return appended


def _is_cancelled(cancel: CancelToken) -> bool:
    """지금 취소됐는가(await 뒤 다시 읽기 — 타입 좁히기를 피한다)."""
    return cancel.cancelled


async def _echo_hooks(
    sink: BackendEventSink,
    req: AgentRequest,
    accepted: Sequence[str],
    probe: _ProbeWriter | None = None,
) -> None:
    """묶음 `hooks` 칸 항목마다 hook 실행 이벤트 흉내(claude-sdk callback 경로와 같은 모양).

    항목 필드(`event`·`matcher`·`command`)는 문자열 그대로 옮긴다(이벤트 이름 목록 없음). 명령은
    실행하지 않고 미리보기에서 `secret://` 참조를 가린다. `probe`가 있으면(hook probe 켜짐)
    항목마다 기록 한 줄도 남긴다.
    """
    slot = KnownResourceSlots.HOOKS
    if req.bundle is None or slot not in accepted:
        return
    items = req.bundle.slots.get(slot)
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, Mapping):
            continue
        command = item.get("command")
        base = {
            "event": item.get("event"),
            "matcher": item.get("matcher"),
            "command_preview": mask_secret_refs(command)[:200]
            if isinstance(command, str)
            else None,
            "hook_type": "command",
            "name": item.get("name"),
            "simulated": True,
        }
        if probe is not None:
            base["hook_probe"] = True
        await sink.emit("hook.started", base)
        await sink.emit(
            "hook.finished", {**base, "exit_code": 0, "duration_ms": 0, "decision": None}
        )
        event = item.get("event")
        if probe is not None and isinstance(event, str) and event:
            matcher = item.get("matcher")
            await probe.write(
                FakeHookProbe(event=event, matcher=matcher if isinstance(matcher, str) else None),
                {},
                sink,
            )


async def _observe(run: _Run, rule: FakeRule, point: str) -> None:
    """`point` 자리의 관측 이벤트 흉내를 낸다(요청의 관측 설정에서 스위치가 켜진 것만)와
    hook probe 기록 흉내(`observe.hook_probe`가 켜졌고 실행 폴더가 있을 때)."""
    for item in rule.observe:
        if item.after == point and item.enabled(run.observe, run.collectors):
            await run.sink.emit(item.type, item.render(run.variables))
    if run.probe is not None:
        for record in rule.hook_probe:
            if record.after == point:
                await run.probe.write(record, run.variables, run.sink)


_SAFE_NAME = re.compile(r"[A-Za-z0-9._-]{1,96}")


def _record_file(session_id: str) -> str:
    """세션마다 한 파일(실제 probe 규칙과 같은 모양: 안전하지 않은 이름은 해시)."""
    if _SAFE_NAME.fullmatch(session_id) and not session_id.startswith("."):
        return session_id + ".jsonl"
    return "s-" + hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32] + ".jsonl"


def _append(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)


@dataclass
class _ProbeWriter:
    """hook probe 기록 흉내를 실행 폴더에 덧붙인다(쓰기 실패는 경고, 실행에 영향 없음)."""

    folder: Path
    session_id: str
    context: dict[str, str]
    cwd: str | None
    clock: Callable[[], float]
    count: int = 0

    async def write(
        self, item: FakeHookProbe, variables: Mapping[str, str], sink: BackendEventSink
    ) -> None:
        self.count += 1
        row = item.record(
            variables,
            probe_id=f"{self.session_id}:probe{self.count}",
            session_id=self.session_id,
            context={k: v for k, v in self.context.items() if v},
            cwd=self.cwd,
            started_at=self.clock(),
        )
        line = json.dumps(row, ensure_ascii=False, default=str) + "\n"
        try:
            await asyncio.to_thread(_append, self.folder / _record_file(self.session_id), line)
        except OSError as exc:
            await sink.emit(
                "log.warning",
                {
                    "message": "hook probe 기록 흉내를 쓰지 못했습니다",
                    "details": {"error": type(exc).__name__, "errno": exc.errno or 0},
                },
            )


UNAVAILABLE_STATUS = "unavailable"
"""`ask`를 열 수 없을 때(sink가 상호작용을 못 열거나 허용에 없는 종류) `$answer_N` 값."""


async def _ask(
    sink: Any,
    grant: InteractionGrant | None,
    item: Any,
    variables: dict[str, str],
) -> tuple[str, str]:
    """상호작용 하나를 열고 `(답 텍스트, 상태)`를 돌려준다."""
    if not isinstance(sink, InteractivePort) or grant is None or item.kind not in grant.kinds:
        await sink.emit(
            "log.warning",
            {
                "message": "허용되지 않은 상호작용이라 열지 않았습니다",
                "details": {"kind": item.kind},
            },
        )
        return UNAVAILABLE_STATUS, UNAVAILABLE_STATUS
    outcome = await sink.request_input(InteractionRequest.model_validate(item.render(variables)))
    if outcome.status != "answered":
        return outcome.status, outcome.status
    return _answer_text(outcome.response, item.answer_path), outcome.status


def _answer_text(response: Any, pointer: str | None) -> str:
    value = response
    if pointer:
        for raw in pointer.split("/")[1:]:
            key = raw.replace("~1", "/").replace("~0", "~")
            if isinstance(value, dict) and key in value:
                value = value[key]
            elif isinstance(value, list) and key.isdigit() and int(key) < len(value):
                value = value[int(key)]
            else:
                return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


async def _notify_result(
    sink: Any, name: str, text: str, status: str, actor: str | None, tool_use_id: str
) -> None:
    """sink가 선택 능력 `SubagentResultListener`(ac-runtime)를 만족하면 위임 결과를 알린다.

    위임 방식(nodes-core `sdk-subagents`)이 이것으로 대상의 답변을 낸다. 실패는 경고 이벤트로.
    """
    emitter: Any = sink
    if not isinstance(sink, SubagentResultListener):
        return
    try:
        await sink.on_subagent_result(
            name,
            text=text,
            status="succeeded" if status == COMPLETED_STATUS else "failed",
            actor=actor,
            tool_use_id=tool_use_id,
        )
    except Exception as exc:
        await emitter.emit(
            "log.warning",
            {
                "message": "서브에이전트 결과를 전달하지 못했습니다",
                "details": {"subagent": name, "error": type(exc).__name__},
            },
        )


async def _tool_calls(
    run: _Run,
    calls: Sequence[FakeToolCall],
    id_prefix: str,
    *,
    actor: str | None = None,
    node_path: Sequence[str] | None = None,
) -> bool:
    """도구 호출·결과 쌍을 낸다. 취소되면 False."""
    for index, call in enumerate(calls):
        if run.cancel.cancelled:
            return False
        tool_use_id = f"{id_prefix}{index}"
        await run.sink.emit(
            "agent.tool_call",
            AgentToolCallPayload(tool_use_id=tool_use_id, name=call.name, input=call.input),
            actor=actor,
            node_path=node_path,
        )
        await run.sink.emit(
            "agent.tool_result",
            AgentToolResultPayload(
                tool_use_id=tool_use_id,
                is_error=call.is_error,
                output_preview=preview(call.output) or "",
            ),
            actor=actor,
            node_path=node_path,
        )
    return True


def _child_path(sink: BackendEventSink, name: str) -> list[str]:
    """위임 대상 이벤트의 `node_path` = `sink.child_path(대상)`(`BackendEventSink` 프로토콜)."""
    return [str(p) for p in sink.child_path(name)]


async def _pause(seconds: float, cancel: CancelToken) -> bool:
    """`seconds`만큼 기다린다. 그 사이 취소되면 True."""
    if cancel.cancelled:
        return True
    if seconds <= 0:
        return False
    try:
        await asyncio.wait_for(cancel.wait(), seconds)
    except TimeoutError:
        return False
    return True


def _usage(rule: FakeRule, prompt: str, text: str) -> Usage:
    if rule.usage is not None:
        return Usage.model_validate(rule.usage)
    return Usage(input_tokens=len(prompt.split()), output_tokens=len(text.split()))


def _cancelled(session: SessionRef, text: str = "") -> AgentResult:
    return AgentResult(status="cancelled", text=text, session=session)


def _problems(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or '(root)'}: {e['msg']}"
        for e in exc.errors(include_input=False, include_url=False)
    )
