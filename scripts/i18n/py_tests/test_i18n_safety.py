"""저장소 설정의 안전장치: 서버 훑기가 실제 백엔드 계정·외부 호출을 하는 경로를 읽지 않는다."""

from __future__ import annotations

import fnmatch

from i18n_common import DEFAULT_CONFIG, load_config

REAL_CALL_PATHS = (
    "/api/v1/backends/{backend_id}/models",
    "/api/v1/backends/{backend_id}/model-catalog",
    "/api/v1/backends/login/current",
    "/api/v1/backends/login/{session_id}",
)


def test_real_call_paths_are_skipped() -> None:
    server = load_config(DEFAULT_CONFIG).server
    for path in REAL_CALL_PATHS:
        assert any(fnmatch.fnmatchcase(path, pattern) for pattern in server.skip_paths), path


def test_model_discovery_is_off_in_the_crawled_server() -> None:
    server = load_config(DEFAULT_CONFIG).server
    assert server.options["mod-runs"]["model_discovery"]["enabled"] is False
