# 변경 기록

## 0.1.0

- 3R.14: 실행 연결을 선택 인자로 — `ChatService(conversations, graphs, *, launcher=None, runs=None, events=None, interactions=None, ...)`. **생성자 인자 순서가 바뀌었다**(키워드 전용). 실행기가 없으면 전송·이어 가기는 `ChatFeatureUnavailableError`(`feature_unavailable`, `details.dependency`), 대화·대기열은 동작하고 대기열은 실행기가 생길 때까지 꺼내지 않는다. 늦은 연결 `connect(...)`, `can_send`. 상수 `LAUNCHER_DEPENDENCY`·`RUNS_DEPENDENCY`.

- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.
