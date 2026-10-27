# 개발 방식

이 프로젝트는 [Claude Code](https://docs.claude.com/en/docs/claude-code)로 개발했습니다. 규칙 전체는 [CLAUDE.md](../CLAUDE.md)에 있고,
이 문서는 그 흐름을 짧게 정리합니다.

## 역할 구조

- **메인 세션이 조율합니다.** 작업 목록을 보고 담당 리더에게 맡기고, 결과를 받아 다음 작업을 정합니다. 직접 구현하지 않습니다.
- **리더 에이전트가 맡습니다.** [`.claude/agents/`](../.claude/agents/)에 정의된 서브에이전트입니다.

  | 에이전트 | 맡는 일 |
  | --- | --- |
  | `pl` | 요구사항 해석, 설계 문서, 작업 분해와 담당자 지정, 통합 검토(코드는 쓰지 않음) |
  | `web-designer-lead` | 화면 구성·흐름·디자인 토큰 명세(코드는 쓰지 않음) |
  | `publisher-lead` | 웹 UI 구현 |
  | `backend-lead` | 서버, 실행 엔진, 확장 지점, CLI, 로그 수집 |
  | `db-lead` | 데이터 모델, 스키마, 마이그레이션 |
  | `qa-lead` | 수용 기준 검증, 테스트, 하드코딩·재사용 점검(구현 코드는 고치지 않음) |

- 서브에이전트끼리는 서로 부를 수 없으므로 위임은 항상 메인 세션을 거칩니다.

## 작업 흐름 (SDD)

1. **설계.** 단계를 시작하면 `pl`이 design.md와 그 단계의 tasks.md를 씁니다. 사람이 승인하기 전에는 구현하지 않습니다.
2. **작업 분해.** 작업마다 담당(`[owner: ...]`), 요구사항(`[req: ...]`), 선행 작업(`[depends: ...]`)을 붙입니다.
   의존이 없는 작업만 병렬로 맡깁니다.
3. **구현.** 리더가 패키지 단위로 구현하고, 변경 파일과 바뀐 계약을 보고합니다.
4. **QA.** `qa-lead`가 수용 기준·하드코딩·재사용 원칙을 검사합니다. 실패하면 담당에게 돌려보내고, 3회 연속 실패하면 멈추고 사람에게 보고합니다.
5. 통과하면 작업에 체크하고, 코드가 설계와 달라졌으면 설계 문서도 고칩니다. 한 번에 한 단계만 진행합니다.

완료 기준은 `uv run poe check`, `pnpm check`, 계약을 건드렸으면 `uv run poe contracts-check`입니다.

## 커밋 위생

- 실행 데이터(작업 공간 `.agent-console/`, `.state/`, SQLite DB, `agent-console.yaml`)는 커밋하지 않습니다.
- 테스트 데이터(녹화 로그, 세션 로그 `*.jsonl`, 픽스처, 스냅숏)와 스크린샷·녹화 파일은 커밋하지 않습니다.
- 요구사항·설계·작업 목록 같은 내부 작업 문서는 공개 저장소에 넣지 않습니다.
- 비밀 값은 환경변수로만 두고 설정·정의에는 `secret://이름` 참조만 씁니다.
- 이 규칙은 [.gitignore](../.gitignore)에 반영되어 있습니다.

## 확장 지점

새 종류는 코드 수정 없이 Python entry point를 가진 패키지 하나로 더합니다. 서버는 이름을 모르고 등록된 것을 불러올 뿐입니다.

| entry point 그룹 | 확장 대상 |
| --- | --- |
| `agent_console.node_types` · `agent_console.edge_types` | 노드 종류, 연결 종류 |
| `agent_console.backends` | 실행 백엔드 |
| `agent_console.delegation_strategies` · `agent_console.condition_operators` · `agent_console.interaction_kinds` | 위임 방식, 조건 연산자, 상호작용 종류 |
| `agent_console.resource_types` | 리소스 종류 |
| `agent_console.log_sources` · `agent_console.log_classifiers` · `agent_console.collectors` | 로그 출처, 로그 분류기, 실행 관측 수집기 |
| `agent_console.usage_sources` | 사용량 출처 |
| `agent_console.import_sources` · `agent_console.exporters` | 가져오기 출처, 내보내기 형식 |
| `agent_console.server_modules` | 서버 기능 모듈·연동 모듈 |

[`examples/extensions/`](../examples/extensions/)에 그룹별로 동작하는 예제 패키지가 있습니다. 설치하고 서버를 다시 시작하면 편집기와 설정 폼에 새 종류가 나타납니다.

```bash
uv pip install -e examples/extensions/agent-console-example-nodes
```

서버는 빈 작업 공간으로 시작합니다. 에이전트·팀 구성은 사용자가 화면에서 만들거나 기존 `.claude/` 설정을 가져와 씁니다.
