# agent-console-cli

조립 앱: `agent-console` 명령. 서버 실행(`serve`)과 Claude Code statusLine 사용량 브리지(`statusline`)만 노출한다.
로직은 패키지에 있다 — 서버는 `agent-console-server`, 사용량 상태 줄은 `agent-console-usage`. 이 앱은 Typer 명령만 조립한다.
설계: `specs/agent-console/design.md` §R5.2·§R7(1R), §6.3(Phase 1).

터미널 콘솔(`console`)은 2R.20에서 삭제했다(design §R5.2, 채팅이 대신한다). 되돌리려면 태그 `phase-2r`를 본다.

## 설치

```bash
uv sync --all-packages        # 워크스페이스 안
uv pip install ./apps/cli     # 단독(서버·사용량 패키지도 함께 설치)
```

| 의존성 | 무엇을 | 왜 | 대안 |
| --- | --- | --- | --- |
| `typer` | 명령·옵션·도움말 | 확정 스택(CLAUDE.md). 타입 힌트로 옵션 선언, 환경변수 기본값 지원 | click 단독, argparse |
| `agent-console-server` | `serve`, 서버 설정에서 workspace 경로 읽기 | 한 번 설치로 `serve`까지(`uv tool install`, R10.1). `_server` 모듈에서만 지연 import(import-linter 예외 1개) | 하위 프로세스로 `python -m agent_console_server` 실행 |
| `agent-console-usage` | `statusline` 파싱·파일 합치기·원자적 쓰기·상태 줄 | 서버 사용량 출처와 같은 파일 형식을 한 곳에서 | — |

1R.15에서 `agent-console-client`·`agent-console-contracts`·`rich`·`prompt-toolkit`·`platformdirs` 의존을 뺐다(콘솔 보류, 2R.20에서 삭제).

## 명령

```bash
uv run agent-console serve [--config PATH] [--host H] [--port N] [--workspace DIR]
                           [--apply-preset ID ...] [--allow-origin ORIGIN ...] [--open | --no-open]
                           [--enable-module ID ...] [--disable-module ID ...]
uv run agent-console statusline (--output PATH | --config PATH) [--label WINDOW=TEXT ...]
                                [--template TEXT] [--separator TEXT] [--empty TEXT]
```

### `serve`
`agent_console_server.load_settings(config, overrides=…)` → `serve(settings)`만 부른다. 옵션 의미는
`python -m agent_console_server`와 같다(우선순위: 명령행 > `AGENT_CONSOLE_*` 환경변수 > 설정 파일 > 기본값).
토큰은 출력하지 않는다 — 클라이언트는 `GET /api/v1/bootstrap`으로 받는다. 설정 오류(1R에서 삭제된 키 포함)는 종료 코드 2.

- `--allow-origin ORIGIN`(여러 번): 설정 파일·환경변수의 `security.allowed_origins` **뒤에 덧붙인다**(목록을 바꾸지 않는다,
  중복·끝의 `/` 무시). 루트 `pnpm app`이 웹 미리보기 출처를 넣을 때 쓴다. 환경변수 `AGENT_CONSOLE_ALLOWED_ORIGINS`는
  예전처럼 목록 전체를 바꾼다.
- `--open`/`--no-open`: 서버 설정 `web.open.enabled`를 덮어쓴다(없으면 설정값, 기본 꺼짐). 준비되면(`GET /api/v1/health`) 웹 화면을 연다.
  열 주소·명령은 설정 `web.open.url`·`command`, 주소가 없으면 `web.serve_static`이 켜졌을 때 서버 주소. 서버 하나로 웹까지
  띄우는 방법은 `apps/server/README.md` "단일 실행".
- `--enable-module ID`·`--disable-module ID`(여러 번): 서버 모듈을 켜고 끈다. 설정 `modules`(`enabled`·`disabled`)보다
  우선하고, 같은 id가 둘 다에 있으면 끄기가 이긴다. 모듈 id·상태는 `GET /api/v1/modules`(예: `mod-chat`·`link-chat-runs`).

