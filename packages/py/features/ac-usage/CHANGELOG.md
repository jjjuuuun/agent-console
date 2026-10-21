# 변경 기록

## 미출시

- 5.2R.27: 적지 않은 출처는 `auto_enable`이고 `test_only`가 아니면 켠다(`auto_enabled`, 이전: 전부 켬 — 외부 출처는 `auto_enable=True`로 기본 켜짐 유지). 기본 출처 데이터 `data/sources.json`(자동 켜기·창 이름·연결 안내 `setup_help`·`setup_snippets`, README 조각은 doctest로 같은 데이터). `UsageService(setup_values=)`·출처 선택 메서드 `setup_values(ctx)`·`received_at(ctx)`, `fill_setup_snippets`·`fill_setup_text`(셸·언어별 따옴표), `UsageSourceInfo.last_received_at`. `statusline-file`이 statusLine 입력 원문 파일도 읽는다(`load_statusline_windows`), `default_window_labels`.
- 5R.13: `counts_toward_usage(run)`(루트 Run만 집계), `load_usage_records`가 자식 Run을 건너뛴다.

- 4R.13 후속: 출처 설정 검증 공개 API `source_config_issues`·`config_error`·`UsageService.config_issues`, 코드 `SOURCE_CONFIG_INVALID`·`SOURCE_SCHEMA_INVALID`. `sources()`가 수집 전에도 지금 설정 오류를 보이고, 출처 스키마 자체가 잘못되면 그 출처만 실패한다(전에는 수집 전체가 예외).

## 0.1.0

- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.
