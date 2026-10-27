"""5.2R.34: 응답 틀 변수 ``$cwd``(요청 작업 폴더, 없으면 빈 문자열) — 실행 범위(프로젝트 작업
폴더)가 실제 요청에 들어갔는지 실서버·테스트에서 보는 용도."""

from __future__ import annotations

from agent_console_backend_fake_agent import FakeBackend
from agent_console_backend_fake_agent.testing import ValidatingSink
from agent_console_contracts import Agent
from agent_console_runtime import AgentRequest, CancelToken


def _agent() -> Agent:
    options = {"default": {"response": "cwd=[$cwd]"}}
    return Agent(id="a1", name="에이전트", backend="fake-agent", backend_options=options)


async def test_cwd_template_variable() -> None:
    backend = FakeBackend(ids=lambda: "s1")
    with_cwd = await backend.run(
        AgentRequest(agent=_agent(), prompt="p", cwd="/w/app"), ValidatingSink(), CancelToken()
    )
    assert with_cwd.text == "cwd=[/w/app]"
    without = await backend.run(
        AgentRequest(agent=_agent(), prompt="p"), ValidatingSink(), CancelToken()
    )
    assert without.text == "cwd=[]"
