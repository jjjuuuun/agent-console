"""fake 백엔드 설정(`Agent.backend_options`) 스키마.

응답 규칙은 모두 데이터다: 프롬프트 조건 → 응답 템플릿·도구 호출·지연·실패.
특정 에이전트 이름이나 프롬프트를 코드에 두지 않는다.
"""

from __future__ import annotations

from collections.abc import Mapping
from string import Template
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_console_contracts import x_ui


class FakeToolCall(BaseModel):
    """응답 중에 도구를 쓴 것처럼 보여 줄 호출 하나입니다. 도구 기록 화면을 확인할 때 씁니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # 흉내 낼 도구 호출 하나(`agent.tool_call` → `agent.tool_result`).

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        title="도구 이름",
        description="흉내 낼 도구 호출의 도구 이름입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="다른 도구 호출을 흉내 내고 싶을 때 바꾸세요.", example="Read"
        ),
    )
    input: Any = Field(
        default=None,
        title="도구 입력",
        description="기록에 실릴 도구 입력입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    output: Any = Field(
        default="",
        title="도구 결과",
        description="기록에 실릴 도구 결과입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    is_error: bool = Field(
        default=False,
        title="오류로 표시",
        description="켜면 이 도구 호출을 실패로 기록합니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class FakeFailure(BaseModel):
    """정한 만큼 답을 낸 뒤 실행을 실패시킵니다. 실패 처리·재시도를 시험할 때 씁니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # 실패 지정. `after_chunks`개 델타를 낸 뒤 실패한다.

    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        default="fake_failure",
        min_length=1,
        title="오류 코드",
        description="실패로 끝낼 때 쓸 오류 코드입니다.",
        json_schema_extra=x_ui(tier="basic", when="다른 오류 상황을 확인하고 싶을 때 바꾸세요."),
    )
    message: str = Field(
        default="fake 백엔드가 설정에 따라 실패했습니다",
        title="오류 문구",
        description="실패로 끝낼 때 보일 문구입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="오류 문구가 화면에 어떻게 보이는지 확인할 때 바꾸세요."
        ),
    )
    after_chunks: int = Field(
        default=0,
        ge=0,
        title="실패 전 조각 수",
        description="글 조각을 이만큼 낸 뒤 실패합니다.",
        json_schema_extra=x_ui(tier="advanced", unit="개"),
    )


