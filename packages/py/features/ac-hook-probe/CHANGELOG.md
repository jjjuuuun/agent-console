# 변경 기록

## 0.1.0

- 처음 만듦(4R.7): 실행 파일 `agent-console-hook-probe`·`python -m agent_console_hook_probe`(stdin 전달, stdout·stderr·
  종료 코드 바이트 동일, 자식 프로세스 그룹 신호 전달·유예 뒤 강제 종료, 기록 실패 격리), 기록 형식 `hook-probe/1`
  (결정 파생·비밀 의심 가림·명령 해시), 셸 인자 규칙 데이터(`DEFAULT_SHELLS`), 감싸기 인자 `wrap_command`·
  `wrap_command_line`, X5 출처 `hook-probe-jsonl`·X6 분류기 `hook-probe`.
