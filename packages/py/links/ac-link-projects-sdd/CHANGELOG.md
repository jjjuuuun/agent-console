# 변경 기록

## 미출시

- 7R.13: 경로 지킴(예약 경로·링크를 푼 실제 경로)을 `ac-projects` `FolderGuard`·`normalize_reserved`·`relative_inside`로 바꿨다(동작 불변, `link-projects-wiki`와 같은 규칙 한 벌). `normalize_reserved`는 그대로 다시 내보낸다. `testing.FolderSpaces`는 `agent_console_project_space.testing`의 것을 다시 내보낸다.

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`).
- `sdd.spaces` 제공(`ProjectSddSpaces`·`ProjectSddSpace`), 폴더 안만 읽고 쓰는 `ProjectSpecFiles`(예약 경로·링크·쓰기 불가 409), 매니페스트 검사, 설정 `reserved_dirs`, 단독 실행(6R.14).
- 6R.20d: `ProjectSpecFiles.list`가 링크를 푼 실제 경로가 폴더 밖인 하위 폴더를 링크(`is_link=True`)로 표시한다
  (링크로 알아보지 못하는 재분석 지점도 가져오기 목록에서 빠지고, 열면 `SpecPathError(link)`).
