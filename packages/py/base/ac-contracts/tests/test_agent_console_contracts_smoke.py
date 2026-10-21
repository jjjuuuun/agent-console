import importlib


def test_agent_console_contracts_imports_standalone() -> None:
    module = importlib.import_module("agent_console_contracts")
    assert module.__name__ == "agent_console_contracts"
