"""QA 3R.13: 비밀 해석 경로 변경 후에도 env_prefix가 적용되고 값이 노출되지 않는다."""

from __future__ import annotations

import json
from pathlib import Path

from agent_console_server.testing import (
    API,
    SECRET_NAME,
    SECRET_VALUE,
    agent_doc,
    make_settings,
    server,
    team_graph,
    wait_run,
)


def test_env_prefix_reaches_runs_and_value_is_redacted(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, secrets={"env_prefix": "AC_"})
    with server(settings, environ={f"AC_{SECRET_NAME}": SECRET_VALUE}) as client:
        client.post(f"{API}/agents", json=agent_doc("fast", f"secret://{SECRET_NAME}"))
        client.post(f"{API}/agents", json=agent_doc("slow", f"키 secret://{SECRET_NAME}"))
        client.post(f"{API}/graphs", json=team_graph())
        run = client.post(f"{API}/runs", json={"graph_id": "flow", "input": {"request": "? 키"}})
        snap = wait_run(client, run.json()["id"])
        text = json.dumps(snap, ensure_ascii=False)
        assert SECRET_VALUE not in text
        assert "[REDACTED]" in text  # 접두가 적용돼 해석됐고 가려졌다
        for path in ("/server-info", "/runs", "/modules", "/bootstrap"):
            assert SECRET_VALUE not in client.get(f"{API}{path}").text


def test_allow_subscription_auth_reaches_backend_via_old_and_new_keys(tmp_path: Path) -> None:
    """3R.29: 옛 `backends`와 새 `mod-runs.backends` 둘 다 훅으로 전달된다."""
    from agent_console_mod_runs import RUNS_STARTER

    old = make_settings(
        tmp_path,
        options={"mod-runs": {"backends": {"claude-agent-sdk": {"allow_subscription_auth": True}}}},
    )
    new = make_settings(
        tmp_path,
        modules={
            "options": {
                "mod-runs": {"backends": {"claude-agent-sdk": {"allow_subscription_auth": True}}}
            }
        },
    )
    for settings in (old, new):
        with server(settings) as client:
            starter = client.app.state.assembly.port(RUNS_STARTER)  # type: ignore[attr-defined]
            backend = starter.registries.backends.get("claude-agent-sdk")
            assert backend._allow_subscription_auth is True
