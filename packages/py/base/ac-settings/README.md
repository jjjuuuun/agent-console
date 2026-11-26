# agent-console-settings

A pure library for **layer merging** of settings, **per-value provenance tracking**, and **comparison** of two definition documents. It has no internal dependencies; its only external dependency is `jsonpatch`, for document comparison.

- Layers (for example common → team → agent → node) are a **data list** the caller passes in. The number, names, and fields of layers are free.
- Default rules: scalars and lists are **replaced**, objects are **merged recursively per key**. An omitted key inherits; a present value (including `null` and empty lists) is set at that layer.
- Per-field exceptions are data: the JSON Schema annotation `x-merge` (default) < `rules={JSON Pointer: strategy name}` (user setting `settings_merge`).
- Strategies are a table registered by name. The defaults are `replace`, `merge`, `append`, `union`, `intersect`. No field names are in the code.
- The result's `provenance` is `{JSON Pointer: layer id}`: which layer each leaf value and list element came from.
- `find_widenings`: whether a lower layer widened a range set by an upper layer (for warnings). The comparison locations are data too (`x-widen` annotations or `checks`).
- `set_at`/`unset_at`: helpers that apply the screen's "override at this layer" and "revert to inherited" to a layer value (the original is not changed).

Resource attachments use the same layer merge rules.

## Installation

```bash
uv sync --all-packages                      # inside the workspace
uv pip install ./packages/py/base/ac-settings    # standalone, from another project
```

## Minimal usage

```python
>>> from agent_console_settings import Layer, resolve_layers, set_at, unset_at

>>> layers = [
...     Layer("common", "공통", {"model": "m1", "limits": {"directories": ["/w"]}}),
...     Layer("team", "팀 구성", {"model": "m2"}),
...     Layer("node", "이 팀의 노드", {"limits": {"commands": ["ls"]}}),
... ]
>>> schema = {"properties": {"limits": {"x-merge": "replace"}}}  # usually the JSON Schema of a Pydantic model

>>> resolve_layers(layers, schema=schema).value  # schema annotation: limits is replaced as a whole
{'model': 'm2', 'limits': {'commands': ['ls']}}
>>> r = resolve_layers(layers, schema=schema, rules={"/limits": "merge"})  # user rules take precedence
>>> r.value
{'model': 'm2', 'limits': {'directories': ['/w'], 'commands': ['ls']}}
>>> r.source_of("/model"), r.source_of("/limits/directories/0"), r.layers_under("/limits")
('team', 'common', ['common', 'node'])
>>> r.issues  # unknown strategy names, shape mismatches (merging continues with replace)
()

>>> node = set_at(layers[2].value, "/model", "m3")  # override at this layer
>>> node
{'limits': {'commands': ['ls']}, 'model': 'm3'}
>>> unset_at(node, "/model")  # revert to inherited (parent objects left empty are cleaned up too)
{'limits': {'commands': ['ls']}}

```

### Adding strategies (extension point)

```python
>>> from agent_console_settings import TracedValue, default_strategies

>>> def keep_first(base, incoming, ctx, /):
...     """The layer that set it first wins."""
...     return base if base is not None else TracedValue.stamp(incoming, ctx.layer)

>>> table = default_strategies()  # a new table (DEFAULT_STRATEGIES is frozen and cannot be registered into)
>>> table.register("keep_first", keep_first)
>>> resolve_layers(layers, rules={"/model": "keep_first"}, strategies=table).value["model"]
'm1'

```

A strategy is `(base: TracedValue | None, incoming, ctx: MergeContext) -> TracedValue`. To descend into an object, call
`ctx.merge_child(key, base_child, incoming_child)` and the rules for that child location are looked up again. Report problems
with `ctx.report(code, message)`. Provenance follows automatically when you build values with `TracedValue.stamp(value, layer)`, `object(...)`, and `array(...)`.
The test helper `keyed_attachments` (attachment `add`, `replace`, `remove`) is an example.

### Widening warnings

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

Comparators can be passed with `comparators=` in addition to `DEFAULT_WIDEN_CHECKS` (`subset`, `path_subset`, `order`).

### Document comparison (version comparison)

```python
>>> from agent_console_settings import diff_digests, diff_documents

>>> changes = diff_documents(
...     {"nodes": [{"id": "a"}, {"id": "b", "label": "B"}], "env": {"TOKEN": "x1"}},
...     {"nodes": [{"id": "b", "label": "B2"}], "env": {"TOKEN": "x2"}},
...     before_secrets=["/env/TOKEN"],  # secret locations per document (JSON Pointer); judging them is up to the caller
...     after_secrets=["/env/TOKEN"],
... )
>>> for c in changes:  # list elements are matched by position like jsonpatch (not paired by id)
...     print(c.op, c.path, c.secret)
add /nodes/0/label False
replace /nodes/0/id False
remove /nodes/1 False
replace /env/TOKEN True
>>> changes[-1].before, changes[-1].after  # secret values come out only as the mask
('***', '***')
>>> [(d.path, d.before, d.after) for d in diff_digests({"a.md": "sha1"}, {"a.md": "sha2", "b.md": "sha3"})]
[('a.md', 'sha1', 'sha2'), ('b.md', None, 'sha3')]

```

- Paths are RFC 6901 JSON Pointers **relative to the original document**: `remove` and `replace` refer to the before document, `add` to the after document
  (if a `replace` is inside an element that was not in the before document, the after document). jsonpatch patches are meant to be applied in sequence, so their indexes refer to intermediate states;
  this package applies the patch itself and follows each list element's original position to rewrite them. `move` becomes `remove` + `add`,
  and `copy` becomes `add`.
- Secret locations are replaced with a content-hash marker before comparison. You can tell whether a value changed, and the result shows only `mask` (default
  `***`) (`secret=True`). If a secret location is **inside** a changed value, only that part becomes `mask` and
  `secret=False`. This package does not judge secrets (schema `x-secret`, suspicion rules); the caller passes the locations.

New dependency: **`jsonpatch`** (python-json-patch, BSD-3). What: computes RFC 6902 patches between two JSON documents. Why: a proven implementation that turns list
changes (deleting, adding, or moving in the middle) into short patches. Alternatives: `deepdiff` (heavy, and its path format is not JSON
Pointer), writing it ourselves (a new list alignment algorithm), `jsondiff` (weakly maintained).

## Provenance rules

- A value set as a whole by one layer belongs to that layer at every location below it.
- The provenance of a container built from several layers (merged objects, concatenated lists, and so on) is **the last layer that contributed**,
  while leaves and elements keep their own layers. For a mixed container, `layers_under(pointer)` shows every contributing layer.
- `union` and `intersect` keep the first provenance of the remaining elements.

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-settings`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
UV_LINK_MODE=copy uv run pytest packages/py/base/ac-settings
```
