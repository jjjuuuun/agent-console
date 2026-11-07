# 변경 기록

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- 7R.12: 위키 서버 모듈 — REST `/wiki/*`(위키·페이지·미리보기·옮기기·기록·되돌리기·링크 넣기·틀 렌더·
  검색·그래프·점검·변경·문법·scan·zip, 위키 규칙), WS `wiki.changed`, 정의 종류 기여(위키·위키 규칙),
  사용자 설정 섹션 `wiki`, 포트 `wiki.service`·선택 `wiki.spaces`·`records.spaces`·`wiki.write_checks`·
  `wiki.integrations`, 계보 `wiki`(app·project), X48·X50 호스트 플러그인 로더, 단독 실행.
- 계약 0.14.1 후속: `GET /wiki/info`가 `writable`(공간 `config_writable`, 단독 공간은 true)을 채운다.
- 계약 0.14.2 후속: 위키 규칙 버전 경로 `GET /wiki/rules/{id}/versions[/{hash}]`·`…/versions/{hash}/files[/{path}]`·
  `POST …/versions/{hash}/restore`(`/sdd/templates`와 같은 모양, 본문 파일 비밀 검사·읽기 전용 공간 409),
  `GET /wiki/info`가 `rules_kind`를 채운다.
