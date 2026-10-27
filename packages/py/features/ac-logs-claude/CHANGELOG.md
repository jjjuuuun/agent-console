# 변경 기록

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `feature`).
- 4R.6: X5 `claude-code-jsonl`(세션·서브에이전트·메타 파일 발견, 기본 꺼짐)과 X6 `claude-code`(행 단위
  무상태 분류기)를 entry point로 등록. 도구 이름 특수 처리·범주·태그·hook 등 행 대응은 설정 스키마 기본값(데이터).
- 4R.12 추가: 목록 요약을 평문으로(설정 `summaries`·행 규칙 `summary` = detail 기준 포인터, 기본값은 스키마 데이터).
  `summary_text` 공개. 원문은 detail·raw 그대로.
- 4R.12 추가: 분류 전에 행·맥락을 `scrub_surrogates`로 정리(외톨이 서로게이트 → U+FFFD). 모델 검증 실패로 진단
  이벤트가 되던 행·서브에이전트 메타가 정상 이벤트가 된다.
- 4R.6·4R.12 QA 후속: 기본 `row_rules`에 `custom-title`·`ai-title`(태그 `session_title`)·`agent-name`·`permission-mode`·
  `mode`(범주 `control`)·`queue-operation`·`last-prompt`·`file-history-*` 추가. 요약 항목에 틀(`{/포인터}`,
  `{/포인터|keys}`, 자리 표시가 비면 건너뜀)을 더하고 hook·MCP·file-history 기본 요약을 평문으로. 설정
  `session_title_from_input`(기본 true) 추가.
- 4R.6·4R.12 QA 후속 2차: `attachment` 하위 종류별 요약 규칙(total_tokens_reminder·deferred_tools_record·date·
  edited_text_file 등), 비밀 후보 첨부(credential* 등)는 요약에 종류만, 모르는 첨부 요약 = 종류 이름. `atis-latch` 규칙.
  도구 결과·호출 요약 대체 항목(블록 수·결과 없음·도구 이름). 요약 틀 `{/포인터|count}` 추가.
- 5R.19: 순위 태그 `session_title.renamed`(custom-title)·`session_title.generated`(ai-title), 타임라인 소음 행
  (`ai-title`·`queue-operation`·`atis-latch`·`file-history-*`·`cost-state`·`api-request*`)을 숨김 범주 `meta`로(규칙 데이터).
- 5.5R.34: 행 규칙 `store_raw`(기본 `true`)·`keep` — `false`면 detail·raw에 원문 대신 `keep` 값 + `omitted`(크기·sha256). 기본 규칙 `api-request-blob`(요청 본문)은 원문을 저장하지 않는다(사용자 `extra_row_rules`로 다시 켬). `omitted_row`·`OMITTED_KEY` 공개. README: 설정 변경은 바꾼 뒤 수집하는 행부터, 옛 색인은 색인을 새로 만들어야 바뀐다.
