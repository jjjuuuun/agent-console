# 변경 기록

## 미출시 (0.2.0)

- I.7c: Message catalog `locales/en.json` registered as entry point `agent_console.message_catalogs` `ac-mod-sdd`, so the web can show the module description and settings in English (data only, no API change). Log lines are now English.
- P1.19: The kind contributions carry `open_role` (spec `sdd`, document template `sdd:templates`, `SPEC_OPEN_ROLE` and `TEMPLATE_OPEN_ROLE`), so the copy dialog kind list (`CopyKindInfo.open_role`, contracts 0.16.0) can offer "Open" for these rows.
- P1.17: Added template version comparison: `GET /sdd/templates/{id}/versions/{a}/diff` (version → current) and `GET /sdd/templates/{id}/versions/{a}/diff/{b}`. Both return the existing contract `DefinitionDiff` and take `?project=<space>` like the other version routes. The calculation is the shared `agent_console_store.diff_versions` (same as `mod-versions`); locations that look like secrets (`secrets.document_secret_paths`, the rules used by restore) are masked as `***`. New public helper `secrets.document_secret_paths`. Consumer range: `agent-console-mod-sdd>=0.2,<0.3`; requires `agent-console-store>=0.2,<0.3`.
- P1.5: `GET /sdd/info`가 `SddInfo.reserved_template_ids`(= `TEMPLATE_ROUTE_WORDS`, 계약 `sdd` 1.4.0)를 낸다 — 화면이 새 틀 id 칸에서 미리 안내한다. `SddService.info(scope, *, reserved_template_ids=())`.
- P1.5 결함 수정: 틀로 저장(`POST /sdd/specs/{id}/save-as-template`)이 경로 예약어 id를 받으면 새 틀 만들기와 같은 422 `validation_failed`(`details` = `{id, reserved}`)로 거절하고 아무것도 쓰지 않는다. 이름에서 만든 id·`rename` 새 id는 예약어를 피한다(전에는 `check`·`variables` 같은 틀이 만들어져 그 틀의 GET이 고정 경로에 가려졌다). 공개 함수 `template_routes.reject_reserved_template_id`.
- FU.6: 문서 틀 종류 데이터가 경로 예약어(`TEMPLATE_ROUTE_WORDS`)를 `DefinitionKind.reserved_ids`로 싣는다(복사 계획이 새 id를 제안).

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
