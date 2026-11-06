# 변경 기록

## 미출시

- 7R.13: `testing.FolderSpaces`(등록 id → 폴더 목록으로 `open_space`)를 `link-projects-sdd`에서 옮겨 왔다(`link-projects-wiki`도 쓴다).

## 0.1.0

- 5.7R.33x: `SpaceError`가 `agent_console_store.StoreError`를 잇는다(정의 경로 공용 오류 매핑이 `code` 그대로 응답 — `project.config_readonly` 409 등). `SecretRejected.field_issues()`(위치마다 `secret.plain_found` error 이슈, 값 없음). 쓰기 전 검사가 버전 기록소의 `ensure_writable()`(`VersionWriteCheck`)을 불러, 기록 DB를 쓸 수 없으면(앞선 리비전 등) 정의 파일도 쓰지 않는다(`RecordsUnavailable` 409).
- 5.7R.33w2: `missing_gitignore_lines`·`append_gitignore`(`.gitignore` 틀의 빠진 줄 점검·덧붙이기).
- 5.7R.33w: 처음 만듦. `open_space`·`init_space`(매니페스트·`.gitignore` 틀을 없을 때만 만들고 있으면 채택,
  쓸 수 없으면 `config_writable=false`), `read_manifest`·`write_manifest`(If-Match, 모르는 키·주석 보존)·`reset_manifest`,
  비밀 저장 거부(`secret://` 참조만), 파일 시스템 주입(`SpaceFiles`).
