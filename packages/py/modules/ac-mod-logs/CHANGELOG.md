# 변경 기록

## 미출시

- 5.7R.13(5.7R.6 후속): `POST /logs/index/purge` 본문 `all` — 범위 없이 실제로 지우려면 `all: true`가 필요(없으면 422). 비우기를 지원하지 않는 색인은 400 `logs.purge_unsupported`(`LogPurgeUnsupportedError`).
- 5.2R.106 후속: 설치자 옵션 `base_taxonomy_file`(기본 분류 체계 교체, `false`·빈 문자열 = 끄기)과 `base_taxonomy_of`. 모듈이 `LogsService(base_taxonomy=)`에 넘긴다.
- 5.2R.27: 선택 multi 포트 `logs.source_defaults`(설정에 `enabled`가 없는 출처의 기본값, 설정 파일 무변경), `apply_source_defaults`·`collect_source_defaults`.

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- 4R.5: 저장 계층(`storage`: 계보 `logs`, `open_log_storage`).
- 4R.10: 모듈 서술자(제공 `logs.query`·`logs.ingest`·`server.warnings`, 선택 `logs.sources`·
  `workspace.settings`·`secrets.rules`, web_roles `logs`, 계보 `logs`)와 entry point
  (`agent_console.server_modules` `mod-logs`, `agent_console.host_plugin_loaders` `logs`) 등록.
  `LogsService`(배경·수동 수집, 수집 예약, 보존 정리, 질의), REST `/logs…` 12개 경로, WS `logs`·토픽
  `logs.ingested`, 비밀 의심 가리기 주입, 출처 실패 경고, 대시보드 템플릿(패키지 데이터 2개),
  설치자 옵션(`LogsModuleSettings`), 단독 실행(`standalone.main`, `--with` 없이 `local-settings`).
- 4R.14: `GET /logs/archive?<LogFilter>&format=json|html&tz=`(첨부, `Content-Disposition`), `LogsService.archive`,
  설치자 옵션 `archive_max_events`·`archive_max_bytes`·`archive_file_prefix`·`archive_title`.
- 5R.19: 설치자 옵션 `session_title_rules`(null = ac-logs 기본 데이터).
- 5.7R.6(M-3): `POST /logs/index/purge`(본문 `LogPurgeRequest`, 응답 `LogPurgeResponse` — 모듈 안 모델, dry_run 기본 true), `LogsService.purge`(수집 잠금 안에서 `purge_index`).
