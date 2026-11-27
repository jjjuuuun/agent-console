"""서비스 문구의 원문 틀 + 값(I.7f, design §I18N.13 I-15·I-16).

연결 테스트 시간 초과·로그인 만료·로그아웃 시간 초과 응답의 ``text_templates``: 각 포인터의
틀을 채워 이은 값 == 칸 값, 설치자가 바꾼 문구도 그 틀로, 가림 대상 값은 params에서도 가려진다.
드라이버 ``LoginProgress.text_templates``는 칸 값과 맞는 것만 응답에 실린다.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any, cast

from agent_console_contracts import (
    BackendCapabilities,
    BackendDescriptor,
    BackendLoginSession,
    BackendLogoutResult,
    BackendProbeResult,
    TextTemplate,
    render_text_parts,
)
from agent_console_runtime import (
    REDACTED,
    BackendCheckContext,
    BackendLoginContext,
    BackendLoginService,
    BackendReadinessService,
    ExecutionBackend,
    LoginProgress,
    LoginTexts,
    ReadinessTexts,
    compact_number,
    matching_text_templates,
)
from agent_console_runtime.testing_login import LoginBackendStub

NOW = 1_700_000_000.0


class Clock:
    def __init__(self) -> None:
        self.mono = 100.0

    def monotonic(self) -> float:
        return self.mono


def assert_consistent(response: Any) -> None:
    """모든 포인터: 틀을 채워 공백 하나로 이은 값 == 칸 값."""
    dumped = response.model_dump(mode="json")
    assert response.text_templates
    for pointer, parts in response.text_templates.items():
        node: Any = dumped
        for key in pointer[1:].split("/"):
            node = node[int(key)] if isinstance(node, list) else node[key]
        assert " ".join(render_text_parts([p]) for p in parts) == node, pointer


async def until(cond: Any, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not cond():
        if loop.time() > end:
            raise AssertionError("조건을 기다리다 시간 초과")
        await asyncio.sleep(0.01)


# ---------------------------------------------------------------- 연결 테스트 시간 초과


class SlowProbe:
    def __init__(self, backend_id: str) -> None:
        self.descriptor = BackendDescriptor(
            id=backend_id, title="Slow", capabilities=BackendCapabilities(probe=True)
        )

    async def run(self, *_args: Any, **_kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def probe(self, ctx: BackendCheckContext, timeout_s: float) -> BackendProbeResult:
        await asyncio.sleep(10)
        raise AssertionError  # pragma: no cover


def readiness_service(*backends: Any, **kwargs: Any) -> BackendReadinessService:
    table = {b.descriptor.id: b for b in backends}
    return BackendReadinessService(
        lambda: cast(Mapping[str, ExecutionBackend], table), clock=lambda: NOW, **kwargs
    )


async def test_probe_timeout_message_has_template() -> None:
    service = readiness_service(SlowProbe("a"), probe_timeout_max_s=0.05)
    result = await service.probe("a")
    assert result.reason == "timeout"
    assert result.message == "0.05초 안에 응답이 없었습니다."
    assert result.text_templates == {
        "/message": [
            TextTemplate(template="{seconds}초 안에 응답이 없었습니다.", params={"seconds": 0.05})
        ]
    }
    assert_consistent(result)


async def test_probe_timeout_uses_installer_text() -> None:
    texts = ReadinessTexts(probe_timeout="No answer in {seconds:g}s")
    service = readiness_service(SlowProbe("a"), probe_timeout_max_s=0.05, texts=texts)
    result = await service.probe("a")
    assert result.message == "No answer in 0.05s"
    assert result.text_templates["/message"][0].template == "No answer in {seconds:g}s"
    assert_consistent(result)


async def test_backend_templates_that_do_not_match_are_dropped() -> None:
    class Fixed(SlowProbe):
        async def probe(self, ctx: BackendCheckContext, timeout_s: float) -> BackendProbeResult:
            good = [TextTemplate(template="키 {name} 확인", params={"name": "sk-live-999"})]
            wrong = [TextTemplate(template="다른 문장")]
            return BackendProbeResult(
                backend_id="x",
                ok=False,
                message="키 sk-live-999 확인",
                details={"note": "n"},
                finished_at=1.0,
                text_templates={"/message": good, "/details/note": wrong, "/missing": good},
            )

    def redact(value: Any) -> Any:
        return json.loads(json.dumps(value).replace("sk-live-999", REDACTED))

    result = await readiness_service(Fixed("a"), redact=redact).probe("a")
    assert list(result.text_templates) == ["/message"]
    assert result.message == f"키 {REDACTED} 확인"
    assert result.text_templates["/message"][0].params == {"name": REDACTED}
    assert_consistent(result)


# ---------------------------------------------------------------- 로그인 만료·로그아웃 시간 초과


def login_service(*backends: Any, clock: Clock, **kwargs: Any) -> BackendLoginService:
    table = {b.descriptor.id: b for b in backends}
    options: dict[str, Any] = {
        "clock": lambda: NOW,
        "monotonic": clock.monotonic,
        "tick_s": 0.01,
        "id_factory": iter(f"s{i}" for i in range(100)).__next__,
    }
    options.update(kwargs)
    return BackendLoginService(lambda: cast(Mapping[str, ExecutionBackend], table), **options)


async def expire(service: BackendLoginService, clk: Clock, timeout_s: float) -> BackendLoginSession:
    session = await service.start("a", timeout_s=timeout_s)
    clk.mono += timeout_s + 1
    await until(lambda: service.get(session.session_id).phase == "expired")
    return service.get(session.session_id)


async def test_login_expired_message_has_template() -> None:
    clk = Clock()
    service = login_service(LoginBackendStub("a"), clock=clk, heartbeat_s=10_000)
    expired = await expire(service, clk, 300)
    assert expired.message.startswith("시간(5분) 안에")
    assert expired.text_templates["/message"][0].params == {"minutes": 5.0}
    assert_consistent(expired)


async def test_login_expired_keeps_g_output_for_fractions() -> None:
    clk = Clock()
    service = login_service(LoginBackendStub("a"), clock=clk, heartbeat_s=10_000)
    expired = await expire(service, clk, 100)
    old = f"시간({100 / 60:g}분)"
    assert expired.message.startswith(old)
    assert expired.text_templates["/message"][0].params == {"minutes": compact_number(100 / 60)}
    assert_consistent(expired)


async def test_login_expired_uses_installer_text() -> None:
    clk = Clock()
    texts = LoginTexts(expired="Stopped after {minutes} min")
    service = login_service(LoginBackendStub("a"), clock=clk, heartbeat_s=10_000, texts=texts)
    expired = await expire(service, clk, 120)
    assert expired.message == "Stopped after 2 min"
    assert expired.text_templates["/message"][0].template == "Stopped after {minutes} min"


async def test_driver_warning_templates_survive_stop_and_mask() -> None:
    clk = Clock()
    backend = LoginBackendStub("a")
    service = login_service(
        backend,
        clock=clk,
        heartbeat_s=10_000,
        redact=lambda v: json.loads(json.dumps(v).replace("TOPSECRETVALUE", REDACTED)),
    )
    session = await service.start("a", timeout_s=300)
    warn = TextTemplate(
        template="서버 환경에 {name}이(가) 있습니다.", params={"name": "TOPSECRETVALUE"}
    )
    stale = TextTemplate(template="다른 문장")
    backend.drivers[0].update(
        warnings=[render_text_parts([warn]), "고정 주의"],
        text_templates={"/warnings/0": [warn], "/warnings/1": [stale], "/message": [stale]},
    )
    view = service.get(session.session_id)
    assert set(view.text_templates) == {"/warnings/0"}  # 맞지 않는 틀은 빠진다
    assert view.text_templates["/warnings/0"][0].params == {"name": REDACTED}
    assert_consistent(view)
    clk.mono += 301
    await until(lambda: service.get(session.session_id).phase == "expired")
    expired = service.get(session.session_id)
    assert set(expired.text_templates) == {"/warnings/0", "/message"}
    assert_consistent(expired)


async def test_logout_timeout_message_has_template() -> None:
    class Slow(LoginBackendStub):
        async def logout(
            self, ctx: BackendLoginContext, method_id: str | None
        ) -> BackendLogoutResult:
            await asyncio.sleep(10)
            raise AssertionError  # pragma: no cover

    service = login_service(Slow("a"), clock=Clock(), logout_timeout_s=0.05)
    result = await service.logout("a")
    assert result.message == "로그아웃이 0.05초 안에 끝나지 않았습니다."
    assert (
        result.text_templates["/message"][0].template
        == "로그아웃이 {seconds}초 안에 끝나지 않았습니다."
    )
    assert_consistent(result)


def test_progress_default_has_no_templates() -> None:
    assert LoginProgress(phase="starting").text_templates == {}


def test_matching_text_templates_checks_values() -> None:
    t = TextTemplate(template="{n}개", params={"n": 2})
    doc = {"message": "2개", "warnings": ["2개", "3개"], "n": 2}
    found = matching_text_templates(
        doc,
        {
            "/message": [t],
            "/warnings/0": [t],
            "/warnings/1": [t],
            "/warnings/9": [t],
            "/n": [t],
            "bad": [t],
            "/message/x": [t],
        },
    )
    assert set(found) == {"/message", "/warnings/0"}
    assert matching_text_templates(
        {"a~b": {"c/d": "x"}}, {"/a~0b/c~1d": [TextTemplate(template="x")]}
    )
