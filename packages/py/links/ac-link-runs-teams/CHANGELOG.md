# 변경 기록

## 미출시

- 5.2R.106 후속: 설치자 옵션 스키마 `RunsTeamsLinkSettings`(`issue_fixes_file` — 해결 버튼 표 교체, 빈 표 파일 = 끄기)와 `issue_fixes_of`. 모듈이 `TeamRules(issue_fixes=)`에 넘긴다.
- 5.2R.43: 준비(`prepare`)가 위임 방식 디스크립터를 `prepare_run(strategies=)`로 넘겨 엔진 대기 grant가 세션 단위(`shares_session` 반영)다.
- 5.2R.34: 노드 서비스 `SCOPE_LAYERS`를 사전 점검·준비에 반영. 준비 결과 `TeamRunPreparation.run_context`에 Run 유효 작업
  폴더(`RUN_CONTEXT_CWD` = `cwd`, `TeamRules(cwd_key=)`), `run_working_directory`.
- 5.2R.5: 해결 버튼 표 `IssueFixes`(데이터 `data/issue_fixes.json`, `DEFAULT_ISSUE_FIXES`·`load_issue_fixes`). `TeamRules.annotate_issues`(검증 이슈에 `fix`), `TeamRules.error_fix`(노드 서비스 `ERROR_FIXES`), 인자 `issue_fixes`.
- 5R.11: 노드 서비스 `TEAM_LOOKUP`(팀 구성 읽기 = `runs.starter.load_graph(id, version_hash)`)과 팀 규칙의 중첩
  검사(`TeamRules(graphs=)`·`find_team`). 단독 실행 동반 모듈 `LocalChecker.load_graph`가 버전 해시를 따른다.

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`).
- 팀 규칙 검사·실행 준비(`runs.preparers`)·노드 서비스(`runs.services`)·목록 검증 요약(`graphs.validation`, 워크스페이스 지문 캐시)·`POST /graphs/{id}/validate`를 `apps/server`에서 옮겼다(3R.13).
