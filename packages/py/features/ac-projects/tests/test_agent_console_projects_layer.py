"""프로젝트 층 값(design §UX-P.3, 5.7R.33e: 작업 폴더 = 프로젝트 folder)."""

from __future__ import annotations

from agent_console_contracts import AgentSettings, Project
from agent_console_projects import project_layer_value


def test_layer_value_only_set_fields_plus_folder() -> None:
    project = Project.model_validate(
        {
            "id": "app",
            "name": "App",
            "working_directory": "/w/app",  # 옛 키 → folder
            "settings": {"model": "m1", "working_directory": "/ignored"},
        }
    )
    assert project_layer_value(project) == {"model": "m1", "working_directory": "/w/app"}


def test_layer_value_settings_working_directory_when_folder_empty() -> None:
    project = Project(
        id="app", name="App", folder=None, settings=AgentSettings(working_directory="/s")
    )
    assert project_layer_value(project) == {"working_directory": "/s"}


def test_layer_value_empty_project_is_empty_layer() -> None:
    assert project_layer_value(Project(id="app", name="App", folder=None)) == {}


def test_layer_value_from_mapping_reads_folder_and_legacy_key() -> None:
    assert project_layer_value({"folder": "/w/a"}) == {"working_directory": "/w/a"}
    assert project_layer_value({"working_directory": "/w/b"}) == {"working_directory": "/w/b"}


def test_layer_value_from_mapping_drops_unknown_keys() -> None:
    value = project_layer_value({"settings": {"model": "m", "not_a_setting": 1}})
    assert value == {"model": "m"}


def test_layer_value_mapping_is_copied() -> None:
    raw = {"settings": {"tools": ["a"]}}
    value = project_layer_value(raw)
    value["tools"].append("b")
    assert raw["settings"]["tools"] == ["a"]
