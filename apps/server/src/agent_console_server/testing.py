"""서버 테스트 공용 도구(공개 `testing` 하위 모듈, design §3R.2.2).

임시 workspace 설정, 앱 클라이언트, 테스트용 그래프·에이전트(fake 백엔드), WS 수신 도우미.
테스트 파일은 `from agent_console_server.testing import ...`로 쓴다.

주의: 이 모듈은 `fastapi.testclient`를 쓰므로 **`httpx`가 설치되어 있어야 import된다**. `httpx`는
서버 패키지의 런타임 의존이 아니라 개발 의존(dev 그룹)이다. 저장소 밖에서 쓰려면
`pip install agent-console-server httpx`처럼 함께 설치한다.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from agent_console_server import (
    SETTINGS_COMPAT_CONTEXT,
    ServerSettings,
    create_app,
    settings_compat,
)

API = "/api/v1"
TEST_TOKEN = "test-token-0123456789abcdef"
SECRET_NAME = "MY_API_KEY"
SECRET_VALUE = "sekret-value-zz9"
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})


def make_settings(
    tmp_path: Path, *, options: Mapping[str, Mapping[str, Any]] | None = None, **extra: Any
) -> ServerSettings:
    """임시 폴더 기준 설정. TestClient의 Host(`testserver`)를 허용한다.

    Args:
        tmp_path: `base_dir`(workspace는 그 아래 `ws`).
        options: 모듈 설정(`{모듈 id: 설정}` → `modules.options`). `modules=`의 같은 id와
            얕게 합친다.
        extra: 호스트 설정 키(`security`·`web`처럼 객체면 기본값과 얕게 합친다).

    설치된 모듈의 설정 호환 선언을 적용한다(`load_settings`와 같다 — 지운 옛 최상위 키는
    `settings.removed_key` 오류).
    """
    data: dict[str, Any] = {
        "base_dir": str(tmp_path),
        "workspace": "ws",
        "security": {"allowed_hosts": ["testserver"]},
    }
    for key, value in extra.items():
        if isinstance(value, Mapping) and isinstance(data.get(key), dict):
            data[key] = {**data[key], **value}
        else:
            data[key] = value
    if options:
        modules = dict(data.get("modules") or {})
        merged = dict(modules.get("options") or {})
        for module_id, value in options.items():
            merged[module_id] = {**merged.get(module_id, {}), **value}
        modules["options"] = merged
        data["modules"] = modules
    return ServerSettings.model_validate(data, context={SETTINGS_COMPAT_CONTEXT: settings_compat()})


def default_environ() -> dict[str, str]:
    return {SECRET_NAME: SECRET_VALUE}


@contextmanager
def server(
    settings: ServerSettings,
    *,
    environ: Mapping[str, str] | None = None,
    token: str = TEST_TOKEN,
    with_token: bool = True,
) -> Iterator[TestClient]:
    """앱을 시작(lifespan)하고 클라이언트를 돌려준다. 끝나면 종료 순서대로 정리한다."""
    env = default_environ() if environ is None else environ
    app = create_app(settings, environ=env, token=token)
    with TestClient(app) as client:
        if with_token:
            client.headers["X-Console-Token"] = token
        yield client


def agent_doc(agent_id: str, response: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": agent_id,
        "name": agent_id,
        "backend": "fake",
        "backend_options": {"default": {"response": response}},
        **extra,
    }


def _edge(
    edge_id: str,
    source: tuple[str, str],
    target: tuple[str, str],
    kind: str,
    **config: Any,
) -> dict[str, Any]:
    return {
        "id": edge_id,
        "source": {"node": source[0], "port": source[1]},
        "target": {"node": target[0], "port": target[1]},
        "kind": kind,
        "config": config,
    }


def team_graph(graph_id: str = "flow") -> dict[str, Any]:
    """사용자 → (메시지, Run 입력 `request`) 빠른(a) → (넘기기) 깊은(b) → (답변) 사용자.

    a의 결과도 중간 답변으로 나간다. 노드·연결 종류는 기본 플러그인(ac-nodes-core) 것이다.
    """
    return {
        "id": graph_id,
        "name": "테스트 흐름",
        "inputs": [{"name": "request"}],  # Run 입력 키(`input.request`)
        "nodes": [
            {"id": "you", "type": "user", "label": "나"},
            {"id": "a", "type": "agent", "label": "빠른", "config": {"agent_ref": "fast"}},
            {"id": "b", "type": "agent", "label": "깊은", "config": {"agent_ref": "slow"}},
        ],
        "edges": [
            _edge("m1", ("you", "says"), ("a", "in"), "message", input_key="request"),
            _edge("h1", ("a", "out"), ("b", "in"), "handoff"),
            _edge("r1", ("a", "out"), ("you", "hears"), "reply", label="빠른", final=False),
            _edge("r2", ("b", "out"), ("you", "hears"), "reply"),
        ],
    }


def seed(client: TestClient, graph_id: str = "flow", **slow_options: Any) -> dict[str, Any]:
    """에이전트 2개 + 그래프를 REST로 만든다. 그래프 응답(VersionedGraph)을 돌려준다."""
    fast = agent_doc("fast", "빠른 답: $prompt")
    slow = agent_doc("slow", "깊은 답: $prompt")
    slow["backend_options"].update(slow_options)
    assert client.post(f"{API}/agents", json=fast).status_code == 201
    assert client.post(f"{API}/agents", json=slow).status_code == 201
    response = client.post(f"{API}/graphs", json=team_graph(graph_id))
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def wait_run(client: TestClient, run_id: str, timeout: float = 10.0) -> dict[str, Any]:
    """Run status가 끝날 때까지 스냅샷을 조회한다. 끝난 스냅샷(RunSnapshot JSON)을 돌려준다.

    주의: 기록기는 최종 Run을 저장한 뒤 종료 이벤트(`run.completed` 등)를 저장한다.
    이 함수가 돌아온 시점의 `last_seq`에는 종료 이벤트가 아직 없을 수 있다.
    이벤트가 필요하면 WS로 종료 이벤트까지 받는다.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snap: dict[str, Any] = client.get(f"{API}/runs/{run_id}").json()
        if snap["run"]["status"] in TERMINAL:
            return snap
        time.sleep(0.02)
    raise AssertionError(f"Run {run_id}가 끝나지 않았다")


