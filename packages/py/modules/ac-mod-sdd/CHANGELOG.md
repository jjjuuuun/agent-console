# 변경 기록

## 0.1.0

- 처음 만듦(6R.13, scripts/pkgkit 템플릿 `module`): REST `/sdd/*`·WS `sdd.changed`, 정의 종류 기여
  (문서 틀·스펙), 사용자 설정 섹션 `sdd`, 설치자 옵션(기본값 `data/defaults.json`), 공간 고르기
  (`sdd.spaces`, 없으면 단독 루트), 작업 연동(X43)·검증 출처(X42, 플러그인 로더), 파싱 캐시, 본문 비밀
  검사, 실행 라벨 표시 규칙(`data/label_display.json`), 포트 `sdd.service`, 단독 실행 `python -m`.
- 6R.20a: 문서 틀 단건 REST(`template_routes`) — `POST /sdd/templates`, `GET·PUT·DELETE /sdd/templates/{id}`,
  `…/variables`, 뼈대 파일 `…/files[/{path}]`(ETag·If-Match = 정의 버전, 본문 비밀 검사), 버전
  `…/versions[/{hash}[/files[/{path}]]]`·`POST …/versions/{hash}/restore`. 저장소는 `/sdd/templates` 목록과 같다
  (라이브러리 → 없으면 단독 루트, `?project=` = 공간). 경로 예약어 `TEMPLATE_ROUTE_WORDS`(`variables`·`check`)는
  틀 id로 쓰지 않는다. 비밀 의심 이슈 만들기를 `secrets.document_issues`로 모았다(단독 저장소 쓰기 전 검사와 공용).
- 6R.20d: `GET /sdd/import/files`가 하위 폴더(`dirs`)를 준다(`ac-sdd` `list_import_files`).
