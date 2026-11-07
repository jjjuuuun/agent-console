# agent-console-link-projects-runs

Agent Console 프로젝트·실행 연동 모듈. 실행의 `project_id`(불투명 문자열)로
프로젝트를 찾아 **프로젝트 설정 층**(작업 폴더 `working_directory` + 프로젝트 `settings`)을 공통 바로
아래에 넣는다. 실행 모듈(`mod-runs`)과 프로젝트 모듈(`mod-projects`)은 서로를 모르고, 이 연동이 둘을
잇는다.

- 받음(필수): `projects.lookup`. `mod-projects`가 꺼지면 이 연동도 꺼진다. 같은 객체의 선택 메서드
  `get_view`(`ProjectView`)로 상태·기록 DB를 점검한다.
- 받음(선택): `definitions.spaces`(Run의 정의 출처 = 프로젝트 공간), `definitions.lookup`(라이브러리 —
  `project.not_imported`의 `in_library`만).
- 제공: `runs.scopes`(실행 시작마다 노드 서비스 `SCOPE_LAYERS`에 프로젝트 층, 정의 출처
  `run_definitions`, 사전 점검 거부 `errors`), `settings.scope_layers`(유효 설정 경로 `?project=`).
- 사전 점검: `project.required`(422)·`project.not_found`(404)·
  `project.folder_missing`·`project.manifest_invalid`(409)·`project.not_imported`(422, `in_library`)·
  `project.records_unavailable`(409)·`project.outside_folder`(422, 경로·층·노드). 경로 필드는 스키마
  주석 `x-path`로만 찾고(에이전트 설정 + 유효 백엔드의 `backend_options` 스키마), 앱 workspace·상태
  폴더는 허용, `{workspace}`는 프로젝트 폴더로 바꿔 본다.
- 자식 Run(중첩 팀)은 부모 서비스를 물려받아 루트 Run의 프로젝트 층·정의 출처를 쓴다.
- 이 연동을 끄면: `project_id` 기록·거르기는 그대로, 프로젝트 층·정의 출처·사전 점검만 빠진다.
- 설정 `modules.options.link-projects-runs`: `layer_id`(기본 `project`), `layer_label`(기본
  `프로젝트`), `unknown_message`(`string.Template`, 변수 `project`), `require_project`(기본 참, 0.3.0부터 — 프로젝트 없이 시작하는 실행·대화 턴은 422 `project.required`. 프로젝트 없는 실행을 쓰려면 `false`로 준다. `ProjectScope(require_project=)` 생성자 기본은 그대로 거짓).

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
>>> projects = MemoryProjects([Project(id="app", name="App", folder="/w/app",
...                                    settings={"model": "m1"})])
>>> scope = ProjectScope(lambda: projects)
>>> [(layer.id, dict(layer.value)) for layer in scope.layers("app").layers]
[('project', {'model': 'm1', 'working_directory': '/w/app'})]
>>> [w.code for w in scope.layers("ghost").warnings]
['project.unknown']
>>> [e.code for e in ProjectScope(lambda: projects, require_project=True).scope_run(
...     None, {}, project_id=None).errors]
['project.required']

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
