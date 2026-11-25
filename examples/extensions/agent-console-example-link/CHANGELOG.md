# 변경 기록

## 미출시

- REL.20: 개발 의존 범위를 `agent-console-server>=1.0,<2`로 올렸다(서버 표시 버전 1.0.0). 코드 변경 없음.

## 0.1.0

- 첫 판: 연동 모듈 `link-example-notes-runs` 예제 — 실행 범위(`runs.scopes`)로 Run마다 노트 읽기 도구 공급자(X30),
  리소스 종류 `example-notes`(칸 `example_notes`), 이벤트 `example_notes.read`(본문 없음), 테스트 대역
  `testing.static_notes_module`.
