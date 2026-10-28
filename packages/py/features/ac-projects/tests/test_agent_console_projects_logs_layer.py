"""로그 묶음 제안과 프로젝트 층 값 (design §UX-P.1·§UX-P.3, 수용 기준 R15.3·R15.4·R8.2)."""

from __future__ import annotations

from agent_console_contracts import AgentSettings, LogProjectRef, LogSessionSummary, Project
from agent_console_projects import (
    log_paths_from_sessions,
    normalize_path,
    project_layer_value,
    suggest_log_projects,
)

# ---------------------------------------------------------------- 로그 묶음 제안


def test_normalize_path() -> None:
    assert normalize_path("C:\\Work\\App\\") == "c:/work/app"
    assert normalize_path("/home/Me/app//") == "/home/Me/app"
    assert normalize_path("/") == "/"


def test_suggest_matches_same_or_sub_path_and_skips_linked() -> None:
    # 0.11.0: Project 모델에는 log_projects가 없다(읽고 버림). 옛 dict 형식으로 제안 규칙만 본다.
    project = {"working_directory": "/w/app", "log_projects": ["linked"]}
    groups = {
        "linked": ["/w/app"],
        "app-main": ["/w/app"],
        "app-sub": ["/w/app/packages/x"],
        "apple": ["/w/apple"],  # 앞부분만 같은 다른 폴더는 아니다
        "/w/app": [],  # 묶음 밖 정책 cwd: id가 곧 경로
    }
    assert suggest_log_projects(project, groups) == ["app-main", "app-sub", "/w/app"]


def test_suggest_windows_paths_case_insensitive() -> None:
    project = {"working_directory": "C:\\Users\\me\\App"}
    assert suggest_log_projects(project, {"g": ["c:/users/me/app/src"]}) == ["g"]


def test_suggest_without_working_directory_uses_fallback_or_nothing() -> None:
    project = Project(id="app", name="App", folder=None)
    groups = {"g": ["/srv/app"]}
    assert suggest_log_projects(project, groups) == []
    assert suggest_log_projects(project, groups, working_directory="/srv/app") == ["g"]


def test_log_paths_from_sessions() -> None:
    sessions = [
        LogSessionSummary(
            session="s1", cwd="/w/app/x", repo_root="/w/app", project=LogProjectRef(id="g1")
        ),
        LogSessionSummary(session="s2", cwd="/w/app/x", project=LogProjectRef(id="g1")),
        LogSessionSummary(session="s3", cwd="/tmp/none"),  # 묶음 없음
        {"cwd": "/w/b", "repo_root": "", "project": {"id": "g2"}},
    ]
    paths = log_paths_from_sessions(sessions)
    assert paths == {"g1": ["/w/app/x", "/w/app"], "g2": ["/w/b"]}
    assert suggest_log_projects({"working_directory": "/w/app"}, paths) == ["g1"]


# ---------------------------------------------------------------- 프로젝트 층 값


def test_layer_value_only_set_fields_plus_working_directory() -> None:
    project = Project.model_validate(
        {
            "id": "app",
            "name": "App",
            "working_directory": "/w/app",
            "settings": {"model": "m1", "working_directory": "/ignored"},
        }
    )
    assert project_layer_value(project) == {"model": "m1", "working_directory": "/w/app"}


def test_layer_value_settings_working_directory_when_field_empty() -> None:
    project = Project(
        id="app", name="App", folder=None, settings=AgentSettings(working_directory="/s")
    )
    assert project_layer_value(project) == {"working_directory": "/s"}


def test_layer_value_empty_project_is_empty_layer() -> None:
    assert project_layer_value(Project(id="app", name="App", folder=None)) == {}


def test_layer_value_from_mapping_drops_unknown_keys() -> None:
    value = project_layer_value({"settings": {"model": "m", "not_a_setting": 1}})
    assert value == {"model": "m"}


def test_layer_value_mapping_is_copied() -> None:
    raw = {"settings": {"tools": ["a"]}}
    value = project_layer_value(raw)
    value["tools"].append("b")
    assert raw["settings"]["tools"] == ["a"]
