# 변경 기록

## 미출시

- 5.2R.31: 목록 `ResourceSummary.project`를 채운다(요약 `extra.project`, 공용 = null).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- `apps/server`의 리소스 CRUD·본문·여러 파일·`/resource-types`·`/merge-strategies`를 옮겼다(3R.12). 제공 포트 `resources.lookup`·`resources.types`, 선택 포트 `definitions.usages`(목록 `usage_count`, 없으면 null).
- 5R.19: 예약 이름 경고 이슈에 위치 `path`(JSON Pointer `/files/<파일 경로>`)를 채우고 메시지에 파일 경로를 넣는다(4R.19 QA — 저장 경고 배너에 경로가 비던 문제).
