# Agent Console

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

## 문서

- [USAGE.md](USAGE.md): 실제 Claude 연결, 기능별 사용법, 서버 운용
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md): Claude Code로 이 프로젝트를 개발한 방식과 확장 지점
- [CLAUDE.md](CLAUDE.md): 개발 규칙(원칙, 스택, 명령어, 완료 조건)
- [.claude/agents/](.claude/agents/): 개발에 쓴 리더 에이전트 정의
- 각 패키지 폴더(`packages/`, `apps/`)의 README: 패키지별 API와 설정

## 라이선스

[MIT](LICENSE) © 2026 jjjuuuun
