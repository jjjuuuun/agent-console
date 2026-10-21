"""순수 도우미(설정 층·턴 조립·세션) 테스트."""

from agent_console_chat import (
    first_message_title,
    layered_chat_settings,
    message_text,
    overlay_chat_settings,
    prune_sessions,
)
from agent_console_contracts import ChatSettings, Graph, GraphSettings, Run, SessionRef


def _run(input: dict[str, object]) -> Run:
    return Run.model_validate(
        {
            "id": "r",
            "graph_id": "g",
            "graph_version": "v",
            "status": "queued",
            "input": input,
            "origin": "chat",
            "created_at": 1.0,
        }
    )


def test_overlay_only_overrides_fields_set_on_team_layer() -> None:
    common = ChatSettings(busy_policy="reject", title="manual")
    team = Graph(id="g", name="g", settings=GraphSettings(chat=ChatSettings(title="first_message")))
    merged = overlay_chat_settings(common, team)
    assert merged.busy_policy == "reject"  # 팀 층이 생략 → 상속
    assert merged.title == "first_message"
    assert overlay_chat_settings(common, None) == common
    assert overlay_chat_settings(common, Graph(id="g", name="g")) == common


def test_layered_resolver_reads_common_each_time() -> None:
    current = {"value": ChatSettings(busy_policy="queue")}
    resolve = layered_chat_settings(lambda: current["value"])
    assert resolve(None).busy_policy == "queue"
    current["value"] = ChatSettings(busy_policy="reject")
    assert resolve(None).busy_policy == "reject"
    assert layered_chat_settings()(None) == ChatSettings()


def test_message_text_and_title() -> None:
    assert message_text(_run({"text": "안녕"}), "text") == "안녕"
    assert message_text(_run({}), "text") == ""
    assert message_text(_run({"text": {"a": 1}}), "text") == '{"a": 1}'
    assert first_message_title("  a\n\n b  ", 40) == "a b"
    assert first_message_title("가나다라마바", 3) == "가나다"


def test_prune_sessions() -> None:
    ref = SessionRef(backend="b", session_id="s")
    assert prune_sessions({"a": ref, "b": ref}, ["b", "c"]) == {"b": ref}
