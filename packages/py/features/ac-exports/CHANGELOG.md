# 변경 기록

## 미출시

- FU.19: `ExportCatalog.content(kind, id)` — 한 파일 본문(문서의 본문 필드가 파일 하나를 가리키는 종류)을 읽는 길. `files`는 여러 파일 본문만이다. 카탈로그를 직접 만드는 앱은 이 메서드를 더해야 한다(없는 본문은 None). `MemoryCatalog.add(content=)`·`contents`. `claude-dir`은 리소스 본문을 `files`에서 못 찾으면 `content`에서 읽는다.
- 5R.15: `claude-dir`이 쓰는 정의 중 팀 구성(중첩 팀의 자식)을 따라가 그 구성원도 내보낸다(주 노드는 고른
  팀 구성만, 순환은 한 번씩).

## 0.1.0

- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.
