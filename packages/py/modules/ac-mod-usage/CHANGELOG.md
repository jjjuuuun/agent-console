# 변경 기록

## 미출시

- 5.2R.22: `resolve_command`가 `PATH`에서 못 찾으면 서버를 실행한 파이썬 폴더(`extra_dirs`)에서 찾고, 경로로 준 값도 절대 경로로 바꾼다(조각을 그대로 붙여 넣어 동작하게).
- 5.2R.27: 연결 안내 조각의 `{agent_console_cmd}`를 채움(옵션 `agent_console_command`, `resolve_command`). 적지 않은 출처의 자동 켜기는 `agent_console_usage.auto_enabled`.
- 4R.13 후속: `definitions.checks` 제공(`UsageSettingsCheck` — 공통 설정 저장 전 출처 설정을 출처 `config_schema`로 검증, error면 422), `server.warnings`에 저장된 설정 오류 `usage.source_config_invalid` 추가.

- 4R.18: 옛 최상위 `usage` 읽기 호환 제거(`settings.removed_key` 오류로 새 위치 안내).

## 0.1.0

- 3R.11: 관측값 저장소를 모듈로 이동(`storage/`, 계보 `usage`). 선택 포트 `usage.observations` 삭제(호스트 DB 핸들 `BaseServices.database`를 쓴다). 단독 실행은 상태 폴더 SQLite를 쓴다. 의존 `agent-console-store`·`sqlalchemy` 추가.

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- `apps/server`의 `/usage`·`/usage/sources`와 사용량 서비스 조립·관측값 정리를 옮겼다(3R.10). `GET /usage?parts=`(E-14·D11): `windows`만 요청하면 실행 기록을 읽지 않는다. 설정 `modules.options.mod-usage`(옛 `usage.*`).
