import importlib


def test_agent_console_backend_fake_imports_standalone() -> None:
    module = importlib.import_module("agent_console_backend_fake_agent")
    assert module.__name__ == "agent_console_backend_fake_agent"
