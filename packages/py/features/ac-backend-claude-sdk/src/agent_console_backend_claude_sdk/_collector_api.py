"""관측 수집기(X7) 프로토콜·문맥·베이스·설정 해석(design §4R.3).

수집기는 실행에 개입하지 않고 SDK 훅 입력·SDK 메시지에서 이벤트를 모은다. 받는 원재료가 백엔드마다
다르므로 프로토콜은 이 백엔드(claude-sdk)가 정의하고, 공용 `CollectorDescriptor.backend`로 거른다.
이 모듈은 특정 수집기 id를 모른다(옛 관측 키 대응표 `LEGACY_OBSERVE_KEYS`만 데이터로 둔다).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, ValidationError

from agent_console_contracts import CollectorDescriptor, JsonObject

__all__ = [
    "LEGACY_OBSERVE_KEYS",
    "BaseClaudeSdkCollector",
    "ClaudeSdkCollector",
    "CollectedEvent",
    "CollectorContext",
    "ResolvedCollector",
    "resolve_collector_settings",
]


@dataclass(frozen=True, slots=True)
class CollectedEvent:
    """수집기가 낸 이벤트 하나(백엔드가 RunEvent 일반형으로 내보낸다).

    Attributes:
        type: 이벤트 type(예: `hook.invoked`).
        payload: 이벤트 payload(JSON 직렬화 가능한 값).
        raw: 원본(SDK 메시지·훅 입력). 백엔드가 정제(비밀 가림·크기 제한)한 뒤 `raw`로 붙인다.
            None이면 raw 없음.
        parent_tool_use_id: SDK 메시지의 `parent_tool_use_id`. 백엔드가 서브에이전트 귀속
            (actor·하위 node_path)에 쓴다. None이면 이 실행의 에이전트 자신.
    """

    type: str
    payload: Mapping[str, Any]
    raw: object | None = None
    parent_tool_use_id: str | None = None


@dataclass
class CollectorContext:
    """실행 하나와 수집기 하나의 문맥. 백엔드가 실행마다 새로 만든다.

    Attributes:
        collector_id: 수집기 id(`descriptor.id`).
        config: 해석한 수집기 설정(`observe.collectors[id].config`, 없으면 빈 객체).
        clock: 시각 함수(초). 소요 시간 측정에 쓴다(백엔드에 주입한 clock).
        redact: payload에 실을 값을 가리는 함수(비밀 값·패턴). raw는 백엔드가 따로 정제한다.
        state: 이 실행 동안 수집기가 쓰는 상태(열린 호출 등). 수집기 인스턴스는 여러 실행이
            함께 쓰므로 실행별 상태는 여기에 둔다.
    """

    collector_id: str
    config: JsonObject
    clock: Callable[[], float]
    redact: Callable[[Any], Any] = lambda value: value
    state: dict[str, Any] = field(default_factory=dict)
    _pending: list[CollectedEvent] = field(default_factory=list, repr=False)

    def emit(
        self,
        type: str,
        payload: Mapping[str, Any],
        *,
        raw: object | None = None,
        parent_tool_use_id: str | None = None,
    ) -> None:
        """이벤트를 낸다(동기. 백엔드가 수집기 호출이 끝나면 순서대로 내보낸다)."""
        self._pending.append(CollectedEvent(type, payload, raw, parent_tool_use_id))

    def drain(self) -> list[CollectedEvent]:
        """쌓인 이벤트를 꺼낸다(꺼낸 것은 비운다). 백엔드가 부른다."""
        out, self._pending = self._pending, []
        return out


@runtime_checkable
class ClaudeSdkCollector(Protocol):
    """claude-sdk 관측 수집기(X7) 프로토콜.

    보통 `BaseClaudeSdkCollector`를 상속해 필요한 것만 고친다.

    - 실행에 개입하지 않는다(훅 결과는 백엔드가 항상 `{}`로 돌려준다).
    - 예외는 백엔드가 삼키고 실행마다 수집기별 경고 이벤트(`log.warning`) 하나로 남긴다.
    - 등록: entry point 그룹 `agent_console.collectors`(클래스면 인자 없이 만든다).
      `descriptor.backend`가 백엔드 id와 같은 것만 쓴다.
    """

    descriptor: CollectorDescriptor

    def hook_events(self, config: JsonObject) -> Sequence[str]:
        """관측 콜백을 걸 SDK 훅 이벤트 이름(데이터). 없으면 빈 목록."""
        ...

    def include_hook_events(self, config: JsonObject) -> bool:
        """CLI가 설정 hook 실행을 메시지(`HookEventMessage`)로 보내게 할지
        (SDK `include_hook_events`)."""
        ...

    async def on_hook(
        self,
        event: str,
        data: Mapping[str, Any],
        tool_use_id: str | None,
        ctx: CollectorContext,
    ) -> None:
        """`hook_events`에 건 SDK 훅 콜백이 불렸을 때. `data`는 SDK 훅 입력 그대로다."""
        ...

    def on_message(self, message: object, ctx: CollectorContext) -> None:
        """SDK 메시지 하나(init·assistant·user·hook 메시지 등)를 받았을 때(번역 이벤트 뒤)."""
        ...

    def config_problems(self, config: JsonObject) -> list[str]:
        """설정 검증(`validate_settings`). 문제 문장 목록(값은 싣지 않는다), 없으면 빈 목록."""
        ...


class BaseClaudeSdkCollector:
    """수집기 공통 베이스: 모든 메서드의 기본 구현(아무것도 하지 않음)과 설정 모델 검증.

    하위 클래스는 `descriptor`(또는 `id`·`title`·`emits`·`config_model` 클래스 속성)를 정하고
    `on_hook`·`on_message` 등 필요한 것만 고친다. `config_model`(pydantic)이 있으면
    `descriptor.config_schema`는 그 스키마이고 `parse_config`·`config_problems`가 그것으로 검증한다.

    Args:
        backend: 이 수집기를 쓸 백엔드 id(기본 `default_backend`).
    """

    id: ClassVar[str] = ""
    title: ClassVar[str] = ""
    description: ClassVar[str | None] = None
    emits: ClassVar[tuple[str, ...]] = ()
    config_model: ClassVar[type[BaseModel] | None] = None
    default_backend: ClassVar[str] = ""

    def __init__(self, *, backend: str | None = None) -> None:
        schema = self.config_model.model_json_schema() if self.config_model is not None else {}
        self.descriptor = CollectorDescriptor(
            id=self.id,
            title=self.title,
            backend=backend or self.default_backend,
            description=self.description,
            config_schema=schema,
            emits=list(self.emits),
        )

    def parse_config(self, config: JsonObject) -> Any:
        """`config_model`로 검증한 설정(모델이 없으면 받은 그대로). 틀리면 `ValidationError`."""
        if self.config_model is None:
            return config
        return self.config_model.model_validate(config)

    def config_problems(self, config: JsonObject) -> list[str]:
        if self.config_model is None:
            return []
        try:
            self.config_model.model_validate(config)
        except ValidationError as exc:
            return [
                f"{'.'.join(str(p) for p in e['loc']) or '(root)'}: {e['msg']}"
                for e in exc.errors(include_input=False, include_url=False)
            ]
        return []

    def hook_events(self, config: JsonObject) -> Sequence[str]:
        return ()

    def include_hook_events(self, config: JsonObject) -> bool:
        return False

    async def on_hook(
        self,
        event: str,
        data: Mapping[str, Any],
        tool_use_id: str | None,
        ctx: CollectorContext,
    ) -> None:
        return None

    def on_message(self, message: object, ctx: CollectorContext) -> None:
        return None


@dataclass(frozen=True, slots=True)
class ResolvedCollector:
    """유효 관측 설정에서 해석한 수집기 하나의 사용 여부와 설정."""

    enabled: bool = False
    config: JsonObject = field(default_factory=dict)


LEGACY_OBSERVE_KEYS: Mapping[str, tuple[str, str | None]] = {
    "hooks": ("sdk-hooks", None),
    "mcp": ("mcp-calls", None),
    "hook_events": ("sdk-hooks", "events"),
}
"""옛 관측 키 → (수집기 id, 설정 키). 설정 키가 None이면 그 값(bool)이 `enabled`다(design §4R.3).
읽기 호환용 데이터다. 다른 대응이 필요하면 `resolve_collector_settings(legacy=...)`로 바꾼다."""


def resolve_collector_settings(
    observe: Mapping[str, Any] | None,
    *,
    legacy: Mapping[str, tuple[str, str | None]] = LEGACY_OBSERVE_KEYS,
) -> dict[str, ResolvedCollector]:
    """유효 관측 설정(`AgentRequest.observe` = `ObserveSettings` 덤프) → 수집기 id별 사용 여부·설정.

    1. 옛 키(`legacy` 대응표)를 먼저 읽는다: bool 키는 `enabled`, 그 밖은 `config[설정 키]`.
    2. `collectors{id: {enabled?, config?}}`의 값이 있는 칸이 1의 같은 칸을 이긴다
       (`config`는 통째로 바꾼다).
    3. `enabled`를 정하지 않은 수집기는 꺼짐이다(코드 기본값 꺼짐).

    모양이 틀린 항목(객체가 아닌 값, bool이 아닌 enabled 등)은 건너뛴다. 결과에는 언급된 id만 있다.
    """
    enabled: dict[str, bool] = {}
    configs: dict[str, JsonObject] = {}
    data = observe or {}
    for key, (collector_id, config_key) in legacy.items():
        if key not in data or data[key] is None:
            continue
        value = data[key]
        if config_key is None:
            if isinstance(value, bool):
                enabled[collector_id] = value
        else:
            configs.setdefault(collector_id, {})[config_key] = value
    collectors = data.get("collectors")
    if isinstance(collectors, Mapping):
        for collector_id, setting in collectors.items():
            if not isinstance(collector_id, str) or not isinstance(setting, Mapping):
                continue
            flag = setting.get("enabled")
            if isinstance(flag, bool):
                enabled[collector_id] = flag
            config = setting.get("config")
            if isinstance(config, Mapping):
                configs[collector_id] = dict(config)
            else:
                configs.setdefault(collector_id, {})
    return {
        cid: ResolvedCollector(enabled=enabled.get(cid, False), config=configs.get(cid, {}))
        for cid in (*enabled, *(c for c in configs if c not in enabled))
    }
