# agent-console-link-definitions-resources

Agent Console 정의 ↔ 리소스 연동 모듈(design §3R.1.4 L8, R13.1). 저장 전 정의 검사(`definitions.checks`)를 제공한다.

- 리소스 정의: 그 종류의 검사(`ac-resources.validate_resource`, 이슈 path는 문서 기준 `/config/...`).
- 에이전트·팀 구성·공통 설정: 리소스 첨부 `config_override`를 덮은 결과의 종류 검사(`x-secret` 평문 거부,
  리소스가 없으면 비밀 의심 규칙). 팀 구성의 리소스 연결은 디스크립터(호스트 `registries`)로 해석한다.
- 이 검사는 정의 저장 경로·버전 되돌리기의 저장 전 검사와 `/server-info` 평문 점검(정의 모듈이
  검사의 평문 이슈를 모은다)에 쓰인다.
- 필수 포트: `definitions.lookup`·`resources.types`. 선택: `resources.lookup`(없으면 `definitions.lookup`으로 찾음),
  `secrets.rules`. 경로 없음.
- 꺼지면: 정의는 리소스 검사 없이 저장된다(정의 모듈이 시작 때 경고 로그).

## 설치

```bash
pip install agent-console-link-definitions-resources
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-definitions-resources
```

## 최소 사용

검사는 서버 없이 쓴다. 리소스 종류 레지스트리·리소스 조회·팀 구성 해석을 함수로 넘긴다.

```python
>>> from agent_console_resources import InMemoryResources, new_resource_types
>>> from agent_console_link_definitions_resources import DefinitionChecker
>>> checker = DefinitionChecker(
...     types=new_resource_types, resources=InMemoryResources, plan_of=lambda graph: None)
>>> agent = {"id": "a", "name": "a",
...          "resources": [{"ref": "later", "config_override": {"token": "ghp_abcdefghijk"}}]}
>>> [(i.severity, i.path) for i in checker.issues("agent", agent)]
[('warning', '/resources/0/ref'), ('error', '/resources/0/config_override/token')]
>>> checker.issues("agent", {"id": "b", "name": "b"})
[]

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

단독 실행. `--with`를 주지 않으면 `testing.local_sources_module`(파일 저장소 + 설치된 리소스 종류)을 붙인다.

```bash
python -m agent_console_link_definitions_resources [--with ID] [--config PATH] [--port 0] [--check]
```
