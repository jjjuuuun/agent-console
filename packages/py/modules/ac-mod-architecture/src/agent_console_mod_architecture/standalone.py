"""단독 실행 진입점(``python -m agent_console_mod_architecture``가 부른다,
테스트에서 직접 부를 수 있다).

``--with``를 주지 않으면 ``testing.local_settings_module``(워크스페이스 ``settings.yaml``)을 붙인다.
사용자 프로필은 그 파일의 ``architecture`` 섹션에 적는다. 저장소(DB)는 쓰지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_modkit.standalone import run

from .module import module
from .testing import local_settings_module


def main(argv: Sequence[str] | None = None, **overrides: Any) -> int:
    """모듈을 단독으로 띄운다.

    Args:
        argv: 명령행 인자(``--with``·``--config``·``--host``·``--port``·``--check``).
        overrides: ``agent_console_modkit.standalone.run``에 넘길 인자(테스트 주입: ``serve``·
            ``out``·``environ``·``available`` 등).

    Returns:
        종료 코드(0 정상, 1 모듈 꺼짐·확인 실패, 2 인자·설정 오류).
    """
    options: dict[str, Any] = {
        "default_with": [local_settings_module()],
        "error_status": HTTP_STATUS_BY_ERROR_CODE,
        "prog": "python -m agent_console_mod_architecture",
    }
    options.update(overrides)
    return run(module, argv=argv, **options)


__all__ = ["main"]
