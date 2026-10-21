# agent-console-hook-probe

hook 명령을 감싸 **그대로 실행**하면서 입출력·결정·소요 시간을 jsonl로 남기는 실행 파일과, 그 기록을 읽는
로그 출처·분류기. 설계: `specs/agent-console/design.md` §4R.7(hook probe 규칙), 결정 F-16.

- **결과를 바꾸지 않는다.** stdin은 받은 그대로 원래 명령에 넘기고, stdout·stderr·종료 코드는 바이트 그대로
  돌려준다. 기록 실패·디스크 오류는 결과에 영향이 없다(경고 줄도 stderr에 섞지 않는다).
- **Claude Code와 같은 셸 규칙.** `--` 뒤가 문자열 하나면 셸 형식(POSIX `/bin/sh -c`, Windows Git Bash
  `bash -c`, 없으면 `powershell -NoProfile -Command`), 여럿이거나 `--exec`면 셸 없이 실행한다. 셸 규칙은
  데이터(`DEFAULT_SHELLS`)이고 `--shell`로 고른다(`sh`·`bash`·`powershell`·`pwsh`·`cmd` 또는 셸 실행 파일).
- **종료 신호를 자식 그룹에 전달한다.** 자식은 새 프로세스 그룹으로 뜨고, probe가 받은 TERM·INT·HUP·QUIT
  (Windows는 INT·BREAK·TERM)을 그룹에 보낸 뒤 2초 안에 끝나지 않으면 그룹을 강제 종료한다. 자식이 신호로
  끝나면 probe도 같은 신호로 끝난다. 시간 제한은 두지 않는다(Claude Code의 hook timeout).
- **기록은 가린 사본이다.** 명령 문자열은 해시(`command_digest`)만, 입출력은 스트림마다 앞 80,000바이트까지
  (`--capture-bytes`)만 남긴다. probe가 직접 만든 값(`PLAIN_FIELDS`: 시각·종료 코드·크기 등)을 뺀 **모든 필드**
  (입출력, cwd·matcher·context·세션 id·도구·에이전트·결정 사유·오류)는 `agent-console-secret-rules` 기본 규칙으로
  가린다. 스트림은 한도 뒤 4 KB(`CAPTURE_MARGIN_BYTES`)까지 잡아 먼저 가린 다음 한도로 자르므로, 경계에 걸친
  비밀도 남지 않는다(4 KB보다 긴 비밀 모양은 예외).
- **opt-in이다(F-16).** 플랫폼은 `observe.hook_probe`가 켜졌을 때 자기가 전달하는 hook에만 붙인다(4R.9).
  `.claude` 내보내기와 사용자 설정 파일은 고치지 않는다.
- 패키지 루트와 실행 경로는 표준 라이브러리만 가져온다(기록할 때 secret-rules). hook마다 뜨는 프로세스라서다.
  출처·분류기는 하위 모듈 `agent_console_hook_probe.plugins`(`agent-console-logs` 사용)에 있다.

## 설치

```bash
uv sync --all-packages                                   # 워크스페이스 안
pip install --find-links <wheelhouse> agent-console-hook-probe   # 단독(사내 의존 휠 모음과 함께)
```

| 의존성 | 무엇을 | 왜 | 대안 |
| --- | --- | --- | --- |
| `agent-console-secret-rules` | 기록 전 비밀 의심 가림 | 플랫폼 전체가 같은 규칙을 쓴다 | 자체 정규식 |
| `agent-console-logs` | 출처(`JsonlFileSource` 상속)·분류기 프로토콜 | X5·X6 확장 지점 | — |
| `agent-console-contracts` | 출처·분류기 디스크립터 | 계약 단일 소스 | — |

## 최소 사용

hook 하나(여기서는 파이썬 스크립트)를 감싸 실행하고, 남은 기록을 로그 색인으로 읽는다.

