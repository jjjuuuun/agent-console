import importlib


def test_agent_console_backend_claude_sdk_imports_standalone() -> None:
    module = importlib.import_module("agent_console_backend_claude_sdk")
    assert module.__name__ == "agent_console_backend_claude_sdk"
