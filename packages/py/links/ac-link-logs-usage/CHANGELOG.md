# 변경 기록

## 미출시

- 5.2R.27: 이 PC에 로그 폴더가 있는 로그 출처 기본 켜기(포트 `logs.source_defaults`, 규칙 데이터 `data/auto_log_sources.json`, `autoenable`), `local-logs` `auto_enable`·창 이름(기본값 데이터 `title`·`short_title`, `window_infos`), 첫 조회가 수집을 기다림(선택 포트 `logs.ingest`, `first_scan_wait_seconds`). 옵션 `auto_enable_log_sources`·`auto_log_sources_file`·`first_scan_wait_seconds`.

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`, 작업 4R.13): 사용량 출처 `local-logs`(`LocalLogsUsageSource`,
  신뢰 등급 `estimated`), 순수 계산 `estimate_windows`, 기본값 데이터 `data/local_logs_defaults.json`,
  `logs.ingested` 캐시 무효화, 설치자 옵션 `source_id`·`defaults_file`.
