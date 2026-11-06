# agent-console-link-runs-sdd

스펙(`mod-sdd`)과 실행 기록(`mod-runs`)을 잇는 연동 모듈(`link-runs-sdd`, design §6R.1.5·§6R.1.6).
스펙 작업 문서의 작업을 실행 프로필(팀 구성 + 입력 틀)로 실행하고, 실행 결과를 작업 표시와 추적 표에
반영한다.

| 하는 일 | 어떻게 |
| --- | --- |
| 작업 동작(X43 `sdd.integrations`, 연동 id 기본 `runs`) | 스펙 규칙 `run_profiles`마다 동작 하나. `when`이 맞지 않는 작업에는 내지 않는다. `run` 관문이 막으면 `disabled`(`sdd.gate_blocked`) |
| 실행 | `when` → `run` 관문 → 입력 틀 치환 → 비밀 검사(`sdd.secret_scan`) → 라벨 상한 → `runs.starter.start_graph(graph, input, origin="sdd", project_id=공간 이름, labels)` |
| 실행 라벨 | `<접두>spec`·`<접두>task`·`<접두>profile`·`<접두>purpose`(접두 = `mod-sdd.run_label_prefix`, 기본 `sdd.`) |
| 결과 반영 | `runs.event` 상태 이벤트 → 실행 프로필 `status_on[결과 이름]`이 있으면 작업 머리 줄 하나만 고친다(`by: run`). 실행 중에 그 줄이 바뀌었거나 `task_status` 관문이 막으면 고치지 않고 정보 이슈 `sdd.status_not_applied`(`details.reason`·`gate_id`) |
| 실행 연결 | `runs.reader.page(labels={<접두>spec: id}, root_only=True)`를 상한까지 → `TaskLink{kind: run}`(상태·시각·토큰 합) |
| 검증 출처(X42 `sdd.verification_sources`, id 기본 `runs`) | `verification.purposes` 목적 실행 → `result_map`으로 바꾼 `VerificationResult` |
| 프로필 검사 | 그 공간에 팀 구성이 없으면 `sdd.profile_graph_missing`(`details.in_library`) |

실행 상태 → 결과 이름(`status_on`·`result_map`이 쓰는 이름) 표, 반영할 이벤트 종류, 연동·출처 이름,
`origin`, 읽기 한도는 설치자 옵션 `modules.options.link-runs-sdd`이고 기본값은 패키지 데이터
`data/defaults.json`이다(`running → started`, `completed → succeeded` 등). `status_on`·`result_map`에
실행 상태 이름(`completed`)을 직접 써도 맞는다.

이 연동이나 `mod-runs`가 꺼지면 `capabilities.runs=false`이고 실행 버튼·실행 칩·검증 열이 없다.
문서·작업·계획·추적(요구 ↔ 작업)은 그대로 동작한다.

자동 진행(6R.16)은 `RunsTaskIntegration.start`(관문·입력·라벨·시작)와 `StatusReflector.add_listener`
(실행 결과 알림) 위에 올린다.

## 설치

```bash
pip install agent-console-link-runs-sdd
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-runs-sdd
```

## 최소 사용

라벨 질의를 페이지 끝까지 모으고(`labeled_runs`), 실행 시작 예외를 오류 이슈로 바꾼다
(`start_issue`). 가짜 실행 모듈(`testing.FakeRuns`)은 서버 없이 같은 모양을 준다.

```python
>>> import asyncio
>>> from agent_console_link_runs_sdd import labeled_runs, start_issue
>>> from agent_console_link_runs_sdd.testing import FakeRuns
>>> runs = FakeRuns(graphs={None: {"team"}}, library={"shared"})
>>> for key in ("1.1", "1.2", "1.3"):
...     _ = asyncio.run(runs.start_graph("team", {}, labels={"sdd.spec": "s", "sdd.task": key}))
>>> [r.labels["sdd.task"] for r in labeled_runs(
...     runs, project_id=None, labels={"sdd.spec": "s"}, limit=10, page_size=2)]
['1.3', '1.2', '1.1']
>>> try:
...     asyncio.run(runs.start_graph("shared", {}, project_id="p1"))
... except Exception as exc:
...     issue = start_issue(exc)
>>> issue.code, issue.details["in_library"]
('project.not_imported', True)

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

서버 조립에서는 entry point `agent_console.server_modules`의 `link-runs-sdd`로 켜진다(필수 포트
`runs.starter`·`runs.reader`·`sdd.service`).

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
