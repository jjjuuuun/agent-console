# 변경 기록

## 미출시

- 5.7R.33x: 선택 포트 `definitions.spaces`. 모든 버전 경로가 `?project=<공간>`을 받아 그 공간 저장소의 버전 기록(목록·하나·비교·본문 파일·되돌리기)을 쓴다. 포트가 없으면 409 `feature_unavailable`, 모르는 공간 404 `project.not_found`. `definitions.saved` 항목에 `space`가 있으면 그 공간에 보존 개수를 적용한다(`VersionService(spaces=)`). **깨는 변경**: `build_router(service, …)`의 `service`가 공간 이름 하나를 받는다.
- 4R.18: 옛 최상위 `versions` 읽기 호환 제거(`settings.removed_key` 오류로 새 위치 안내).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- `apps/server`의 버전 경로(목록·비교·되돌리기)를 옮겼다(3R.10). 컬렉션 표는 설정 데이터(`collections`). `max_per_definition` 연결(D3·E-16): 저장 알림 `definitions.saved`마다·시작 때 보존 개수 적용. 설정 `modules.options.mod-versions`(옛 `versions.*`).