```python
>>> import json, subprocess, sys, tempfile
>>> from pathlib import Path
>>> from agent_console_hook_probe import wrap_command

>>> work = Path(tempfile.mkdtemp())
>>> script = work / "lint_hook.py"
>>> _ = script.write_text(
...     "import json, sys\n"
...     "sys.stdin.read()\n"
...     "print(json.dumps({'decision': 'block', 'reason': 'lint failed'}))\n",
...     encoding="utf-8",
... )
>>> out = work / "hook-probe"
>>> argv = wrap_command([sys.executable, str(script)], out=out, matcher="Edit")  # 실행 형식
>>> payload = {"session_id": "S1", "hook_event_name": "PostToolUse", "tool_name": "Edit"}
>>> done = subprocess.run(argv, input=json.dumps(payload).encode(), capture_output=True)
>>> done.returncode, json.loads(done.stdout)        # 원래 hook의 출력 그대로
(0, {'decision': 'block', 'reason': 'lint failed'})

>>> record = json.loads((out / "S1.jsonl").read_text(encoding="utf-8"))
>>> record["format"], record["event"], record["matcher"], record["decision"]["value"]
('hook-probe/1', 'PostToolUse', 'Edit', 'block')

>>> from agent_console_contracts.logs import LogSettings
>>> from agent_console_logs import LogFilter, LogIngestor, LogRegistries, query_context
>>> from agent_console_logs.testing import MemoryLogIndex
>>> registries = LogRegistries()
>>> _ = registries.load(enabled_sources={"hook-probe-jsonl"}, enabled_classifiers={"hook-probe"})
>>> index = MemoryLogIndex()
>>> settings = LogSettings.model_validate(
...     {"sources": [{"id": "hook-probe-jsonl", "config": {"roots": [str(work)]}}]}
... )
>>> LogIngestor(index, registries).scan(settings).new_events
2
>>> [e.title for e in index.query_events(LogFilter(), query_context(settings)).items]
['PostToolUse Edit 시작', 'PostToolUse Edit → block (exit 0)']

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 실행 파일

```text
agent-console-hook-probe --out DIR [--matcher M] [--shell SH] [--exec]
                         [--context KEY=VALUE ...] [--capture-bytes N] -- <원래 명령>
