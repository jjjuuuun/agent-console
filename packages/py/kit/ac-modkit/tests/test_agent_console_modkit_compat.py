"""모듈이 선언하는 호스트 설정 호환(3R.16): 옛 키 옮기기·환경변수·명령행·기본값·지운 키."""

from __future__ import annotations

import os
from dataclasses import replace

import pytest

from agent_console_modkit import (
    PATHSEP,
    EnvSetting,
    MovedSetting,
    RemovedSetting,
    SeedSetting,
    SettingsCompat,
    compat_flags,
    compat_of,
    env_settings,
    flag_settings,
    migrate_settings,
    removed_settings,
)
from agent_console_modkit.testing import ECHO_SETTINGS_COMPAT, fake_module

COMPAT = {"mod-echo": ECHO_SETTINGS_COMPAT}


def test_compat_of_reads_descriptors() -> None:
    plain = fake_module("mod-plain")
    echo = fake_module("mod-echo")
    echo.descriptor = replace(echo.descriptor, settings_compat=ECHO_SETTINGS_COMPAT)
    assert compat_of([plain, echo]) == COMPAT


def test_migrate_whole_into_and_seed() -> None:
    data = {
        "host": "127.0.0.1",
        "echo": {"a": 1, "b": 2},
        "echo_prefix": ">",
        "modules": {"options": {"mod-echo": {"b": 3}}},
    }
    out, moves = migrate_settings(data, COMPAT)
    assert "echo" not in out
    assert "echo_prefix" not in out
    expected = {"a": 1, "b": 3, "prefix": ">", "host": "127.0.0.1"}
    assert out["modules"]["options"]["mod-echo"] == expected
    assert [(m.old, m.new, m.overridden) for m in moves] == [
        ("echo", "modules.options.mod-echo", ("b",)),
        ("echo_prefix", "modules.options.mod-echo.prefix", ()),
    ]
    assert "새 위치 값이 이긴 키: b" in moves[0].message()
    assert data["echo"] == {"a": 1, "b": 2}  # 원본은 그대로


def test_wrong_shape_is_left_for_validation() -> None:
    out, moves = migrate_settings({"echo": "not-a-dict"}, COMPAT)
    assert out["echo"] == "not-a-dict"
    assert moves == []


def test_seed_before_moves_reads_original() -> None:
    compat = {
        "mod-x": SettingsCompat(
            moved=(MovedSetting("old"),),
        ),
        "mod-y": SettingsCompat(
            seeds=(SeedSetting("home", "old.home", before_moves=True),),
        ),
    }
    out, _ = migrate_settings({"old": {"home": "/h"}}, compat)
    assert out["modules"]["options"]["mod-y"] == {"home": "/h"}
    assert out["modules"]["options"]["mod-x"] == {"home": "/h"}


def test_env_settings_split() -> None:
    compat = {
        "mod-p": SettingsCompat(
            env=(
                EnvSetting("DIRS", ("dirs",), split=PATHSEP),
                EnvSetting("ONE", ("deep", "one")),
            )
        )
    }
    env = {"AC_DIRS": f"a{os.pathsep} b", "AC_ONE": "1", "AC_EMPTY": ""}
    assert env_settings(env, compat, prefix="AC_") == {
        "modules": {"options": {"mod-p": {"dirs": ["a", "b"], "deep": {"one": "1"}}}}
    }
    assert env_settings({"AC_ECHO_TAGS": "x, y"}, COMPAT, prefix="AC_") == {
        "modules": {"options": {"mod-echo": {"tags": ["x", "y"]}}}
    }


def test_flags() -> None:
    [flag] = compat_flags(COMPAT)
    assert (flag.module_id, flag.setting.flag) == ("mod-echo", "echo-tag")
    assert flag.setting.repeat
    assert flag_settings({"echo-tag": ["a"]}, COMPAT) == {
        "modules": {"options": {"mod-echo": {"tags": ["a"]}}}
    }
    assert flag_settings({"echo-tag": None}, COMPAT) == {}
    with pytest.raises(KeyError):
        flag_settings({"nope": "x"}, COMPAT)


def test_removed_settings() -> None:
    assert [r.path for r in removed_settings({"echo": {"legacy": 1}}, COMPAT)] == ["echo.legacy"]
    assert removed_settings({"echo": {}}, COMPAT) == []


def test_removed_setting_messages_point_to_new_location() -> None:
    """4R.18: 읽기 호환이 끝난 옛 키는 새 위치를 알려 주는 거부 메시지가 된다."""
    [old] = removed_settings({"echo_old": {"a": 1}}, COMPAT)
    assert old.new == "modules.options.mod-echo"
    assert old.message() == (
        "설정 키 echo_old는 더 이상 읽지 않습니다. modules.options.mod-echo로 옮기세요"
    )
    assert RemovedSetting("a.b", "이유").message() == "이유"
    assert RemovedSetting("a", "이유", new="x.y").message() == "이유. 새 위치: x.y"
    assert "지웠습니다" in RemovedSetting("a").message()
