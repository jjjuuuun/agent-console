"""테스트 지원 모듈 `testing`: 시험용 에이전트 정의의 백엔드는 인자이고, 기본값은 백엔드 패키지
상수다(5.5R.32 — 서버 소스에 백엔드 이름 리터럴이 없다)."""

from __future__ import annotations

from pathlib import Path

from agent_console_backend_fake_agent import FAKE_BACKEND_ID
from agent_console_server import testing


def test_agent_doc_backend_defaults_to_package_constant() -> None:
    assert testing.agent_doc("a", "hi")["backend"] == FAKE_BACKEND_ID


def test_agent_doc_backend_is_an_argument() -> None:
    doc = testing.agent_doc("a", "hi", backend="zz-engine", role="r")
    assert doc["backend"] == "zz-engine"
    assert doc["role"] == "r"


def test_testing_module_has_no_backend_name_literal() -> None:
    source = Path(testing.__file__).read_text(encoding="utf-8")
    for quote in ('"', "'"):
        assert f"{quote}{FAKE_BACKEND_ID}{quote}" not in source
