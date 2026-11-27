"""``plugins.disabled``에 entry point 이름이 아닌 이름(배포 이름·서버 모듈 id)을 적었을 때의 안내.

설치 경로와 같은 방식(dist-info + ``entry_points.txt``)으로 만든 배포의 entry point를 주입한다
(``EntryPoint.dist``가 채워진다). 실제 설치된 패키지에 의존하지 않는다.
"""

from __future__ import annotations

import importlib
import sys
import textwrap
import uuid
from collections.abc import Iterator
from importlib.metadata import EntryPoint, PathDistribution
from pathlib import Path
from types import ModuleType

import pytest

from agent_console_modkit import (
    HOST_PLUGIN_LOADERS_GROUP,
    MODULES_GROUP,
    SettingsNoticeCodes,
    load_host_plugins,
)

PLUGIN_GROUP = "test.operators"

LOADER_SOURCE = textwrap.dedent(
    """
    from agent_console_registry import load_entry_points

    EPS = []

    def loader(ctx):
        group = "test.operators"
        registry = ctx.registries.extension(group)
        eps = [ep for ep in EPS if ep.group == group]
        return [
            (group, r)
            for r in load_entry_points(group, registry, enabled=ctx.enabled, entry_points=eps)
        ]
    """
)


@pytest.fixture
def loader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """``EPS``의 ``test.operators`` entry point를 ``ctx.enabled``로 읽는 로더 모듈."""
    name = f"acmk_hint_loader_{uuid.uuid4().hex}"
    (tmp_path / f"{name}.py").write_text(LOADER_SOURCE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    module = importlib.import_module(name)
    yield module
    sys.modules.pop(name, None)


def _dist(root: Path, name: str, entry_points: str) -> list[EntryPoint]:
    """``name`` 배포(dist-info)를 만들고 그 entry point(``dist`` 붙음)를 돌려준다."""
    folder = root / f"{name.replace('-', '_')}-0.1.0.dist-info"
    folder.mkdir(parents=True)
    (folder / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.1.0\n", encoding="utf-8"
    )
    (folder / "entry_points.txt").write_text(textwrap.dedent(entry_points), encoding="utf-8")
    eps = list(PathDistribution(folder).entry_points)
    assert all(ep.dist is not None for ep in eps)
    return eps


def _load(loader: ModuleType, eps: list[EntryPoint], disabled: list[str]) -> list[str]:
    loader.EPS = eps  # type: ignore[attr-defined]
    loader_ep = EntryPoint("hint", f"{loader.__name__}:loader", HOST_PLUGIN_LOADERS_GROUP)
    plugins = load_host_plugins(entry_points=[loader_ep, *eps], disabled=disabled)
    # 안내는 경고일 뿐이다: 적힌 이름이 틀렸으니 플러그인은 그대로 읽힌다.
    assert all(r.status == "loaded" for _, r in plugins.reports), plugins.reports
    return plugins.warnings


def _ops(tmp_path: Path) -> list[EntryPoint]:
    """플러그인 두 개 + 서버 모듈 하나를 담은 배포 ``my-console-ops``."""
    return _dist(
        tmp_path / "site",
        "my-console-ops",
        f"""
        [{PLUGIN_GROUP}]
        mine.max_chars = builtins:len
        mine.min_chars = builtins:abs

        [{MODULES_GROUP}]
        mod-mine = builtins:len
        """,
    )


def test_distribution_name_suggests_its_entry_point_names(
    loader: ModuleType, tmp_path: Path
) -> None:
    [warning] = _load(loader, _ops(tmp_path), ["my-console-ops"])
    assert "'my-console-ops'" in warning
    assert "설치된 플러그인 이름이 아닙니다(무시함)" in warning
    assert "배포 이름" in warning
    assert "이 배포의 entry point 이름: mine.max_chars, mine.min_chars" in warning
    assert "mod-mine" not in warning  # 서버 모듈은 plugins.disabled가 받는 이름이 아니다


def test_distribution_name_is_matched_after_normalizing(loader: ModuleType, tmp_path: Path) -> None:
    [warning] = _load(loader, _ops(tmp_path), ["My_Console.Ops"])
    assert "배포 이름" in warning
    assert "mine.max_chars" in warning


def test_module_id_points_to_modules_disabled_and_same_distribution(
    loader: ModuleType, tmp_path: Path
) -> None:
    [warning] = _load(loader, _ops(tmp_path), ["mod-mine"])
    assert "서버 모듈 id" in warning
    assert "modules.disabled" in warning
    assert "--disable-module" in warning
    assert "이 배포의 entry point 이름: mine.max_chars, mine.min_chars" in warning


def test_module_only_distribution_says_nothing_to_disable(
    loader: ModuleType, tmp_path: Path
) -> None:
    eps = _dist(
        tmp_path / "site",
        "only-module",
        f"""
        [{MODULES_GROUP}]
        mod-only = builtins:len
        """,
    )
    [by_dist, by_module] = _load(loader, eps, ["mod-only", "only-module"])
    assert "서버 모듈 id" in by_dist  # 경고는 이름 순(mod-only → only-module)
    assert "plugins.disabled로 끌 수 있는 entry point가 없습니다" in by_dist
    assert "배포 이름" in by_module
    assert "plugins.disabled로 끌 수 있는 entry point가 없습니다" in by_module


def test_unrelated_name_keeps_plain_warning(loader: ModuleType, tmp_path: Path) -> None:
    [warning] = _load(loader, _ops(tmp_path), ["typo-name"])
    assert warning == "plugins.disabled의 'typo-name'은(는) 설치된 플러그인 이름이 아닙니다(무시함)"


def test_entry_point_name_needs_no_hint(loader: ModuleType, tmp_path: Path) -> None:
    loader.EPS = _ops(tmp_path)  # type: ignore[attr-defined]
    loader_ep = EntryPoint("hint", f"{loader.__name__}:loader", HOST_PLUGIN_LOADERS_GROUP)
    plugins = load_host_plugins(entry_points=[loader_ep, *loader.EPS], disabled=["mine.max_chars"])
    assert plugins.warnings == []
    assert [(r.key, r.status) for _, r in plugins.reports] == [
        ("mine.max_chars", "skipped"),
        ("mine.min_chars", "loaded"),
    ]


def test_notices_carry_code_and_details_for_the_web(loader: ModuleType, tmp_path: Path) -> None:
    """I.7c: 웹이 문구 묶음 ``codes``로 문구를 고르도록 경고마다 코드·``details``가 붙는다."""
    eps = [
        *_ops(tmp_path),
        *_dist(tmp_path / "site2", "only-module", f"[{MODULES_GROUP}]\nmod-only = builtins:len\n"),
    ]
    loader.EPS = eps  # type: ignore[attr-defined]
    loader_ep = EntryPoint("hint", f"{loader.__name__}:loader", HOST_PLUGIN_LOADERS_GROUP)
    names = ["my-console-ops", "mod-mine", "mod-only", "only-module", "typo-name"]
    plugins = load_host_plugins(entry_points=[loader_ep, *eps], disabled=names)
    got = {n.details["name"]: (n.code, dict(n.details)) for n in plugins.notices}
    listed = "mine.max_chars, mine.min_chars"
    codes = SettingsNoticeCodes
    assert got == {
        "my-console-ops": (
            codes.PLUGINS_DISABLED_DISTRIBUTION,
            {"name": "my-console-ops", "entry_points": listed},
        ),
        "mod-mine": (
            codes.PLUGINS_DISABLED_MODULE_ID,
            {"name": "mod-mine", "entry_points": listed},
        ),
        "mod-only": (codes.PLUGINS_DISABLED_MODULE_ID_NOTHING, {"name": "mod-only"}),
        "only-module": (codes.PLUGINS_DISABLED_DISTRIBUTION_NOTHING, {"name": "only-module"}),
        "typo-name": (codes.PLUGINS_UNKNOWN_DISABLED, {"name": "typo-name"}),
    }
    assert plugins.warnings == [n.message for n in plugins.notices]
    assert all(str(n) == n.message for n in plugins.notices)
