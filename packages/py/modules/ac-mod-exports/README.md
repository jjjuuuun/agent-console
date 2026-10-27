# agent-console-mod-exports

Agent Console 내보내기 기능 모듈(design §3R.1.3, §2R.7). 내보내기 라이브러리 `agent-console-exports`를 서버에 꽂는다.

- 경로: `GET /exporters`, `POST /exports/plan`(쓰기 없음), `POST /exports/archive`(zip 응답, 서버 디스크에 쓰지
  않음), `GET /exports/roots`(토큰 필수), `POST /exports/write`(허용 루트 아래에만, 기본 `on_conflict=fail`).
- 필수 포트: `definitions.lookup`(정의 읽기). 선택 포트: `exports.dependencies`(없으면 고른 항목만 내보낸다),
  `secrets.rules`(없으면 기본 의심 규칙).
- 설정 `modules.options.mod-exports`(옛 최상위 `exports`는 4R.18부터 `settings.removed_key` 오류로 새 위치를 안내): `roots`·`home`·
  `protected_in_home`·`protected`·`options`·`expose_paths`. 상대 경로는 `base_dir` 기준.
- 웹 역할: `exports`.

## 설치

```bash
pip install agent-console-mod-exports
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-mod-exports
```

## 최소 사용

정의 읽기 포트가 없으면 모듈은 꺼진다(이유 보고). 제공 모듈과 함께 조립한다.

```python
>>> from agent_console_modkit import assemble
>>> from agent_console_mod_exports import module
>>> from agent_console_mod_exports.testing import local_definitions_module
>>> assemble([module]).report[0].missing
('definitions.lookup',)
>>> [(r.id, r.state.value) for r in assemble([module, local_definitions_module()]).report]
[('local-definitions', 'active'), ('mod-exports', 'active')]

```

카탈로그 어댑터는 정의 읽기 포트만 있으면 된다(없는 정의는 None).

```python
>>> import tempfile
>>> from agent_console_store import DEFAULT_KINDS, FileDefinitionStore
>>> from agent_console_mod_exports import LookupExportCatalog
>>> store = FileDefinitionStore(tempfile.mkdtemp(), DEFAULT_KINDS)
>>> _ = store.create("agent", {"id": "a", "name": "A", "backend": "fake-agent"})
>>> catalog = LookupExportCatalog(store)
>>> catalog.document("agent", "a")["name"], catalog.document("agent", "ghost")
('A', None)

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
python -m agent_console_mod_exports [--with ID] [--config PATH] [--port 0] [--check]
```
