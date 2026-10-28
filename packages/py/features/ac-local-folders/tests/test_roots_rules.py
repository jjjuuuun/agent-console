"""`default_roots`·규칙 데이터 테스트."""

from __future__ import annotations

import pytest

from agent_console_local_folders import (
    MemoryFileSystem,
    default_roots,
    load_browse_defaults,
)


def test_posix_roots_home_and_root_only() -> None:
    fs = MemoryFileSystem().add_dir("/home/me").add_dir("/media/usb").add_dir("/srv/x")
    roots = default_roots({"HOME": "/home/me"}, fs=fs)
    # 기본 규칙은 OS 공통 위치만(홈·루트·macOS /Volumes)
    assert [(r.kind, r.path, r.label) for r in roots] == [
        ("home", "/home/me", "~"),
        ("root", "/", "/"),
    ]


def test_missing_home_and_mac_volumes() -> None:
    fs = MemoryFileSystem().add_dir("/Volumes/Data").add_dir("/Volumes/.hidden")
    roots = default_roots({"HOME": "/Users/nobody"}, fs=fs)
    assert [(r.kind, r.path) for r in roots] == [("root", "/"), ("mount", "/Volumes/Data")]
    assert default_roots({}, fs=MemoryFileSystem())[0].kind == "root"


def test_windows_drives() -> None:
    fs = MemoryFileSystem("windows").add_dir("C:\\Users\\me").add_dir("E:\\")
    roots = default_roots({"USERPROFILE": "C:\\Users\\me"}, fs=fs)
    assert [(r.kind, r.path, r.label) for r in roots] == [
        ("home", "C:\\Users\\me", "~"),
        ("drive", "C:\\", "C:"),
        ("drive", "E:\\", "E:"),
    ]


def test_custom_roots_data_and_dedupe() -> None:
    defaults = load_browse_defaults(
        {
            "roots": {
                "posix": [
                    {"kind": "work", "path": "/srv/work", "label": "작업 {path}"},
                    {"kind": "dup", "path": "/srv/work/"},
                ]
            }
        }
    )
    fs = MemoryFileSystem().add_dir("/srv/work")
    roots = default_roots({}, fs=fs, defaults=defaults)
    assert [(r.kind, r.label) for r in roots] == [("work", "작업 /srv/work")]


@pytest.mark.parametrize(
    "data",
    [
        {"roots": []},
        {"roots": {"posix": [{"kind": "x"}]}},
        {"roots": {"posix": [{"kind": "x", "path": "/", "parent": "/"}]}},
        {"roots": {"bsd": []}},
        {"hidden_names": "x"},
    ],
)
def test_bad_browse_data(data: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="browse_defaults"):
        load_browse_defaults(data)


def test_package_data_loads() -> None:
    defaults = load_browse_defaults()
    assert set(defaults.roots) == {"posix", "windows"}
    assert defaults.hidden_names == frozenset()
    assert [r.kind for r in defaults.roots["posix"]] == ["home", "root", "mount"]