### `statusline`
Claude Code가 statusLine 명령에 넘기는 stdin JSON을 받아 사용량 상태 줄 한 줄을 출력하고, `rate_limits`만
브리지 파일에 원자적으로 합쳐 쓴다(서버의 `statusline-file` 사용량 출처가 읽는다). 로직은
`agent-console-usage`(`agent_console_usage.statusline`)에 있고 이 명령은 stdin·stdout·경로만 잇는다.
`~/.claude`를 읽거나 쓰지 않는다 — statusLine 설정 한 줄은 사용자가 직접 넣는다(`packages/py/features/ac-usage/README.md`).

| 옵션 | 기본 | 의미 |
| --- | --- | --- |
| `--output`, `-o` | — | 브리지 파일 경로(권장: 빠름) |
| `--config` / `AGENT_CONSOLE_CONFIG` | — | `--output`이 없을 때 서버 설정의 `<workspace>/.state/usage/statusline.json`. 둘 다 없으면 종료 코드 2(현재 폴더에 몰래 쓰지 않는다) |
| `--label` | 창 id 그대로 | `창=표시 이름`(여러 번) |
| `--template` | `{label} {percent}{resets_suffix}` | 창 하나의 틀. 자리 `label`·`window`·`percent`·`resets_in`·`resets_suffix` |
| `--separator` | ` · ` | 창 사이 구분자 |
| `--empty` | 빈 문자열 | 보일 창이 없을 때 |

- 창·필드가 빠져 있어도 동작한다. 사용률이 없으면 `-`(숫자를 만들지 않는다), 창이 하나도 없으면 파일은 그대로.
- 종료 코드: 0 정상, 1 입력이 JSON 객체가 아님(파일 그대로) 또는 파일 쓰기 실패(줄은 출력), 2 옵션·설정 오류.
- 브리지 파일은 원자적으로 교체하지만 읽기-합치기-쓰기를 잠그지 않는다. 여러 세션이 같은 파일에 동시에 쓰면 마지막
  쓰기가 이긴다(`packages/py/features/ac-usage/README.md` "브리지 파일 형식").

## 공개 API(재사용)

| 이름 | 설명 |
| --- | --- |
| `main(argv=None) -> int`, `app`(Typer) | 진입점 |

명령 내부 함수(`_server.run_server`·`merge_origins`·`server_state_dir`, `_statusline.run_statusline`)는 앱 전용이다.
재사용할 로직은 `agent-console-usage`(`agent_console_usage.statusline`)와 `agent-console-server`에 있다.

## 시작 시간

`statusline`은 Claude Code가 상태 줄을 그릴 때마다 실행된다. 그래서 모듈 상단에서 서버·클라이언트·계약(pydantic)을
import하지 않고, `agent_console_usage.statusline`(표준 라이브러리만 사용)만 읽는다. `agent-console-usage`의 `__init__`은
이름을 처음 쓸 때 import한다(PEP 562). 단위 테스트가 `import agent_console_cli` 뒤 `sys.modules`를 검사한다.
측정(WSL `/mnt/c`, 1R.15): 콘솔 엔트리포인트 직접 실행 약 1.5초 → 약 0.45초, `uv run` 경유 약 1.9초 → 약 0.8초.
상태 줄에는 `uv run` 대신 설치된 `agent-console` 실행 파일 경로를 쓰는 편이 빠르다.

## 테스트

```bash
uv run pytest apps/cli/tests
```

- 단위: 노출 명령(`serve`·`statusline`만), `serve` 옵션 전달·설정 오류·1R 삭제 키 거부, 허용 출처 덧붙이기,
  시작 시 무거운 패키지를 import하지 않음.
- statusline: 파일 쓰기·상태 줄·잘못된 입력·옵션 오류·서버 설정 workspace 사용, `~/.claude`를 건드리지 않음.
