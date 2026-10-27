# Agent Console

[![CI](https://github.com/jjjuuuun/agent-console/actions/workflows/ci.yml/badge.svg)](https://github.com/jjjuuuun/agent-console/actions/workflows/ci.yml)

에이전트 팀을 원하는 대로 구성해서 채팅으로 일을 맡기는 로컬 웹 플랫폼입니다.
화면에서 에이전트를 만들고 그래프로 이어 팀을 구성한 뒤, 채팅으로 일을 맡기고 실행 과정·사용량·로그를 같은 화면에서 봅니다.

에이전트, 팀 구성, 리소스, 모델, 연결 종류는 모두 사용자가 만들고 고치는 데이터이며, 새 종류는 플러그인으로 더합니다.
서버(Python)와 웹(React)은 내 컴퓨터에서 돌고, 기본으로 `127.0.0.1`에서만 접속을 받습니다.

> 개발 중인 프로젝트입니다. 저장소를 받아 로컬에서 실행하는 방식만 지원하며, 화면과 설정 키는 바뀔 수 있습니다.

## 준비물

- Python 3.12 이상
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Node.js 22 이상
- pnpm 10 (`corepack enable`로 켤 수 있습니다)

## 설치

```bash
git clone https://github.com/jjjuuuun/agent-console.git
cd agent-console
uv sync --all-packages
pnpm install
```

## 실행

웹을 한 번 빌드하면 서버 하나가 API와 웹 화면을 함께 제공합니다.

```bash
pnpm --filter @agent-console/web build    # 처음 한 번, 코드를 새로 받을 때마다
AGENT_CONSOLE_SERVE_STATIC=1 AGENT_CONSOLE_WEB_DIR=apps/web/dist uv run agent-console serve --open
```

브라우저에서 <http://127.0.0.1:8765>을 엽니다. `--open`을 붙이면 서버가 준비된 뒤 자동으로 열립니다. 종료는 Ctrl-C입니다.

`agent-console`은 실행 명령입니다. `serve`(서버 실행)와 `statusline`(Claude Code 사용량 상태 줄 연결)이 있고,
옵션은 `uv run agent-console serve --help`로 봅니다.

## 처음 쓰기

서버는 빈 작업 공간으로 시작합니다. 미리 들어 있는 에이전트나 팀 구성은 없습니다.

1. **에이전트**를 만듭니다(이름·지시문·백엔드·모델).
2. **팀 구성**을 만들어 에이전트 노드를 놓고 연결합니다. 에이전트 하나만 있는 팀도 됩니다.
3. **채팅**에서 팀 구성을 골라 일을 맡깁니다. 실행 과정·사용량·로그는 각 화면에서 봅니다.

Claude Code에서 쓰던 `~/.claude`나 프로젝트 `.claude/` 설정이 있으면 **가져오기**로 복사해 올 수 있습니다(원본은 읽기만 합니다).

Claude 호출은 기본으로 이 PC의 Claude 구독 로그인을 씁니다. 로그인하지 않았다면 백엔드 상태 카드의 **[구독으로 로그인]**으로
앱 화면에서 로그인합니다(앱은 토큰을 저장하지 않습니다). API 키 방식, 모델 등록 등 자세한 설정은 [USAGE.md](USAGE.md)에 있습니다.

## 문서

- [USAGE.md](USAGE.md): 실제 Claude 연결, 기능별 사용법, 서버 운용
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md): Claude Code로 이 프로젝트를 개발한 방식과 확장 지점
- [CLAUDE.md](CLAUDE.md): 개발 규칙(원칙, 스택, 명령어, 완료 조건)
- [.claude/agents/](.claude/agents/): 개발에 쓴 리더 에이전트 정의
- 각 패키지 폴더(`packages/`, `apps/`)의 README: 패키지별 API와 설정

## 라이선스

[MIT](LICENSE) © 2026 jjjuuuun
