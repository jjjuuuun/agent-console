# 변경 기록

## 미출시

- 6R.5: 선택 포트 `definitions.kind_contributions`(X44, `KIND_CONTRIBUTIONS`). 공간 종류 = 라이브러리 종류 + 기여 종류(`library=False` 포함) 중 옮길 수 있는 것 — `library_kinds(store, contributions=())`. 기여의 `references`를 `definitions.references`와 합쳐 복사 계획·범위 검사에 쓴다(`contribution_references`). 기여가 없으면 종류·복사 결과가 전과 같다.
- 5.7R.33i: `projects.folders`에 보관 폴더(`archived`). 옛 로그 범위 `current`용 `ProjectManager(working_directory=)`와 `working_directory` 이어받기(SeedSetting)를 지웠다. 설정 `working_directory`는 남지만 읽지 않는다(스키마 `deprecated`).
- 6R.20a(6R.20c 입력): 복사 대화상자 메타데이터 `GET /projects/copy/kinds?project=`(`CopyKindInfo[]` — 그 공간의
  복사 종류와 `library`·`portable`, 싱글턴·모르는 종류 제외)·`GET /projects/copy/items?project=&kind=`(`CopyItem[]`,
  모르는 종류 404). `CopyService(kind_info=)`·`kinds`·`items` — 종류 정보는 `library_kinds`(기본 + X44 기여).

## 0.2.0

- 5.7R.33f(깨는 변경): 등록부 = `ProjectRegistration`(폴더·보관·라벨), 이름·설명·프로젝트 층은 폴더 매니페스트. 응답은 `ProjectView`(상태·`config_writable`·`manifest_id`·`kinds`·`issues`·`config_dir`·`records_*`, 시간 상한). 등록 = `init_space`(없을 때만 쓰고 채택, 깨진 매니페스트는 쓰지 않음), 겹침 409, DELETE = 보관, `PUT archived:false` = 다시 등록.
- 새 경로: `manifest/reset`, `gitignore/append`, `{id}/legacy/plan`, `copy/plan`·`copy/apply`, `folders`·`folders/check`·`folders/capabilities`·`folders/pick`(가짜 실행기로 시험, 루프백 전용, 한 번에 하나, 끊기면 창 닫음).
- 포트 제공 `projects.spaces`·`definitions.spaces`(공간 캐시), 선택 `records.spaces`·`secrets.rules`·`definitions.reference_rewriters`. entry point `agent_console.folder_dialogs`(X35).
- 없앤 것: `definitions.checks` 범위 경고 제공, `delete-plan`·DELETE `mode`. 옛 범위 경로(`move-plan`·`move`·`scope-issues`)는 deprecated로 남김(33t 삭제).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- 5.2R.33: 프로젝트 CRUD(`projects/<id>.yaml`, 자기 `FileDefinitionStore`), `delete-plan`·삭제 두 경로(`move_to_shared`·`delete_definitions`), `move-plan`·`move`(적용), `scope-issues`, 포트 `projects.lookup`·`definitions.checks` 제공, 선택 `definitions.lookup`·`definitions.store`·`definitions.references`, 웹 역할 `projects`.
