# 변경 기록

## 0.1.0

- 처음 만듦(4R.4): X5·X6 프로토콜·레지스트리, `JsonlFileSource`, `LogIngestor`, `LogIndex` 프로토콜,
  질의 의미(`query`), `testing.MemoryLogIndex`·계약 테스트 묶음, 기본 플러그인 `normalized-v1`·`mapped-jsonl`,
  기본 분류 체계 `default_taxonomy.yaml`.
- 4R.7 보완(4R.4 QA 제안): `JsonlFileSource` 회전 감지(앞부분 지문 `state.jsonl_head` + 내용 세대
  `state.jsonl_generation` → `RawRecord.generation`·`identity_for(generation=)`, 기본 0이면 identity 그대로),
  줄어든 파일을 다시 읽을 때 `read_bytes` 과소 계산 수정, 파일 심볼릭 링크 정책(루트 밖 링크 건너뜀·같은 실제 파일
  한 번). 기존 공개 API는 그대로이고 키워드 인자·필드만 기본값과 함께 더했다.
- 4R.10: 레지스트리 이름 상수 `LOG_SOURCES_EXTENSION`·`LOG_CLASSIFIERS_EXTENSION`을 패키지 최상위에서 내보낸다
  (호스트 플러그인 로더가 묶음의 같은 이름 확장을 쓰도록).
- 4R.10 수정: `LogRegistries(sources=, classifiers=)`에 빈 레지스트리를 주면 거짓 값이라 새 레지스트리로
  바꿔 버리던 문제를 고쳤다(`is not None`으로 가름). 호스트 묶음의 빈 확장에 로드하는 경로가 이것에 기댄다.
- 4R.14: 오프라인 보관본 `build_archive`(`LogArchive` v1, 필터 범위·이벤트 수·바이트 한도·내보내기 가림)·
  `filter_to_params`·`render_archive`(스크립트 없는 HTML, CSP로 스크립트·외부 자원 차단)·`escape_html`.
- 4R.12 추가: `LogEventDraft.summary`(선택, 기본 None). 분류기가 주면 그 평문을 목록 요약으로 쓰고(가리기·길이
  제한은 같게), 없으면 이전처럼 detail(없으면 raw)을 문자열로 만든다.
- 4R.14 후속: 외톨이 서로게이트(U+D800~DFFF, 깨진 UTF-16 원문)를 `build_record`가 모든 문자열 필드(본문·원문 안,
  태그·상관·토큰 표본·줄 정보 포함)에서 U+FFFD로 바꾼다(SQLite 쓰기·직렬화 실패로 수집이 멈추지 않게).
  `build_archive`·`render_archive`(`escape_html`)도 같은 방어를 둔다. 공개 함수 `scrub_surrogates`.
- 5R.19: 세션 제목 순위 규칙 데이터(`SessionTitleRule`·`QueryContext.session_title_rules`·`data/default_session_title_rules.yaml`,
  `query_context(session_title_rules=)`, `pick_session_title`), 기본 분류 체계 숨김 범주 `meta`, 짝 질의 색인 사용 실행 계획 테스트.
