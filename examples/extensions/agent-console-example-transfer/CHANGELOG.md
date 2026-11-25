# 변경 기록

## 미출시

- FU.22: 통합 서버 시험이 에이전트 하나만 고른다 — 프로젝트 공간에서 내보낼 때 쓰는 리소스가 그 공간에서 함께 담긴다.
- FU.19: 한 파일 본문(카탈로그 `content`)을 항목 필드 `content`로 담고 가져올 때 `ImportItem.content`로 넘긴다(필드 이름은 옵션 데이터 `fields.content`). 설치 없이 쓰는 `register(registries)`와 통합 서버 왕복 시험(`tests/test_server.py`)을 더했다.

## 0.1.0

- 첫 판: 정의를 JSON 파일 하나로 내보내는 형식과 같은 파일에서 가져오는 출처 `example-json`(내보내기·가져오기 확장 예제) — 형식 이름·필드 이름은 옵션 데이터.
