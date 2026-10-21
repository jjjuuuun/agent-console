# agent-console-mod-imports

Agent Console 가져오기 기능 모듈(design §3R.1.3, §R11). 가져오기 라이브러리 `agent-console-imports`를 서버에 꽂는다.
외부 설정(`~/.claude`, 프로젝트 `.claude/` 등)에서 정의를 **복사해** 가져온다. 원본은 읽기만 한다.

- 경로: `GET /resources/import/sources`, `POST /resources/import/preview`(쓰기 없음), `POST /resources/import`.
- 필수 포트: `definitions.store`(가져온 정의를 쓸 저장소). 선택 포트: `secrets.rules`(없으면 기본 의심 규칙).
- 설정 `modules.options.mod-imports`(옛 최상위 `imports`는 4R.18부터 `settings.removed_key` 오류로 새 위치를 안내): `home`(비우면 HOME·USERPROFILE),
  `project_dir`(비우면 호스트 `paths.base_dir` — 설정 파일 폴더. 4R.18부터 실행 모듈의 `working_directory`를
  기본값으로 읽지 않는다. 작업 폴더의 `.claude/`를 가져오려면 이 값을 직접 준다), `options`(출처 공장 이름 → 옵션).
- 웹 역할: `imports`.

## 설치

```bash
pip install agent-console-mod-imports
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-mod-imports
```

## 최소 사용

정의 저장소가 없으면 모듈은 꺼진다(이유 보고). 제공 모듈과 함께 조립한다.

```python
>>> from agent_console_modkit import assemble
>>> from agent_console_mod_imports import module
>>> from agent_console_mod_imports.testing import local_definitions_module
>>> assemble([module]).report[0].missing
('definitions.store',)
>>> [(r.id, r.state.value) for r in assemble([module, local_definitions_module()]).report]
[('local-definitions', 'active'), ('mod-imports', 'active')]

```

홈 폴더는 설정 값(상대 경로는 `base_dir` 기준) 또는 환경변수에서 찾는다.

```python
>>> from pathlib import Path
>>> from agent_console_mod_imports import resolve_home
>>> resolve_home(None, {"HOME": "/home/me"}, None).as_posix()
'/home/me'
>>> resolve_home(Path("people/me"), {}, Path("/srv")).as_posix()
'/srv/people/me'
>>> resolve_home(None, {}, None) is None
True

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

단독 실행(같은 modkit 호스트, 기본 127.0.0.1). `--with`를 주지 않으면 `testing.local_definitions_module`
(워크스페이스 폴더의 파일 저장소)을 붙인다. 다른 제공자를 쓰려면 `--with <모듈 id>`.

```bash
python -m agent_console_mod_imports [--with ID] [--config PATH] [--port 0] [--check]
```
