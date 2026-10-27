"""agent-console-backend-fake-agent: 모델 없이 에이전트 실행을 흉내 내는 개발·테스트용 실행 백엔드.

응답·지연·실패·도구 호출은 `Agent.backend_options`(형식 `FakeBackendOptions`)의
규칙 데이터로 정한다.

공개 API:
    - ``FakeBackend``: X3 `ExecutionBackend` 구현(entry point
      `agent_console.backends:fake-agent`, 표시 이름 ``FAKE_BACKEND_TITLE``, 디스크립터
      `ui_hints.hidden = true`로 사용자 화면에서 기본 숨김)
    - 설정 모델: ``FakeBackendOptions``, ``FakeRule``, ``FakeToolCall``, ``FakeFailure``,
      ``FakeDelegation``, ``FakeAsk``, ``FakeObserve``, ``FakeTaskUsage``, ``fake_config_schema``,
      ``DEFAULT_OBSERVE_SWITCHES``, ``DEFAULT_OBSERVE_COLLECTORS``·``observe_switch_on``
      (관측 스위치:
      `observe.collectors[id].enabled`가 옛 키를 이긴다), ``FakeHookProbe``(hook probe 기록 흉내,
      `observe.hook_probe`), ``DEFAULT_PROBE_FORMAT``·``HOOK_PROBE_SWITCH``
    - 플랫폼 도구(5R.10, design §5R.6, `capabilities.host_tools = true`): 규칙 `host_tool_calls`
      (``FakeHostToolCall``·``FakeHostToolWhen``)로 `AgentRequest.host_tools`를 부르고 결과를
      `$host_N`·`$host_N_status`(``HostCallStatus``)와 응답 끝에 붙인다. 없는 도구는
      ``UNKNOWN_HOST_TOOL_TEXT`` 오류 결과
    - 준비 상태·연결 테스트(선택 능력, ux-overhaul §15.8): ``FakeBackend.status``(늘
      ``FAKE_READY_STATE``, 톤 ok)·``FakeBackend.probe``(지연 없는 성공)
    - 대본 로그인(5.2R.83, ux-overhaul §15.9, e2e·웹 개발용): 설치자 설정 ``login``
      (``FakeLoginScript``·``FakeLoginTexts``)을 주면 ``capabilities.login/logout``·
      ``login_methods``를 선언하고 ``FakeBackend.start_login``(``FakeScriptedLoginDriver``: 코드
      ``success_code``면 성공, 그 밖 ``fail_reason``)·``logout``을 제공한다. 로그인 상태는 메모리
      (``FakeLoginState``), 상태 점검은 로그인 전 ``FAKE_LOGIN_REQUIRED_STATE``. PTY·네트워크 없음
    - 묶음 미리보기 훅 ``FakeBackend.preview_notes``(info ``HOOK_PROBE_NOTE_CODE``),
      ``DEFAULT_HOOK_PROBE_FOLDER``
    - ``FakeInstallOptions``·``FakeRateLimit``: 설치자 설정 형식(``FakeBackend.from_options`` 훅)
    - ``bundle_summary``·``mask_secret_refs``: 실행 묶음 요약
      (응답에 넣는 옵션 `echo_bundle`·템플릿 변수 `$bundle`)
    - 상수: ``FAKE_BACKEND_ID``(`fake-agent`), ``FAKE_BACKEND_TITLE``,
      ``DEFAULT_DELEGATE_TOOL``, ``DEFAULT_RESOURCE_SLOTS``,
      ``EMPTY_BUNDLE``
"""

from agent_console_backend_fake_agent._backend import (
    DEFAULT_DELEGATE_TOOL,
    DEFAULT_HOOK_PROBE_FOLDER,
    DEFAULT_RESOURCE_SLOTS,
    FAKE_BACKEND_ID,
    FAKE_BACKEND_TITLE,
    FAKE_READY_STATE,
    HOOK_PROBE_NOTE_CODE,
    UNKNOWN_HOST_TOOL_TEXT,
    FakeBackend,
    FakeInstallOptions,
    HostCallStatus,
)
from agent_console_backend_fake_agent._bundle import EMPTY_BUNDLE, bundle_summary, mask_secret_refs
from agent_console_backend_fake_agent._config import (
    DEFAULT_OBSERVE_COLLECTORS,
    DEFAULT_OBSERVE_SWITCHES,
    DEFAULT_PROBE_FORMAT,
    HOOK_PROBE_SWITCH,
    FakeAsk,
    FakeBackendOptions,
    FakeDelegation,
    FakeFailure,
    FakeHookProbe,
    FakeHostToolCall,
    FakeHostToolWhen,
    FakeObserve,
    FakeRateLimit,
    FakeRule,
    FakeTaskUsage,
    FakeToolCall,
    fake_config_schema,
    observe_switch_on,
)
from agent_console_backend_fake_agent._login import (
    FAKE_LOGIN_METHOD_ID,
    FAKE_LOGIN_REQUIRED_STATE,
    FakeLoginScript,
    FakeLoginState,
    FakeLoginTexts,
    FakeScriptedLoginDriver,
)

__all__ = [
    "DEFAULT_DELEGATE_TOOL",
    "DEFAULT_HOOK_PROBE_FOLDER",
    "DEFAULT_OBSERVE_COLLECTORS",
    "DEFAULT_OBSERVE_SWITCHES",
    "DEFAULT_PROBE_FORMAT",
    "DEFAULT_RESOURCE_SLOTS",
    "EMPTY_BUNDLE",
    "FAKE_BACKEND_ID",
    "FAKE_BACKEND_TITLE",
    "FAKE_LOGIN_METHOD_ID",
    "FAKE_LOGIN_REQUIRED_STATE",
    "FAKE_READY_STATE",
    "HOOK_PROBE_NOTE_CODE",
    "HOOK_PROBE_SWITCH",
    "UNKNOWN_HOST_TOOL_TEXT",
    "FakeAsk",
    "FakeBackend",
    "FakeBackendOptions",
    "FakeDelegation",
    "FakeFailure",
    "FakeHookProbe",
    "FakeHostToolCall",
    "FakeHostToolWhen",
    "FakeInstallOptions",
    "FakeLoginScript",
    "FakeLoginState",
    "FakeLoginTexts",
    "FakeObserve",
    "FakeRateLimit",
    "FakeRule",
    "FakeScriptedLoginDriver",
    "FakeTaskUsage",
    "FakeToolCall",
    "HostCallStatus",
    "bundle_summary",
    "fake_config_schema",
    "mask_secret_refs",
    "observe_switch_on",
]
