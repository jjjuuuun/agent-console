"""5.2R.106 후속: 설치자 옵션 ``base_taxonomy_file``(기본 분류 체계 교체·끄기, R0.1(3))."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_console_logs import load_default_taxonomy
from agent_console_mod_logs import LogsModuleSettings, base_taxonomy_of

from .test_agent_console_mod_logs_module import (  # type: ignore[import-not-found]
    _assembly,
    _service,
)


def test_option_values() -> None:
    assert LogsModuleSettings().base_taxonomy_file is None
    off = LogsModuleSettings.model_validate({"base_taxonomy_file": False})
    assert off.base_taxonomy_file is False
    for blank in ("", "  "):
        cfg = LogsModuleSettings.model_validate({"base_taxonomy_file": blank})
        assert cfg.base_taxonomy_file is False
    cfg = LogsModuleSettings.model_validate({"base_taxonomy_file": "a/b.yaml"})
    assert cfg.base_taxonomy_file == Path("a/b.yaml")
    with pytest.raises(ValidationError):
        LogsModuleSettings.model_validate({"base_taxonomy_file": True})


def test_base_taxonomy_of(tmp_path: Path) -> None:
    assert base_taxonomy_of(None, tmp_path) is None  # 패키지 기본(LogsService가 읽는다)
    off = base_taxonomy_of(False, tmp_path)
    assert off is not None
    assert off.categories == {}
    (tmp_path / "t.yaml").write_text("categories: {x: {label: X}}", encoding="utf-8")
    mine = base_taxonomy_of(Path("t.yaml"), tmp_path)  # 상대 경로 = 설정 폴더 기준
    assert mine is not None
    assert list(mine.categories) == ["x"]
    missing = base_taxonomy_of(tmp_path / "none.yaml", None)
    assert missing is not None
    assert missing.categories == {}


def test_default_keeps_package_taxonomy(tmp_path: Path) -> None:
    ctx = _service(_assembly(tmp_path)).query_context()
    assert "meta" in ctx.hidden_categories
    assert set(_service(_assembly(tmp_path / "b")).taxonomy().categories) == set(
        load_default_taxonomy().categories
    )


def test_off_drops_defaults_and_file_replaces(tmp_path: Path) -> None:
    off = _service(_assembly(tmp_path / "off", options={"base_taxonomy_file": False}))
    assert off.query_context().hidden_categories == frozenset()
    (tmp_path / "mine.yaml").write_text(
        "categories: {mine: {label: 내것, visible: false}}", encoding="utf-8"
    )
    mine = _service(_assembly(tmp_path, options={"base_taxonomy_file": "mine.yaml"}))
    assert mine.query_context().hidden_categories == frozenset({"mine"})
