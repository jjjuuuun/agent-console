# 변경 기록

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`, 작업 7R.13): `projects.spaces` → `wiki.spaces`(`ProjectWikiSpaces`·
  `ProjectWikiSpace`), 페이지 폴더 경로 지킴(`ac-projects` `FolderGuard` — 예약 폴더·링크를 푼 실제 경로,
  `UnsafePagesRoot` 422 `folders.invalid_path`), 쓰기 불가 폴더 `config_writable=false`(색인은 메모리), 깨진
  매니페스트·폴더 없음 409, 설정 `pages_dir`(`mod-wiki.pages_dir` 이어받기)·`index_dir`·`reserved_dirs`.
