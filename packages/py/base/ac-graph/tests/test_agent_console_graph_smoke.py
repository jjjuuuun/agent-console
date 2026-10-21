import importlib


def test_agent_console_graph_imports_standalone() -> None:
    module = importlib.import_module("agent_console_graph")
    assert module.__name__ == "agent_console_graph"
