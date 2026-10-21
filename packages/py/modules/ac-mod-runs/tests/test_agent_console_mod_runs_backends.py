"""백엔드 설치자 설정: 모듈은 `ConfigurableBackend` 훅 유무만 보고 호출한다.

백엔드 id·키의 의미는 모른다.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import pytest

from agent_console_contracts import BackendDescriptor, ModelInfo
from agent_console_mod_runs import BackendOptionsError, configure_backends
from agent_console_runtime import (
    AgentRequest,
    AgentResult,
    BackendEventSink,
    CancelToken,
    EnvSecretProvider,
    Registries,
    SecretResolver,
)


class _Base:
    def __init__(self, backend_id: str, models: list[ModelInfo] | None = None) -> None:
        self.descriptor = BackendDescriptor(id=backend_id, title=backend_id)
        self.models = models or []

    async def list_models(self) -> list[ModelInfo]:
        return list(self.models)

    async def run(
        self, req: AgentRequest, sink: BackendEventSink, cancel: CancelToken
    ) -> AgentResult:
        return AgentResult(status="succeeded", text=req.prompt)


class HookBackend(_Base):
    """예제 플러그인: 설정 `models`를 받는다. 받은 인자를 기록한다."""

    seen: dict[str, Any] = {}  # noqa: RUF012 - 테스트 기록용

    @classmethod
    def from_options(
        cls, options: Mapping[str, Any], *, secrets: SecretResolver, environ: Mapping[str, str]
    ) -> HookBackend:
        if set(options) - {"models"}:
            raise ValueError("모르는 키")
        cls.seen = {"secrets": secrets, "environ": environ}
        return cls("hooked", [ModelInfo.model_validate(m) for m in options.get("models", [])])


def _registries() -> Registries:
    registries = Registries()
    registries.backends.register("hooked", HookBackend("hooked"), source="test")
    registries.backends.register("plain", _Base("plain"), source="test")
    return registries


async def test_configure_backends_calls_hook_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    registries = _registries()
    resolver = SecretResolver([EnvSecretProvider({})])
    environ = {"X": "1"}
    with caplog.at_level(logging.WARNING):
        replaced = configure_backends(
            registries,
            {"hooked": {"models": [{"id": "m1"}]}, "plain": {"a": 1}, "missing": {}},
            secrets=resolver,
            environ=environ,
        )
    assert replaced == ["hooked"]
    hooked = registries.backends.get("hooked")
    assert [m.id for m in await hooked.list_models()] == ["m1"]
    assert HookBackend.seen == {"secrets": resolver, "environ": environ}
    assert registries.backends.list()[0].source == "test"  # 출처는 그대로
    warnings = " ".join(r.getMessage() for r in caplog.records)
    assert "plain" in warnings  # 훅 없음 → 설정 무시 경고
    assert "missing" in warnings  # 등록 안 됨 → 경고

    with pytest.raises(BackendOptionsError, match=r"backends\.hooked"):
        configure_backends(
            _registries(), {"hooked": {"bad": True}}, secrets=resolver, environ=environ
        )
