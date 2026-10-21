# agent-console-mod-definitions

Agent Console 정의 기능 모듈(design §3R.1.3, R1.2·R13.1). 워크스페이스의 정의(에이전트·팀 구성·리소스·공통 설정)
저장소와 CRUD 경로를 서버에 꽂고, 다른 모듈이 쓰는 포트와 저장 알림 토픽을 낸다.

- 경로: `/agents`·`/agents/{id}`, `/graphs`·`/graphs/{id}`·`POST /graphs/{id}/duplicate`, `/settings`.
  응답은 저장 원문 + `ETag`(`version_hash`), `If-Match`로 낙관적 잠금(그래프 저장은 필수 428, 다르면 412).
- 제공 포트: `definitions.store`·`definitions.lookup`(같은 파일 저장소), `workspace.settings`(`() -> WorkspaceSettings`),
  `secrets.rules`(`() -> SecretRules`), `definitions.checks`(공통 설정의 비밀 규칙 정규식 검사),
  `server.warnings`(평문 비밀 점검 `secret.plain_found`). 토픽 `definitions.saved{kind, id, version_hash}`.
- 선택 포트: `definitions.checks`(여러 제공자 — 저장 전 검사, error면 422), `graphs.validation`·`graphs.entry_labels`
  (팀 구성 목록의 검증 요약·입구 이름, 없으면 null).
- 버전 기록: 호스트 DB 핸들(`BaseServices.database`)의 legacy 테이블(시작 때 legacy 계보를 올린다), 없으면 메모리.
- 평문 점검 캐시는 `definitions.saved`·삭제 때 버린다(계산 잠금과 짧은 상태 잠금을 나눠 교착·낡은 캐시를 막는다).
- 설정 `modules.options.mod-definitions`: `max_content_bytes`(정의 본문 총량 한도, 옛 `resources.max_content_bytes`),
  `plain_secret_issue_codes`(평문 점검으로 옮길 검사 이슈 코드).
- 웹 역할: `definitions:agent`·`definitions:graph`·`settings`.

## 설치

```bash
pip install agent-console-mod-definitions
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-mod-definitions
```

## 최소 사용

조립하면 정의 저장소 포트가 생기고, 저장할 때마다 `definitions.saved`가 나온다. 호스트 DB 핸들이 없으면 버전 기록은 메모리에 두고 경고(`definitions.versions_memory`)한다.

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_modkit import BaseServices, Paths, assemble
>>> from agent_console_mod_definitions import (
...     DEFINITIONS_SAVED, DEFINITIONS_STORE, SERVER_WARNINGS, WORKSPACE_SETTINGS, module)
>>> root = Path(tempfile.mkdtemp())
>>> base = BaseServices(paths=Paths(base_dir=root, workspace=root / "ws", state=root / "state"))
>>> assembly = assemble([module], base=base)
>>> saved = []
>>> _ = assembly.services.events.subscribe(DEFINITIONS_SAVED, lambda item: saved.append(item.id))
>>> store = assembly.port(DEFINITIONS_STORE)
>>> _ = store.create("agent", {"id": "rev", "name": "리뷰어", "token": "ghp_PlainToken123456"})
>>> saved
['rev']
>>> assembly.port(WORKSPACE_SETTINGS)().default_backend is None
True
>>> [(w.code, w.path) for w in assembly.ports(SERVER_WARNINGS)[0]()]
[('secret.plain_found', '/token'), ('definitions.versions_memory', None)]

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```

단독 실행(같은 modkit 호스트, 기본 127.0.0.1). 버전 기록은 상태 폴더의 `console.sqlite3`.

```bash
python -m agent_console_mod_definitions [--with ID] [--config PATH] [--port 0] [--check]
```
