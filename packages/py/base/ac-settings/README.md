# agent-console-settings

설정 **층 병합**과 **값별 출처 추적**, 두 정의 문서의 **비교**를 하는 순수 라이브러리. 사내 의존이 없고, 외부 의존은 문서 비교용 `jsonpatch` 하나다.

- 층(예: 공통 → 팀 구성 → 에이전트 → 노드)은 호출자가 넘기는 **데이터 목록**이다. 층 개수·이름·필드는 자유다.
- 기본 규칙: 스칼라·목록 = **교체**, 객체 = **키별 재귀 병합**. 키를 생략하면 상속, 값이 있으면(`null`·빈 목록 포함) 그 층에서 지정.
- 필드별 예외는 데이터로 둔다: JSON Schema 주석 `x-merge`(기본값) < `rules={JSON Pointer: 전략 이름}`(사용자 설정 `settings_merge`).
- 전략은 이름으로 등록하는 표다. 기본 `replace`·`merge`·`append`·`union`·`intersect`. 필드 이름은 코드에 없다.
- 결과의 `provenance`는 `{JSON Pointer: 층 id}` — 잎 값·목록 원소마다 어느 층에서 왔는지.
- `find_widenings`: 아래 층이 위 층보다 범위를 넓혔는지(경고용). 비교 위치도 데이터(`x-widen` 주석 또는 `checks`).
- `set_at`/`unset_at`: 화면의 "이 층에서 덮어쓰기"/"상속으로 되돌리기"를 층 값에 적용하는 도우미(원본 불변).

리소스 첨부도 같은 층 병합 규칙을 쓴다.

## 설치

```bash
uv sync --all-packages                      # 워크스페이스 안에서
uv pip install ./packages/py/base/ac-settings    # 다른 프로젝트에서 단독으로
```

## 최소 사용 예

```python
>>> from agent_console_settings import Layer, resolve_layers, set_at, unset_at

>>> layers = [
...     Layer("common", "공통", {"model": "m1", "limits": {"directories": ["/w"]}}),
...     Layer("team", "팀 구성", {"model": "m2"}),
...     Layer("node", "이 팀의 노드", {"limits": {"commands": ["ls"]}}),
... ]
>>> schema = {"properties": {"limits": {"x-merge": "replace"}}}  # 보통은 Pydantic 모델의 JSON Schema

>>> resolve_layers(layers, schema=schema).value  # 스키마 주석: limits는 통째로 대체
{'model': 'm2', 'limits': {'commands': ['ls']}}
>>> r = resolve_layers(layers, schema=schema, rules={"/limits": "merge"})  # 사용자 규칙이 우선
>>> r.value
{'model': 'm2', 'limits': {'directories': ['/w'], 'commands': ['ls']}}
>>> r.source_of("/model"), r.source_of("/limits/directories/0"), r.layers_under("/limits")
('team', 'common', ['common', 'node'])
>>> r.issues  # 모르는 전략 이름·형태 불일치(병합은 대체 동작으로 계속)
()

>>> node = set_at(layers[2].value, "/model", "m3")  # 이 층에서 덮어쓰기
>>> node
{'limits': {'commands': ['ls']}, 'model': 'm3'}
>>> unset_at(node, "/model")  # 상속으로 되돌리기(비게 된 상위 객체도 정리)
{'limits': {'commands': ['ls']}}

```

### 전략 추가(확장 지점)

```python
>>> from agent_console_settings import TracedValue, default_strategies

>>> def keep_first(base, incoming, ctx, /):
...     """먼저 지정한 층이 이긴다."""
...     return base if base is not None else TracedValue.stamp(incoming, ctx.layer)

>>> table = default_strategies()  # 새 표(DEFAULT_STRATEGIES는 얼어 있어 등록 불가)
>>> table.register("keep_first", keep_first)
>>> resolve_layers(layers, rules={"/model": "keep_first"}, strategies=table).value["model"]
'm1'

```

전략은 `(base: TracedValue | None, incoming, ctx: MergeContext) -> TracedValue`다. 객체 안으로 내려갈 때는
`ctx.merge_child(key, base_child, incoming_child)`를 부르면 그 하위 위치의 규칙을 다시 찾는다. 문제는
`ctx.report(code, message)`로 남긴다. 출처는 `TracedValue.stamp(value, layer)`·`object(...)`·`array(...)`로
만들면 자동으로 따라간다. 테스트의 `keyed_attachments`(첨부 `add`·`replace`·`remove`)가 예제다.

