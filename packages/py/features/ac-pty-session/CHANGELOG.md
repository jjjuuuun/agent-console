# 변경 기록

## 0.1.0

- 처음 만듦(5.2R.81, ux-overhaul §15.9): `PtySession`(띄우기·읽기·쓰기·키·대기·유예 뒤 강제 종료),
  `TerminalText`·`strip_ansi`(제어 시퀀스 제거, `\r` 덮어쓰기, 줄 단위 화면, OSC 8 링크), `ExpectRules`·
  `ExpectWatcher`(규칙 → 신호, 컴파일 함수 주입), POSIX `ptyprocess`·Windows `pywinpty`(선택 `windows`) 어댑터,
  `PtyUnavailableError`, 테스트용 `FakePty`·`FakePtySpawner`.
