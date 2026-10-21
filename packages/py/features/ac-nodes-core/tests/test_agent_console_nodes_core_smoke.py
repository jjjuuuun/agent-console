import importlib


def test_agent_console_nodes_core_imports_standalone() -> None:
    module = importlib.import_module("agent_console_nodes_core")
    assert module.__name__ == "agent_console_nodes_core"