### 넓힘 경고

```python
>>> from agent_console_settings import find_widenings

>>> schema = {
...     "properties": {
...         "limits": {
...             "properties": {
...                 "directories": {"x-widen": "path_subset"},
...                 "commands": {"x-widen": "subset"},
...                 "network": {"x-widen": {"kind": "order", "order": ["deny", "allow"]}},
...             }
...         }
...     }
... }
>>> wide = [
...     Layer("common", "공통", {"limits": {"directories": ["/w"], "network": "deny"}}),
...     Layer("node", "이 팀의 노드", {"limits": {"directories": ["/w", "/etc"], "network": "allow"}}),
... ]
>>> for w in find_widenings(wide, schema=schema):
...     print(w.layer, "이", w.upper_layer, "보다", w.pointer, "을 넓힘:", w.added)
node 이 common 보다 /limits/directories 을 넓힘: ('/etc',)
node 이 common 보다 /limits/network 을 넓힘: ('allow',)

```

비교기는 `DEFAULT_WIDEN_CHECKS`(`subset`·`path_subset`·`order`)에 더해 `comparators=`로 넘길 수 있다.

### 문서 비교(버전 비교, design §2R.9)

```python
>>> from agent_console_settings import diff_digests, diff_documents

>>> changes = diff_documents(
...     {"nodes": [{"id": "a"}, {"id": "b", "label": "B"}], "env": {"TOKEN": "x1"}},
...     {"nodes": [{"id": "b", "label": "B2"}], "env": {"TOKEN": "x2"}},
...     before_secrets=["/env/TOKEN"],  # 문서별 비밀 위치(JSON Pointer) -- 판정은 호출자 몫
...     after_secrets=["/env/TOKEN"],
... )
>>> for c in changes:  # 목록 원소는 jsonpatch처럼 위치로 맞춰 비교한다(id로 짝을 짓지 않는다)
...     print(c.op, c.path, c.secret)
add /nodes/0/label False
replace /nodes/0/id False
remove /nodes/1 False
replace /env/TOKEN True
>>> changes[-1].before, changes[-1].after  # 비밀 값은 mask만 나온다
('***', '***')
>>> [(d.path, d.before, d.after) for d in diff_digests({"a.md": "sha1"}, {"a.md": "sha2", "b.md": "sha3"})]
[('a.md', 'sha1', 'sha2'), ('b.md', None, 'sha3')]

```

- 경로는 **원래 문서 기준** RFC 6901 JSON Pointer다: `remove`·`replace`는 이전 문서, `add`는 이후 문서
  (`replace`가 이전 문서에 없던 원소 안이면 이후 문서). jsonpatch 패치는 차례로 적용하는 형식이라 중간 상태
  기준 번호가 나오는데, 패치를 직접 적용하며 목록 원소의 원래 위치를 따라가 바꾼다. `move`는 `remove`+`add`,
  `copy`는 `add`로 바꾼다.
- 비밀 위치는 비교 전에 내용 해시 표식으로 바꿔 둔다. 값이 바뀌었는지는 알 수 있고 결과에는 `mask`(기본
  `***`)만 나온다(`secret=True`). 바뀐 값 **안쪽**에 비밀 위치가 있으면 그 부분만 `mask`로 바뀌고
  `secret=False`다. 비밀 판정(스키마 `x-secret`, 의심 규칙)은 이 패키지가 모른다 -- 호출자가 위치를 넘긴다.

새 의존: **`jsonpatch`**(python-json-patch, BSD-3) -- 무엇을: 두 JSON 문서의 RFC 6902 패치 계산. 왜: 목록
변경(가운데 삭제·추가·이동)을 짧은 패치로 만드는 검증된 구현. 대안: `deepdiff`(무겁고 경로 형식이 JSON
Pointer가 아님), 직접 구현(목록 정렬 알고리즘을 새로 써야 함), `jsondiff`(유지보수 약함).

## 출처 규칙

- 한 층이 통째로 정한 값은 그 아래 모든 위치가 그 층이다.
- 여러 층이 합쳐 만든 컨테이너(객체 병합·목록 이어 붙이기 등)의 출처는 **마지막으로 기여한 층**이고,
  잎·원소는 각자의 층이다. 섞인 컨테이너는 `layers_under(pointer)`로 기여한 층 전체를 본다.
- `union`·`intersect`는 남은 원소의 처음 출처를 유지한다.

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-settings`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
UV_LINK_MODE=copy uv run pytest packages/py/base/ac-settings
```
