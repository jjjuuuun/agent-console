# 변경 기록

## Unreleased

- I.7c: Message catalog `locales/en.json` registered as entry point `agent_console.message_catalogs` `ac-link-logs-trace`, so the web can show the link module description and settings in English (data only, no API change).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`).
- `build_log_trace`(세션 로그 → `Trace`), `LogTraceViews`, `GET /logs/sessions/{session}/trace`, 웹 역할 `logs:trace`, 설정 `link_keys`·`max_events`(작업 4R.12).
