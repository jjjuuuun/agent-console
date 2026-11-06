# 변경 기록

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- 5.7R.13: 공유 메모리 서버 모듈. REST `/memory/*`(범위 종류·범위·태그·항목 CRUD·버전·정리·설정 검사·내보내기/가져오기), WS 토픽 `memory.changed`, 사용자 설정 섹션 `memory`(깨진 부분만 빼고 읽기), 계보 `memory`(`memory_0001`), 저장 위치(호스트 DB 파일 / `store_path` / 메모리 + 경고), 정리 스케줄, 포트 `memory.service`, X29 호스트 플러그인 로더, 설치자 한도 옵션, 단독 실행.
- 5.7R.33z(design §PI.4.3): 선택 포트 `memory.spaces`(공간 이름 → 저장소 + 맥락 바꾸기), REST `?project=<id>`(항목·범위·태그·버전·정리·내보내기/가져오기·범위 종류, 제공자 없음 409 `feature_unavailable`, 모르는 공간 404 `project.not_found`, 제공자 예외 `code` 그대로), `POST /memory/copy`(`MemoryCopyRequest` → `MemoryCopyResult`, 같은 공간 400). `MemoryService.space(name)`·`copy`·`context_overrides`·`effective_context`, `MemorySpaceServices`, 오류 `MemorySpaceError`·`MemorySpacesUnavailable`·`UnknownMemorySpace`. 계보 `memory`의 범위에 `memory`(`MEMORY_DB_SCOPE`)를 더함 — 프로젝트 메모리 DB를 여는 연동이 찾는다. `build_router(service)`는 그대로(공간은 서비스의 `space`).