python -m agent_console_hook_probe ...      # 같은 것
```

- 기록 파일: `DIR/<session_id>.jsonl`(세션이 없으면 `no-session.jsonl`, 파일 이름에 못 쓰는 id는 해시).
  한 번의 hook 실행 = 한 줄. 여러 hook이 동시에 써도 줄이 섞이지 않게 파일 잠금 후 한 번에 덧붙인다.
- probe 자신의 사용법 오류는 종료 코드 **1**(Claude Code의 "막지 않는 오류")이다. 2(차단)를 쓰지 않는 것은
  probe 설정 실수가 도구 호출을 막지 않게 하기 위해서다. 원래 명령을 띄우지 못하면 127.
- `--context KEY=VALUE`는 기록의 `context`에 남는다. `run_id`·`node_path`(또는 `node`, `/` 구분)는 분류기가
  이벤트의 run_id·node_path로 쓴다(경로에서 읽은 값보다 우선).

## 외부 Claude Code 세션에서 직접 감싸기

플랫폼은 사용자의 `settings.json`을 고치지 않는다. 외부 세션의 hook 입출력까지 보려면 **사용자가 직접**
hook 명령 앞에 probe를 붙인다.

```jsonc
// 원래: "command": "./.claude/hooks/check.sh --strict"
// 셸 형식(원래 명령을 따옴표로 묶어 한 인자로) — Claude Code가 셸로 돌리던 방식 그대로 실행된다
"command": "agent-console-hook-probe --out ~/.agent-console/hook-probe -- './.claude/hooks/check.sh --strict'"
// 또는 실행 형식(Claude Code `args` 형식)
"command": "agent-console-hook-probe",
"args": ["--out", "/home/me/.agent-console/hook-probe", "--exec", "--", "./.claude/hooks/check.sh", "--strict"]
```

그다음 로그 설정에서 그 폴더를 출처 루트에 더한다: `logs.sources: [{id: hook-probe-jsonl, config: {roots:
["~/.agent-console/hook-probe"], include: ["**/*.jsonl"], run_layout: false}}]`. 감싸기를 그만두려면
명령 앞의 probe 부분만 지우면 된다.

## 기록 형식 `hook-probe/1`

| 키 | 뜻 |
| --- | --- |
| `format` | `"hook-probe/1"`(형식이 바뀌면 숫자를 올리고 분류기가 버전별로 읽는다) |
| `probe_id` | 실행 한 번의 id(시작·끝 이벤트의 `call_id`) |
| `event`·`session_id`·`tool_use_id`·`tool`·`agent_id`·`agent_type`·`cwd` | hook 입력(stdin JSON)에서 |
| `matcher`·`context`·`form`(`shell`/`exec`)·`shell` | probe 인자에서 |
| `command_digest` | `sha256:<hex>`(원래 명령 원문은 남기지 않는다) |
| `started_at`·`ended_at`(epoch 초)·`duration_ms` | 시각·소요 시간 |
| `exit_code`·`signal`·`forwarded_signal`·`error` | 종료 코드(신호로 끝나면 null + `signal`), probe가 전달한 신호, 실행 실패 사유 |
| `decision` | `{value, source, reason, updated_input, updated_output, additional_context}` — value: `block`(종료 2)·`stop`(continue false)·`allow`/`deny`/`ask`/`defer`·`modify`(수정 입력만)·`none`·`error`(그 밖 종료 코드·실행 실패) |
| `input`·`stdout`·`stdout_json`·`stderr` | 입출력(가림·크기 제한). 입력이 JSON 객체면 객체, 아니면 텍스트 |
| `bytes`·`truncated` | 스트림별 실제 크기와 잘림 여부 |

## 로그 출처·분류기

| id | 종류 | 설정 |
| --- | --- | --- |
| `hook-probe-jsonl` | X5 출처(`JsonlFileSource` 상속), **기본 켜짐**(이미 플랫폼 데이터) | `roots`(비우면 호스트 `paths["state"]/runs`), `include`(기본 `**/hook-probe/*.jsonl`), `exclude`, `run_layout`(기본 참: 경로 `<run>/<노드…>/hook-probe/<파일>`에서 run_id·node_path) |
| `hook-probe` | X6 분류기 | `category`(기본 `hook`), `error_category`(기본 `error`: 막지 않는 오류·실행 실패), `actor`(기본 `hook`), `probe_basis`(기본 `hook_probe`) |

기록 한 줄 → 이벤트 둘(`start`·`complete`, 같은 `call_id` = `probe_id`라 색인이 소요 시간을 계산).
`correlation.call_id = tool_use_id`로 같은 도구 호출의 다른 출처 이벤트(Claude Code 세션·플랫폼 실행)와 이어진다.
태그: `hook`, `hook:<이벤트>`, `decision:<값>`.

## 공개 API

| 묶음 | 이름 |
| --- | --- |
| 실행 | `main`(콘솔 스크립트), `parse_args`, `ProbeUsageError`, `USAGE_EXIT_CODE`, `run_probe`, `ProbeIO`, `DEFAULT_GRACE_SECONDS`, `SPAWN_FAILED_EXIT_CODE` |
| 감싸기 | `wrap_command`(인자 목록), `wrap_command_line`(설정 파일용 한 줄), `default_probe_command` |
| 셸 규칙 | `DEFAULT_SHELLS`, `ShellRule`, `shell_invocation`, `exec_invocation`, `default_shell_name` |
| 결정·기록 | `derive_decision`, `parse_hook_output`, `BLOCKING_EXIT_CODE`, `build_record`, `RECORD_FORMAT`, `Capture`, `ProbeOutcome`, `command_digest`, `default_redactor`, `record_file_name`, `append_line`, `DEFAULT_CAPTURE_BYTES` |
| 플러그인 | `agent_console_hook_probe.plugins`: `HookProbeSource`, `HookProbeClassifier`, `SOURCE_ID`, `CLASSIFIER_ID` |

## 한계

- probe가 SIGKILL로 강제 종료되면 자식에게 전달할 수 없다(자식 그룹이 남을 수 있다).
- Windows의 신호 전달은 `CTRL_BREAK_EVENT`(INT·BREAK) 또는 자식 종료(TERM)이고, 강제 종료는 자식 하나만 끝낸다.
  Windows 경로는 셸 인자 규칙 단위 테스트로만 확인했다.
- 자식이 끝난 뒤에도 손자 프로세스가 stdout·stderr를 잡고 있으면 그 파이프가 닫힐 때까지 기다린다(원래
  명령을 직접 실행했을 때와 같다).

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다(사내 의존은 `--find-links <wheelhouse>`).

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
