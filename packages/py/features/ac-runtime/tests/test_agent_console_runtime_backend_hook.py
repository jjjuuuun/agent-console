"""`ConfigurableBackend`(X3 선택 훅) 예제 구현과 판별."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_console_contracts import BackendDescriptor, ModelInfo
from agent_console_runtime import (
    BACKEND_OPTIONS_HOOK,
    AgentRequest,
    AgentResult,
    BackendEventSink,
    CancelToken,
    ConfigurableBackend,
    EnvSecretProvider,
    ExecutionBackend,
    SecretResolver,
)


class EchoBackend:
    """예제: 설치자 설정 `prefix`를 받는 백엔드."""

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix
        self.descriptor = BackendDescriptor(id="echo", title="Echo")

    @classmethod
    def from_options(
        cls, options: Mapping[str, Any], *, secrets: SecretResolver, environ: Mapping[str, str]
    ) -> EchoBackend:
        unknown = set(options) - {"prefix"}
        if unknown:
            raise ValueError(f"모르는 키: {sorted(unknown)}")
        return cls(prefix=str(options.get("prefix", "")))

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def run(
        self, req: AgentRequest, sink: BackendEventSink, cancel: CancelToken
    ) -> AgentResult:
        return AgentResult(status="succeeded", text=self.prefix + req.prompt)


class PlainBackend:
    descriptor = BackendDescriptor(id="plain", title="Plain")

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def run(
        self, req: AgentRequest, sink: BackendEventSink, cancel: CancelToken
    ) -> AgentResult:
        return AgentResult(status="succeeded", text=req.prompt)


def test_configurable_backend_is_optional_hook() -> None:
    assert BACKEND_OPTIONS_HOOK == "from_options"
    echo = EchoBackend()
    assert isinstance(echo, ExecutionBackend)
    assert isinstance(echo, ConfigurableBackend)
    assert not isinstance(PlainBackend(), ConfigurableBackend)
    resolver = SecretResolver([EnvSecretProvider({})])
    built = type(echo).from_options({"prefix": "> "}, secrets=resolver, environ={})
    assert built.prefix == "> "
