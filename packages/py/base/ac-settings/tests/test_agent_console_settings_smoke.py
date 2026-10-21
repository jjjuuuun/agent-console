import importlib


def test_agent_console_settings_imports_standalone() -> None:
    module = importlib.import_module("agent_console_settings")
    assert module.__name__ == "agent_console_settings"
    for name in module.__all__:
        assert hasattr(module, name), name