class FakeTaskUsage(BaseModel):
    """서브에이전트가 쓴 것처럼 보고할 사용량(토큰·도구 사용 수·소요 시간)입니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # 서브에이전트 사용량(SDK `TaskUsage` 모양: 총 토큰·도구 사용 수·소요 시간만).

    model_config = ConfigDict(extra="forbid")

    total_tokens: int | None = Field(
        default=None,
        ge=0,
        title="총 토큰",
        description="보고할 서브에이전트 총 토큰 수입니다.",
        json_schema_extra=x_ui(tier="advanced", example=1200, unit="개"),
    )
    tool_uses: int | None = Field(
        default=None,
        ge=0,
        title="도구 사용 수",
        description="보고할 도구 사용 횟수입니다.",
        json_schema_extra=x_ui(tier="advanced", example=3, unit="회"),
    )
    duration_ms: int | None = Field(
        default=None,
        ge=0,
        title="소요 시간",
        description="보고할 소요 시간입니다.",
        json_schema_extra=x_ui(tier="advanced", example=1500, unit="ms"),
    )


class FakeDelegation(BaseModel):
    """다른 에이전트에게 일을 맡긴 것처럼 흉내 낼 위임 하나입니다. 위임 흐름을 시험할 때 씁니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # `delegate` 항목 하나: 위임 도구 호출 → 서브에이전트 실행 흉내.
    #
    # `to`는 요청의 `AgentRequest.subagents[].name`(위임 대상 노드 id)이다. 요청에 없는 이름이면
    # SDK처럼 위임 도구 결과가 오류(`is_error`)가 되고 서브에이전트 이벤트는 나지 않는다.
    #
    # 템플릿 변수 — `prompt`: 위임자 변수 그대로. `response`: `$prompt`(= 과제), `$agent_id`
    # (대상 actor), `$agent_name`(대상 이름), `$model`, `$session_id`, `$bundle`(대상 묶음 요약).

    model_config = ConfigDict(extra="forbid")

    to: str = Field(
        min_length=1,
        title="대상",
        description="일을 맡길 서브에이전트 이름(대상 노드 id)입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="다른 에이전트에게 맡기는 상황을 확인하고 싶을 때 바꾸세요."
        ),
    )
    prompt: str = Field(
        default="$prompt",
        title="맡길 일",
        description="대상에게 넘길 일의 틀입니다. $prompt는 받은 프롬프트입니다.",
        json_schema_extra=x_ui(tier="basic", when="맡기는 일의 내용을 바꾸고 싶을 때 바꾸세요."),
    )
    description: str | None = Field(
        default=None,
        title="짧은 설명",
        description="위임 호출에 붙일 짧은 설명입니다. 비우면 대상 설명을 씁니다.",
        json_schema_extra=x_ui(tier="advanced", example="자료 조사"),
    )
    response: str = Field(
        default="$prompt",
        title="대상의 답",
        description="대상이 돌려줄 답의 틀입니다. $prompt·$agent_name 등을 씁니다.",
        json_schema_extra=x_ui(tier="basic", when="맡은 에이전트의 답을 바꾸고 싶을 때 바꾸세요."),
    )
    tool_calls: list[FakeToolCall] = Field(
        default_factory=list,
        title="대상의 도구 호출",
        description="대상이 부른 것으로 기록할 도구 호출입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    status: str = Field(
        default="completed",
        min_length=1,
        title="종료 상태",
        description="대상이 끝난 상태입니다(completed, failed, stopped).",
        json_schema_extra=x_ui(tier="advanced"),
    )
    delay_ms: int = Field(
        default=0,
        ge=0,
        title="지연",
        description="끝나기 전에 기다릴 시간입니다.",
        json_schema_extra=x_ui(tier="advanced", unit="ms"),
    )
    usage: FakeTaskUsage | None = Field(
        default=None,
        title="보고할 사용량",
        description="대상의 사용량입니다. 비우면 글자·호출 수로 셉니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )

    def render_prompt(self, variables: dict[str, str]) -> str:
        """과제 템플릿을 채운다(위임자 변수)."""
        return Template(self.prompt).safe_substitute(variables)

    def render_response(self, variables: dict[str, str]) -> str:
        """결과 템플릿을 채운다(대상 변수)."""
        return Template(self.response).safe_substitute(variables)


class FakeHostToolWhen(BaseModel):
    """앞선 플랫폼 도구 결과를 보고 이 호출을 할지 정하는 조건입니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # `host_tool_calls[].when`: 앞선 플랫폼 도구 결과를 보고 이 호출을 할지 정한다.
    #
    # 주어진 조건이 모두 맞아야 부른다. 볼 결과가 없으면(첫 호출이거나 건너뛴 호출) 부르지 않는다.

    model_config = ConfigDict(extra="forbid")

    after: int | None = Field(
        default=None,
        ge=1,
        title="볼 호출 번호",
        description="결과를 볼 앞선 호출 번호입니다(1부터). 비우면 바로 앞 호출입니다.",
        json_schema_extra=x_ui(tier="advanced", example=1),
    )
    contains: str | None = Field(
        default=None,
        title="들어 있을 글",
        description="앞선 결과에 이 글이 있어야 부릅니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="앞 결과에 따라 호출을 건너뛰는 상황을 확인할 때 적으세요.",
            example="승인",
        ),
    )
    not_contains: str | None = Field(
        default=None,
        title="없어야 할 글",
        description="앞선 결과에 이 글이 없어야 부릅니다.",
        json_schema_extra=x_ui(tier="advanced", example="오류"),
    )
    is_error: bool | None = Field(
        default=None,
        title="오류 여부",
        description="앞선 결과가 오류인지(켬) 아닌지(끔)를 봅니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    ignore_case: bool = Field(
        default=True,
        title="대소문자 무시",
        description="글을 비교할 때 대소문자를 가리지 않습니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )

    def matches(self, text: str, is_error: bool) -> bool:
        """앞선 결과(`text`, `is_error`)가 조건에 맞으면 참."""

        def norm(value: str) -> str:
            return value.casefold() if self.ignore_case else value

        if self.contains is not None and norm(self.contains) not in norm(text):
            return False
        if self.not_contains is not None and norm(self.not_contains) in norm(text):
            return False
        return self.is_error is None or self.is_error == is_error


class FakeHostToolCall(BaseModel):
    """응답 전에 부를 플랫폼 도구 호출 하나입니다. 결과를 응답에 넣을 수 있습니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # `host_tool_calls` 항목 하나: 요청의 플랫폼 도구(`AgentRequest.host_tools`)를 부른다.
    #
    # `input`의 문자열은 위임자 변수(`$prompt`, 앞선 결과 `$host_N` 등)로 채운다. 결과는
    # `$host_N`(텍스트)·`$host_N_status`(succeeded|failed|skipped|cancelled)로 응답 템플릿에
    # 들어가고, `append`가 참이면 응답 끝에도 붙는다. 요청에 없는 도구면 오류 결과다(SDK처럼).

    model_config = ConfigDict(extra="forbid")

    tool: str = Field(
        min_length=1,
        title="도구 이름",
        description="부를 플랫폼 도구 이름입니다(예: 위임 도구).",
        json_schema_extra=x_ui(
            tier="basic",
            when="다른 플랫폼 도구 호출을 확인하고 싶을 때 바꾸세요.",
            example="delegate",
        ),
    )
    input: Any = Field(
        default_factory=dict,
        title="도구 입력",
        description="도구에 넘길 입력의 틀입니다. $prompt 등을 씁니다.",
        json_schema_extra=x_ui(tier="basic", when="도구에 넘기는 값을 바꾸고 싶을 때 바꾸세요."),
    )
    when: FakeHostToolWhen | None = Field(
        default=None,
        title="부를 조건",
        description="앞선 결과에 따라 부를지 정합니다. 비우면 항상 부릅니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    append: bool = Field(
        default=True,
        title="결과 붙이기",
        description="도구 결과를 답 끝에 붙입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class FakeAsk(BaseModel):
    """응답 전에 사용자에게 묻거나 승인을 받는 흉내 하나입니다. 되묻기 흐름을 시험할 때 씁니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # `ask` 항목 하나: 응답 전에 사용자에게 상호작용을 연다.
    #
    # sink가 `InteractivePort`이고 요청의 허용(`AgentRequest.interactions.kinds`)에 `kind`가
    # 있을 때만 연다. 결과는 응답 템플릿 변수 `$answer_N`(1부터)·`$answer_N_status`로
    # 들어간다:
    # answered면 `answer_path`(JSON Pointer)가 가리키는 응답 값, 없으면 응답 전체 JSON.
    # 만료·취소면 상태 문자열(`expired`·`cancelled`), 열 수 없으면 `unavailable`.
    # `title`·`message`·`payload`의 문자열은 위임자 변수(`$prompt` 등)로 채운다.

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(
        min_length=1,
        title="요청 종류",
        description="열 요청 종류입니다(예: question).",
        json_schema_extra=x_ui(
            tier="basic", when="승인 등 다른 요청 카드를 확인하고 싶을 때 바꾸세요."
        ),
    )
    title: str = Field(
        default="",
        title="제목",
        description="요청 카드 제목입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="요청 카드 제목이 어떻게 보이는지 확인할 때 바꾸세요.",
            example="확인 필요",
        ),
    )
    message: str = Field(
        default="",
        title="안내",
        description="요청 카드 안내 문구입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="요청 카드 안내가 어떻게 보이는지 확인할 때 바꾸세요.",
            example="계속할까요?",
        ),
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        title="요청 내용",
        description="요청 종류가 받는 추가 내용입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    response_schema: dict[str, Any] | None = Field(
        default=None,
        title="응답 형식",
        description="받을 응답의 형식입니다. 비우면 종류 기본값입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    timeout_seconds: float | None = Field(
        default=None,
        gt=0,
        title="대기 한도",
        description="답을 기다리는 시간입니다. 비우면 설정값입니다.",
        json_schema_extra=x_ui(tier="advanced", example=60, unit="초"),
    )
    answer_path: str | None = Field(
        default=None,
        pattern=r"^(/.*)?$",
        title="답 위치",
        description="응답에서 $answer_N에 넣을 값의 위치입니다(예: /text).",
        json_schema_extra=x_ui(tier="advanced", example="/text"),
    )

    def render(self, variables: dict[str, str]) -> dict[str, Any]:
        """제목·안내·payload 문자열을 채운 요청 필드."""
        data: dict[str, Any] = {
            "kind": self.kind,
            "title": fill_template(self.title, variables),
            "message": fill_template(self.message, variables),
            "payload": fill_template(self.payload, variables),
        }
        if self.response_schema is not None:
            data["response_schema"] = self.response_schema
        if self.timeout_seconds is not None:
            data["timeout_seconds"] = self.timeout_seconds
        return data


DEFAULT_OBSERVE_SWITCHES: dict[str, str] = {"hook": "hooks", "mcp": "mcp"}
"""관측 이벤트 type의 첫 세그먼트 → 켜져 있어야 하는 `AgentRequest.observe` 키(`when` 생략 시).

`ObserveSettings`(계약)의 키 이름 관례(`hooks`·`mcp`)를 따른다. 다른 접두의 이벤트는 `when`을 준다.
"""

DEFAULT_OBSERVE_COLLECTORS: dict[str, str] = {"hooks": "sdk-hooks", "mcp": "mcp-calls"}
"""옛 관측 키(스위치) → 같은 뜻의 수집기 id(`observe.collectors`의 키, 4R.8).

claude-sdk의 옛 키 대응표(`LEGACY_OBSERVE_KEYS`의 bool 행)와 같은 규칙이다:
`collectors[id].enabled`가 bool이면 그것이 옛 키를 이긴다. 대응표에 없는 스위치는 스위치 이름
자체를 수집기 id로도 본다
(`when: example.tool_count`). 설치자 설정 `observe_collectors`로 바꾼다.
"""

DEFAULT_PROBE_FORMAT = "hook-probe/1"
"""hook probe 기록 흉내의 `format` 기본값(`agent-console-hook-probe` 기록 형식 이름, 데이터)."""

HOOK_PROBE_SWITCH = "hook_probe"
"""hook probe 기록 흉내를 켜는 `AgentRequest.observe` 키(`ObserveSettings.hook_probe`)."""


def observe_switch_on(
    observe: Mapping[str, Any],
    switch: str,
    collectors: Mapping[str, str] = DEFAULT_OBSERVE_COLLECTORS,
) -> bool:
    """관측 설정에서 `switch`가 켜졌는가.

    1. `observe.collectors[<수집기 id>].enabled`가 bool이면 그 값(수집기 id = `collectors[switch]`,
       없으면 `switch` 자체).
    2. 아니면 옛 키 `observe[switch] is True`.
    """
    table = observe.get("collectors")
    if isinstance(table, Mapping):
        setting = table.get(collectors.get(switch, switch))
        if isinstance(setting, Mapping) and isinstance(setting.get("enabled"), bool):
            return bool(setting["enabled"])
    return observe.get(switch) is True


ObservePoint = Literal["start", "tool", "end"]
"""관측 이벤트를 낼 자리: start = 세션 시작 직후, tool = 규칙의 도구 호출 다음(위임 전),
end = 응답 텍스트 다음·`agent.usage` 앞(실패여도 낸다, 취소면 내지 않는다)."""


class FakeObserve(BaseModel):
    """hook(도구 실행 전후에 도는 명령)·MCP(외부 도구 서버) 관측 이벤트 흉내입니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # `observe` 항목 하나: hook·MCP 관측 이벤트 흉내.
    #
    # 이벤트 이름과 payload는 데이터다(fake 코드에 hook 종류 목록이 없다). 요청의 관측 설정
    # (`AgentRequest.observe`, = `AgentSettings.observe`)에서 `when` 키가 참일 때만 낸다.
    # payload의 문자열은 `string.Template`로 채운다(`$prompt`, `$session_id`, `$agent_id` 등 —
    # 규칙 도구 호출의 id는 `$session_id:tool0`, `$session_id:tool1`…).

    model_config = ConfigDict(extra="forbid")

    type: str = Field(
        pattern=r"^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)+$",
        title="이벤트 종류",
        description=(
            "흉내 낼 관측 이벤트 이름입니다(예: hook.invoked = hook(도구 실행 전후 명령) 실행)."
        ),
        json_schema_extra=x_ui(tier="basic", when="다른 관측 이벤트를 흉내 내고 싶을 때 바꾸세요."),
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        title="이벤트 내용",
        description="이벤트에 실을 내용의 틀입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    after: ObservePoint = Field(
        default="start",
        title="낼 자리",
        description="시작 직후(start), 도구 호출 뒤(tool), 끝(end) 중 언제 낼지입니다.",
        json_schema_extra=x_ui(
            enum_labels={"start": "시작 직후", "tool": "도구 호출 뒤", "end": "끝날 때"},
            tier="advanced",
        ),
    )
    when: str | None = Field(
        default=None,
        min_length=1,
        title="켜는 관측 키",
        description="켜져 있어야 할 관측 설정 이름입니다. 비우면 이벤트 종류로 정합니다.",
        json_schema_extra=x_ui(tier="advanced", example="hooks"),
    )

    @model_validator(mode="after")
    def _known_switch(self) -> FakeObserve:
        if self.when is None and self.family not in DEFAULT_OBSERVE_SWITCHES:
            raise ValueError(
                f"type 계열 {self.family!r}의 관측 스위치를 모릅니다: when 키를 지정하세요"
            )
        return self

    @property
    def family(self) -> str:
        """type의 첫 세그먼트."""
        return self.type.split(".", 1)[0]

    @property
    def switch(self) -> str:
        """이 이벤트를 켜는 `AgentRequest.observe` 키."""
        return self.when if self.when is not None else DEFAULT_OBSERVE_SWITCHES[self.family]

    def enabled(
        self,
        observe: Mapping[str, Any],
        collectors: Mapping[str, str] = DEFAULT_OBSERVE_COLLECTORS,
    ) -> bool:
        """요청의 관측 설정에서 스위치가 켜졌으면 True(`observe_switch_on`: `collectors`가 옛 키를
        이긴다)."""
        return observe_switch_on(observe, self.switch, collectors)

    def render(self, variables: dict[str, str]) -> dict[str, Any]:
        """payload 문자열을 채운다."""
        filled: dict[str, Any] = fill_template(self.payload, variables)
        return filled


class FakeHookProbe(BaseModel):
    """hook(도구 실행 전후에 도는 명령) 실행 기록 한 줄을 흉내 냅니다. 명령은 실행하지 않습니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # `hook_probe` 항목 하나: hook probe 기록(`hook-probe/1`) 한 줄 흉내.
    #
    # 요청의 관측 설정 `observe.hook_probe`가 참이고 실행 폴더(`AgentRequest.run_folder`)가
    # 있을 때만 `<run_folder>/<hook_probe_folder>/<세션>.jsonl`에 덧붙인다
    # (실제 probe처럼 E2E·로그 출처 `hook-probe-jsonl`이 읽는다). 명령은 실행하지 않는다.
    # 문자열 필드는 `string.Template`로 채운다(`$session_id`, `$prompt` 등).
    # 기록 키: format, probe_id, event, session_id, tool_use_id,
    # tool, matcher, context(= `run_context`), started_at, ended_at, duration_ms, exit_code, error,
    # decision{value, source, reason}, input, agent_id, agent_type, cwd, simulated + `fields`.

    model_config = ConfigDict(extra="forbid")

    event: str = Field(
        min_length=1,
        title="hook 이벤트",
        description="기록할 hook(도구 실행 전후에 도는 명령) 이벤트 이름입니다(예: PreToolUse).",
        json_schema_extra=x_ui(
            tier="basic", when="다른 hook 이벤트 기록을 확인하고 싶을 때 바꾸세요."
        ),
    )
    matcher: str | None = Field(
        default=None,
        title="매처",
        description="기록할 hook(도구 실행 전후에 도는 명령) 대상 필터입니다.",
        json_schema_extra=x_ui(tier="advanced", example="Bash"),
    )
    tool: str | None = Field(
        default=None,
        title="도구 이름",
        description="기록할 도구 이름입니다.",
        json_schema_extra=x_ui(tier="advanced", example="Bash"),
    )
    tool_use_id: str | None = Field(
        default=None,
        title="도구 호출 id",
        description="기록할 도구 호출 id의 틀입니다.",
        json_schema_extra=x_ui(tier="advanced", example="$session_id:tool0"),
    )
    input: Any = Field(
        default=None,
        title="hook 입력",
        description="기록할 hook(도구 실행 전후에 도는 명령) 입력의 틀입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    exit_code: int | None = Field(
        default=0,
        title="종료 코드",
        description="기록할 명령 종료 코드입니다. 비우면 실행 실패로 기록합니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    decision: str = Field(
        default="none",
        min_length=1,
        title="결정",
        description="기록할 hook(도구 실행 전후에 도는 명령) 결정입니다(예: allow, deny).",
        json_schema_extra=x_ui(tier="advanced"),
    )
    reason: str | None = Field(
        default=None,
        title="결정 이유",
        description="기록할 결정 이유입니다.",
        json_schema_extra=x_ui(tier="advanced", example="위험한 명령"),
    )
    error: str | None = Field(
        default=None,
        title="오류",
        description="기록할 오류 문구입니다.",
        json_schema_extra=x_ui(tier="advanced", example="시간 초과"),
    )
    duration_ms: int = Field(
        default=0,
        ge=0,
        title="소요 시간",
        description="기록할 소요 시간입니다.",
        json_schema_extra=x_ui(tier="advanced", unit="ms"),
    )
    agent_id: str | None = Field(
        default=None,
        title="에이전트 id",
        description="기록할 서브에이전트 id입니다.",
        json_schema_extra=x_ui(tier="advanced", example="sub-1"),
    )
    agent_type: str | None = Field(
        default=None,
        title="에이전트 종류",
        description="기록할 서브에이전트 종류입니다.",
        json_schema_extra=x_ui(tier="advanced", example="reviewer"),
    )
    after: ObservePoint = Field(
        default="start",
        title="쓸 자리",
        description="시작 직후(start), 도구 호출 뒤(tool), 끝(end) 중 언제 쓸지입니다.",
        json_schema_extra=x_ui(
            enum_labels={"start": "시작 직후", "tool": "도구 호출 뒤", "end": "끝날 때"},
            tier="advanced",
        ),
    )
    format: str = Field(
        default=DEFAULT_PROBE_FORMAT,
        min_length=1,
        title="기록 형식",
        description="기록 형식 이름입니다. 보통은 바꾸지 않습니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    fields: dict[str, Any] = Field(
        default_factory=dict,
        title="추가 키",
        description="기록에 덧붙이거나 덮어쓸 키입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )

    def record(
        self,
        variables: Mapping[str, str],
        *,
        probe_id: str,
        session_id: str,
        context: Mapping[str, str],
        cwd: str | None,
        started_at: float,
    ) -> dict[str, Any]:
        """기록 한 줄(JSON 객체)."""
        row: dict[str, Any] = {
            "format": self.format,
            "probe_id": probe_id,
            "event": self.event,
            "session_id": session_id,
            "tool_use_id": fill_template(self.tool_use_id, variables),
            "tool": self.tool,
            "matcher": self.matcher,
            "context": dict(context),
            "started_at": started_at,
            "ended_at": started_at + self.duration_ms / 1000,
            "duration_ms": self.duration_ms,
            "exit_code": self.exit_code,
            "error": self.error,
            "decision": {
                "value": self.decision,
                "source": "fake-agent",
                "reason": fill_template(self.reason, variables),
            },
            "input": fill_template(self.input, variables),
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "cwd": cwd,
            "simulated": True,
        }
        row.update(fill_template(self.fields, variables))
        return row


class FakeRule(BaseModel):
    """프롬프트가 조건에 맞으면 정해 둔 응답을 냅니다. 조건은 모두 맞아야 합니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # 프롬프트 조건 → 응답. 조건(`contains`·`prefix`·`equals`)을 여러 개 주면 모두 맞아야 하고,
    # 하나도 없으면 항상 맞는다.
    #
    # `response`는 `string.Template` 문법(`$prompt`, `$agent_id`, `$agent_name`, `$model`,
    # `$session_id`, `$bundle`, `$cwd`(요청 작업 폴더, 없으면 빈 문자열), 위임 결과 `$delegate_1`…,
    # 플랫폼 도구 결과 `$host_1`…, 상호작용 결과 `$answer_1`…)이다.
    # `observe`는 요청의 관측 설정이 켜졌을 때만 내는 hook·MCP 이벤트 흉내다(`FakeObserve`).
    # 모르는 변수는 그대로 남는다.

    model_config = ConfigDict(extra="forbid")

    contains: str | None = Field(
        default=None,
        title="들어 있을 글",
        description="프롬프트에 이 글이 있으면 이 규칙을 씁니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="특정 말이 든 메시지에만 이 답을 쓰고 싶을 때 적으세요.",
            example="요약",
        ),
    )
    prefix: str | None = Field(
        default=None,
        title="시작 글",
        description="프롬프트가 이 글로 시작하면 이 규칙을 씁니다.",
        json_schema_extra=x_ui(tier="advanced", example="/plan"),
    )
    equals: str | None = Field(
        default=None,
        title="같은 글",
        description="프롬프트가 이 글과 같으면 이 규칙을 씁니다.",
        json_schema_extra=x_ui(tier="advanced", example="안녕"),
    )
    ignore_case: bool = Field(
        default=True,
        title="대소문자 무시",
        description="글을 비교할 때 대소문자를 가리지 않습니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    response: str = Field(
        default="$prompt",
        title="답",
        description="돌려줄 답의 틀입니다. $prompt·$agent_name 등을 씁니다.",
        json_schema_extra=x_ui(tier="basic", when="체험용 답의 내용을 바꾸고 싶을 때 바꾸세요."),
    )
    structured: Any = Field(
        default=None,
        title="구조화 결과",
        description="함께 돌려줄 구조화 결과입니다(그대로 전달).",
        json_schema_extra=x_ui(tier="advanced"),
    )
    tool_calls: list[FakeToolCall] = Field(
        default_factory=list,
        title="도구 호출",
        description="답 전에 부른 것으로 기록할 도구 호출입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    delegate: list[FakeDelegation] = Field(
        default_factory=list,
        title="위임",
        description="순서대로 흉내 낼 서브에이전트 위임입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    ask: list[FakeAsk] = Field(
        default_factory=list,
        title="사용자에게 묻기",
        description="답 전에 순서대로 열 질문·승인 요청입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    host_tool_calls: list[FakeHostToolCall] = Field(
        default_factory=list,
        title="플랫폼 도구 호출",
        description="위임 다음에 순서대로 부를 플랫폼 도구입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    observe: list[FakeObserve] = Field(
        default_factory=list,
        title="관측 이벤트",
        description=(
            "관측을 켰을 때 낼 hook(도구 실행 전후에 도는 명령)·MCP(외부 도구 서버) 이벤트입니다."
        ),
        json_schema_extra=x_ui(tier="advanced"),
    )
    hook_probe: list[FakeHookProbe] = Field(
        default_factory=list,
        title="hook 기록",
        description="hook(도구 실행 전후에 도는 명령) 전체 기록이 켜졌을 때 남길 기록입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    fail: FakeFailure | None = Field(
        default=None,
        title="실패",
        description="주면 답 대신 이 내용으로 실패합니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    delay_ms: int | None = Field(
        default=None,
        ge=0,
        title="조각 사이 지연",
        description="글 조각 사이에 기다릴 시간입니다. 비우면 전체 설정값입니다.",
        json_schema_extra=x_ui(tier="advanced", example=50, unit="ms"),
    )
    chunk_chars: int | None = Field(
        default=None,
        ge=1,
        title="조각 크기",
        description="글 조각 하나의 글자 수입니다. 비우면 전체 설정값입니다.",
        json_schema_extra=x_ui(tier="advanced", example=16, unit="자"),
    )
    usage: dict[str, Any] | None = Field(
        default=None,
        title="보고할 사용량",
        description="보고할 사용량입니다. 비우면 단어 수로 셉니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    llm_duration_ms: int | None = Field(
        default=None,
        ge=0,
        title="모델 호출 소요",
        description=(
            "마지막 사용량 기록에 실을 모델 호출 소요 시간입니다. 비우면 싣지 않습니다(모름)."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="관측 화면의 모델 호출 소요 표시를 확인하고 싶을 때 넣으세요.",
            example=1200,
            unit="ms",
        ),
    )

    def matches(self, prompt: str) -> bool:
        """이 규칙의 조건이 프롬프트에 맞으면 참."""
        text = prompt.casefold() if self.ignore_case else prompt

        def norm(value: str) -> str:
            return value.casefold() if self.ignore_case else value

        if self.contains is not None and norm(self.contains) not in text:
            return False
        if self.prefix is not None and not text.startswith(norm(self.prefix)):
            return False
        return self.equals is None or text == norm(self.equals)

    def render(self, variables: dict[str, str]) -> str:
        """응답 템플릿을 채운다(모르는 변수는 그대로)."""
        return Template(self.response).safe_substitute(variables)


class FakeBackendOptions(BaseModel):
    """모델 없이 정해 둔 응답을 내는 시험용 실행 설정입니다. 위 규칙부터 처음 맞는 것을 씁니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # `Agent.backend_options` 형식. 위에서부터 처음 맞는 규칙을 쓰고, 없으면 `default`.

    model_config = ConfigDict(extra="forbid")

    rules: list[FakeRule] = Field(
        default_factory=list,
        title="규칙",
        description="프롬프트에 따라 답을 고르는 규칙입니다. 위에서부터 처음 맞는 것을 씁니다.",
        json_schema_extra=x_ui(
            tier="basic", when="메시지에 따라 다른 답을 확인하고 싶을 때 더하세요."
        ),
    )
    default: FakeRule = Field(
        default_factory=FakeRule,
        title="기본 답",
        description="맞는 규칙이 없을 때 쓰는 규칙입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="맞는 규칙이 없을 때의 답을 바꾸고 싶을 때 바꾸세요."
        ),
    )
    delay_ms: int = Field(
        default=0,
        ge=0,
        title="조각 사이 지연",
        description="글 조각 사이에 기다릴 기본 시간입니다.",
        json_schema_extra=x_ui(tier="advanced", unit="ms"),
    )
    chunk_chars: int = Field(
        default=16,
        ge=1,
        title="조각 크기",
        description="글 조각 하나의 기본 글자 수입니다.",
        json_schema_extra=x_ui(tier="advanced", unit="자"),
    )
    echo_bundle: bool = Field(
        default=False,
        title="묶음 요약 붙이기",
        description="받은 리소스 묶음 요약을 답 끝에 붙입니다(화면 확인용).",
        json_schema_extra=x_ui(tier="advanced"),
    )

    def pick(self, prompt: str) -> FakeRule:
        """프롬프트에 맞는 첫 규칙(없으면 `default`)."""
        for rule in self.rules:
            if rule.matches(prompt):
                return rule
        return self.default


class FakeRateLimit(BaseModel):
    """흉내 낼 `usage.rate_limit` 하나(설치자 설정 `rate_limits`, design §R4.3).

    `resets_at`(epoch 초)이나 `resets_in_seconds`(실행 시각 기준 상대값) 중 하나만 준다.
    """

    model_config = ConfigDict(extra="forbid")

    window: str = Field(min_length=1, description="창 id(예: five_hour). 고정 목록 아님.")
    status: str | None = Field(default=None, description="상태 문자열(예: allowed).")
    utilization: float | None = Field(default=None, ge=0, description="사용률(0~1).")
    resets_at: float | None = None
    resets_in_seconds: float | None = Field(default=None, ge=0)
    overage_status: str | None = None

    @model_validator(mode="after")
    def _one_reset(self) -> FakeRateLimit:
        if self.resets_at is not None and self.resets_in_seconds is not None:
            raise ValueError("resets_at과 resets_in_seconds 중 하나만 줄 수 있습니다")
        return self


def fill_template(value: Any, variables: Mapping[str, str]) -> Any:
    """문자열(중첩 dict·list 안 포함)을 `string.Template.safe_substitute`로 채운다."""
    if isinstance(value, str):
        return Template(value).safe_substitute(variables)
    if isinstance(value, dict):
        return {k: fill_template(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [fill_template(v, variables) for v in value]
    return value


def fake_config_schema() -> dict[str, Any]:
    """`BackendDescriptor.config_schema`로 쓰는 JSON Schema."""
    return FakeBackendOptions.model_json_schema()
