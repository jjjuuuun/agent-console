# 변경 기록

## 미출시

- I.7d: Message catalogs `locales/en.json` and `locales/ko.json` registered as entry point `agent_console.message_catalogs` `ac-resources-core`, so the web can show the built-in resource types and the `resource.unsafe_path` issue in English (data only, no API change).

## 0.1.0

- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.