def ws_path(token: str | None = TEST_TOKEN) -> str:
    return "/ws" if token is None else f"/ws?token={token}"


def receive_until(
    ws: WebSocketTestSession,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """`predicate`가 참인 메시지까지(포함) 받은 메시지 목록. `limit`개를 넘으면 실패."""
    received: list[dict[str, Any]] = []
    for _ in range(limit):
        message: dict[str, Any] = ws.receive_json()
        received.append(message)
        if predicate(message):
            return received
    raise AssertionError(f"조건에 맞는 메시지가 {limit}개 안에 없다: {received[-5:]}")


QUESTION_PAYLOAD: dict[str, Any] = {
    "questions": [
        {
            "question": "진행할까요?",
            "options": [{"label": "예"}, {"label": "아니오"}],
            "multi_select": False,
        }
    ]
}


def asker_agent(agent_id: str = "asker", **options: Any) -> dict[str, Any]:
    """fake 백엔드: 메시지에 `묻기`가 있으면 되묻기(`question`)를 열고 답을 응답에 넣는다."""
    return agent_doc(
        agent_id,
        "에코: $prompt",
        **{
            "backend_options": {
                "rules": [
                    {
                        "contains": "묻기",
                        "ask": [
                            {
                                "kind": "question",
                                "title": "확인",
                                "payload": QUESTION_PAYLOAD,
                                "answer_path": "/response",
                            }
                        ],
                        "response": "답: $answer_1 ($answer_1_status)",
                    }
                ],
                "default": {"response": "에코: $prompt"},
                **options,
            }
        },
    )


def chat_graph(
    graph_id: str = "chat", agent_ref: str = "asker", *, ask: bool = True
) -> dict[str, Any]:
    """사용자 →(message, 기본 입력 키 text) a →(reply) 사용자, a →(ask_user) 사용자."""
    edges = [
        _edge("m1", ("you", "says"), ("a", "in"), "message"),
        _edge("r1", ("a", "out"), ("you", "hears"), "reply"),
    ]
    if ask:
        edges.append(_edge("k1", ("a", "out"), ("you", "asks"), "ask_user"))
    return {
        "id": graph_id,
        "name": "채팅 팀",
        "nodes": [
            {"id": "you", "type": "user", "label": "나"},
            {"id": "a", "type": "agent", "label": "응답자", "config": {"agent_ref": agent_ref}},
        ],
        "edges": edges,
    }


def seed_chat(client: TestClient, **options: Any) -> None:
    assert client.post(f"{API}/agents", json=asker_agent(**options)).status_code == 201
    response = client.post(f"{API}/graphs", json=chat_graph())
    assert response.status_code == 201, response.text


def wait_for(predicate: Callable[[], Any], *, timeout: float = 10.0) -> Any:
    """`predicate()`가 참 값을 돌려줄 때까지 기다린다(그 값을 돌려준다)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("조건이 시간 안에 참이 되지 않았다")


def pending_of(client: TestClient, count: int = 1) -> list[dict[str, Any]]:
    """대기 상호작용이 `count`개 이상 생길 때까지 기다린다."""

    def check() -> list[dict[str, Any]] | None:
        found: list[dict[str, Any]] = client.get(
            f"{API}/interactions", params={"status": "pending"}
        ).json()
        return found if len(found) >= count else None

    result: list[dict[str, Any]] = wait_for(check)
    return result
