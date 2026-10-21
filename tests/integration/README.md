# 저장소 통합 테스트

여러 패키지를 묶거나 저장소의 다른 폴더(`packages/ts/lib/contracts/schema`, 루트 예시 설정)를 읽는 테스트.
패키지 폴더 안의 테스트는 자기 폴더 밖을 보지 않으므로(design §3R.2, modularity P5), 저장소 전체를 전제로 하는 검사는 여기에 둔다.

- 실행: 루트 `uv run poe test`(루트 pytest `testpaths`에 포함) 또는 `uv run pytest tests/integration`
- 타입 검사: 루트 `uv run poe typecheck`(루트 mypy `files`에 포함)
- 파일 이름은 `test_integration_*.py`(mypy가 테스트 파일을 최상위 모듈로 다루므로 이름이 겹치지 않게)

| 파일 | 검사 |
| --- | --- |
| `test_integration_presets_empty.py` | 프리셋 없이 동작: 빈 프리셋 경로 + 빈 workspace에서 정의 생성·검증·실행(서버 없이) |
| `test_integration_contracts_schema.py` | 커밋된 TS 계약 생성물이 지금 계약과 같은지 |
| `test_integration_cli_example_config.py` | 루트 `agent-console.example.yaml`로 서버가 뜨는지 |
