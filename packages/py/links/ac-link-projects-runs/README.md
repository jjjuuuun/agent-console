# agent-console-link-projects-runs

Agent Console 프로젝트·실행 연동 모듈(design §UX-P.5·§5.2R.6). 실행의 `project_id`(불투명 문자열)로
프로젝트를 찾아 **프로젝트 설정 층**(작업 폴더 `working_directory` + 프로젝트 `settings`)을 공통 바로
아래에 넣는다. 실행 모듈(`mod-runs`)과 프로젝트 모듈(`mod-projects`)은 서로를 모르고, 이 연동이 둘을
잇는다.

- 받음(필수): `projects.lookup`. `mod-projects`가 꺼지면 이 연동도 꺼진다.
- 제공: `runs.scopes`(실행 시작마다 노드 서비스 `SCOPE_LAYERS`에 프로젝트 층, 없는 프로젝트 =
  `project.unknown` 경고 후 층 없이), `settings.scope_layers`(유효 설정 경로 `?project=`).
- 자식 Run(중첩 팀)은 부모 서비스를 물려받아 루트 Run의 프로젝트 층을 쓴다.
- 이 연동을 끄면: `project_id` 기록·거르기는 그대로, 프로젝트 층(작업 폴더·설정)만 빠진다.
- 설정 `modules.options.link-projects-runs`: `layer_id`(기본 `project`), `layer_label`(기본
  `프로젝트`), `unknown_message`(`string.Template`, 변수 `project`).

## 설치

```bash
pip install agent-console-link-projects-runs
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-projects-runs
```

## 최소 사용

서버 없이 프로젝트 층을 만든다(프로젝트 읽기는 주입).

```python
>>> from agent_console_contracts import Project
>>> from agent_console_link_projects_runs import ProjectScope
>>> from agent_console_link_projects_runs.testing import MemoryProjects
>>> projects = MemoryProjects([Project(id="app", name="App", working_directory="/w/app",
...                                    settings={"model": "m1"})])
>>> scope = ProjectScope(lambda: projects)
>>> [(layer.id, dict(layer.value)) for layer in scope.layers("app").layers]
[('project', {'model': 'm1', 'working_directory': '/w/app'})]
>>> [w.code for w in scope.layers("ghost").warnings]
['project.unknown']

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

단독 실행(빈 메모리 프로젝트 모듈과 함께): `python -m agent_console_link_projects_runs --check`.
실제 모듈과: `--with mod-projects --with mod-runs`.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
