# 변경 기록

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- 5.7R.13: 공유 메모리 서버 모듈. REST `/memory/*`(범위 종류·범위·태그·항목 CRUD·버전·정리·설정 검사·내보내기/가져오기), WS 토픽 `memory.changed`, 사용자 설정 섹션 `memory`(깨진 부분만 빼고 읽기), 계보 `memory`(`memory_0001`), 저장 위치(호스트 DB 파일 / `store_path` / 메모리 + 경고), 정리 스케줄, 포트 `memory.service`, X29 호스트 플러그인 로더, 설치자 한도 옵션, 단독 실행.
