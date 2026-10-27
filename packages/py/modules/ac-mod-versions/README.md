# agent-console-mod-versions

Agent Console 버전 기능 모듈(design §3R.1.3, R2.5, D3·E-16). 정의 버전 목록·비교·되돌리기 경로와 보존 개수를
서버에 꽂는다. 버전 기록 자체는 정의 저장소(`agent-console-store`)가 한다.

- 경로(컬렉션마다, 기본 `/agents` `/graphs` `/resources` `/settings`): `…/{id}/versions`,
  `…/versions/{hash}`, `…/versions/{a}/diff[/{b}]`, `…/versions/{hash}/files[/{path}]`,
  `POST …/versions/{hash}/restore`(`If-Match` 필수, 없음 428·다름 412, 검사 error 422).
- 필수 포트: `definitions.store`. 선택 포트: `definitions.checks`(여러 제공자 — 되돌리기 전 검사·비밀 위치),
  `secrets.rules`(없으면 기본 의심 규칙). 구독 토픽: `definitions.saved`(보존 개수 적용).
- 설정 `modules.options.mod-versions`(옛 최상위 `versions`는 4R.18부터 `settings.removed_key` 오류로 새 위치를 안내): `max_per_definition`(정의마다 남길 버전 수,
  비우면 모두 — 저장할 때와 시작할 때 적용), `collections`(버전 경로 표), `secret_issue_codes`.
- 웹 역할: `versions`.

## 설치

```bash
pip install agent-console-mod-versions
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-mod-versions
```

## 최소 사용

보존 개수를 정하면 저장 알림(`definitions.saved`)마다 오래된 버전을 지운다(현재 버전은 남는다).

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_modkit import ModulesConfig, assemble
>>> from agent_console_mod_versions import DEFINITIONS_STORE, module
>>> from agent_console_mod_versions.testing import local_definitions_module
>>> workspace = Path(tempfile.mkdtemp())
>>> config = ModulesConfig(options={"mod-versions": {"max_per_definition": 2}})
>>> assembly = assemble([module, local_definitions_module(workspace=workspace)], config)
>>> store = assembly.port(DEFINITIONS_STORE)
>>> saved = store.create("agent", {"id": "a", "name": "0", "backend": "fake-agent"})
>>> for name in ("1", "2", "3"):
...     saved = store.save("agent", {"id": "a", "name": name, "backend": "fake-agent"},
...                        expected_version=saved.version_hash)
>>> len(store.list_versions("agent", "a"))
2

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
(워크스페이스 폴더의 파일 저장소, 버전은 메모리)을 붙인다. 다른 제공자를 쓰려면 `--with <모듈 id>`.

```bash
python -m agent_console_mod_versions [--with ID] [--config PATH] [--port 0] [--check]
```
