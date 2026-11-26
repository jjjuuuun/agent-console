# 변경 기록

## 미출시

- I.6: The `--example-notes-max` help is English (it appears in `agent-console serve --help`).
- REL.20: 개발 의존 범위를 `agent-console-server>=1.0,<2`로 올렸다(서버 표시 버전 1.0.0). 코드 변경 없음.

## 0.1.0

- 첫 판: 서버 모듈 `mod-example-notes` 예제 — REST `/example-notes`, 설치자 옵션(`x-ui`·설명)·명령행 옵션 `--example-notes-max`,
  사용자 설정 섹션 `example_notes`, 정의 종류 기여(노트 틀), 마이그레이션 계보 `example_notes`(앱·프로젝트 기록 DB),
  포트 `example_notes.reader`, `python -m agent_console_example_module` 단독 실행.
