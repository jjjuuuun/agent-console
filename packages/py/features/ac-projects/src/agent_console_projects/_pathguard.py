"""경로 지킴(design §PI.5 K33-7, X33): 설정 값 중 경로를 찾아 프로젝트 폴더 밖이면 알린다.

- 어떤 필드가 경로인지는 JSON Schema 주석 `x-path`(`directory`·`file`)로만 안다. 필드 이름을 코드에
  두지 않는다 — 새 백엔드·노드 옵션은 주석만 달면 지킴 대상이 된다. 목록 필드에 달면 각 항목이
  경로다.
- 상대 경로는 프로젝트 폴더 기준, 절대 경로는 프로젝트 폴더나 `allowed`(앱 workspace·상태 폴더처럼
  앱이 만드는 폴더) 안이어야 한다. `~`는 홈으로 펼쳐 같은 규칙.
- 파일 시스템을 읽지 않는다(문자열 규칙). 링크를 풀어 보려면 `realpath`를 주입한다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from agent_console_contracts import X_PATH, OutsideFolderPath
from agent_console_local_folders import PathFlavor

from ._paths import PathRules, absolute_path, folder_within, host_flavor

__all__ = ["PathField", "outside_paths", "path_fields"]

_MAX_REF_HOPS: Final = 32
_NO_ENV: Final[Mapping[str, str]] = {}


@dataclass(frozen=True, slots=True)
class PathField:
    """설정 값 안의 경로 값 하나.

    Attributes:
        pointer: 값의 위치(JSON Pointer, `value` 기준).
        value: 적힌 문자열 그대로.
        kind: `x-path` 값(`directory`·`file`, 열린 문자열).
    """

    pointer: str
    value: str
    kind: str


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _lookup_ref(root: Mapping[str, Any], ref: str) -> Mapping[str, Any] | None:
    if not ref.startswith("#"):
        return None  # 바깥 문서 참조는 풀지 않는다
    node: Any = root
    for raw in ref[1:].split("/")[1:] if ref != "#" else []:
        token = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, Mapping) or token not in node:
            return None
        node = node[token]
    return node if isinstance(node, Mapping) else None


def _expand(schema: Any, root: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """스키마 하나 → `$ref`를 풀고 `anyOf`·`oneOf`·`allOf`를 편 후보 목록."""
    out: list[Mapping[str, Any]] = []
    stack: list[tuple[Any, int]] = [(schema, 0)]
    while stack:
        node, hops = stack.pop()
        if not isinstance(node, Mapping) or hops > _MAX_REF_HOPS:
            continue
        out.append(node)
        ref = node.get("$ref")
        if isinstance(ref, str):
            target = _lookup_ref(root, ref)
            if target is not None:
                stack.append((target, hops + 1))
        for key in ("anyOf", "oneOf", "allOf"):
            subs = node.get(key)
            if isinstance(subs, list):
                stack.extend((s, hops + 1) for s in reversed(subs))
    return out


def _kind_of(cands: Sequence[Mapping[str, Any]]) -> str | None:
    for c in cands:
        kind = c.get(X_PATH)
        if isinstance(kind, str) and kind:
            return kind
    return None


def _walk(
    cands: list[Mapping[str, Any]],
    value: Any,
    pointer: str,
    inherited: str | None,
    root: Mapping[str, Any],
    out: list[PathField],
) -> None:
    kind = _kind_of(cands) or inherited
    if isinstance(value, str):
        if kind and value.strip():
            out.append(PathField(pointer=pointer, value=value, kind=kind))
        return
    if isinstance(value, list):
        items: list[Mapping[str, Any]] = []
        for c in cands:
            items.extend(_expand(c.get("items"), root))
        for i, item in enumerate(value):
            _walk(items, item, f"{pointer}/{i}", kind, root, out)
        return
    if isinstance(value, Mapping):
        for key, sub in value.items():
            subs: list[Mapping[str, Any]] = []
            for c in cands:
                props = c.get("properties")
                if isinstance(props, Mapping) and key in props:
                    subs.extend(_expand(props[key], root))
            if not subs:
                for c in cands:
                    extra = c.get("additionalProperties")
                    if isinstance(extra, Mapping):
                        subs.extend(_expand(extra, root))
            if subs:
                _walk(subs, sub, f"{pointer}/{_escape(str(key))}", None, root, out)


def path_fields(schema: Mapping[str, Any], value: Any) -> list[PathField]:
    """`value`에서 스키마가 `x-path`로 표시한 문자열 값(빈 값 제외)을 찾는다.

    `$ref`(문서 안 `#/...`)·`anyOf`·`oneOf`·`allOf`·`properties`·`additionalProperties`·`items`를
    따라간다. 필드 이름은 보지 않는다.

    >>> schema = {"type": "object", "properties": {
    ...     "cwd": {"type": "string", "x-path": "directory"},
    ...     "dirs": {"type": "array", "items": {"type": "string"}, "x-path": "directory"},
    ...     "model": {"type": "string"}}}
    >>> [(f.pointer, f.value) for f in path_fields(schema, {"cwd": "src", "dirs": ["/a", ""],
    ...                                                     "model": "/not/a/path"})]
    [('/cwd', 'src'), ('/dirs/0', '/a')]
    """
    out: list[PathField] = []
    _walk(_expand(schema, schema), value, "", None, schema, out)
    return out


def _resolve(
    raw: str,
    root: str,
    fl: PathFlavor,
    placeholders: Mapping[str, str],
    environ: Mapping[str, str],
) -> str | None:
    text = raw.strip()
    for name, replacement in placeholders.items():
        text = text.replace("{" + name + "}", replacement)
    return absolute_path(text, root, flavor=fl, environ=environ)


def outside_paths(
    value: Any,
    schema: Mapping[str, Any],
    root: str,
    allowed: Iterable[str] = (),
    *,
    flavor: PathFlavor | None = None,
    rules: PathRules | None = None,
    placeholders: Mapping[str, str] | None = None,
    environ: Mapping[str, str] = _NO_ENV,
    realpath: Callable[[str], str] | None = None,
    layer: str | None = None,
    node_id: str | None = None,
    pointer_prefix: str = "",
) -> list[OutsideFolderPath]:
    """`x-path` 값 중 프로젝트 폴더(`root`)·`allowed` 밖을 가리키는 것(K33-7, 422 `outside_folder`).

    Args:
        value: 설정 값(예: 한 층의 `AgentSettings` dict, 백엔드 옵션 dict).
        schema: 그 값의 JSON Schema(`x-path` 주석이 달린).
        root: 프로젝트 폴더(정규화한 절대 경로). 상대 경로는 이 폴더 기준이다.
        allowed: 함께 허용하는 폴더(앱 workspace·상태 폴더 등, 정규화한 절대 경로).
        flavor: 경로 방식(기본 = 이 프로세스).
        rules: 경로 비교 규칙(대소문자 무시 앞부분).
        placeholders: 값 안의 `{이름}`을 먼저 바꿀 표(예: `{"workspace": root}`). 표에 없는 틀은
            글자 그대로 남는다(대개 상대 경로로 보여 폴더 안이 된다 — 실행 때 바꾸는 틀은 여기에
            넣는다).
        environ: `~` 펼치기용 환경(없으면 `~`는 풀 수 없어 밖으로 본다).
        realpath: 링크를 풀 함수(주입, 선택). 주면 푼 경로로도 확인한다.
        layer: 결과에 적을 설정 층 이름(열린 문자열).
        node_id: 결과에 적을 노드 id.
        pointer_prefix: 결과 `pointer` 앞에 붙일 위치(예: `/settings`).

    Returns:
        밖을 가리키는 값 목록(`resolved`는 푼 절대 경로, 풀 수 없으면 None).

    >>> schema = {"properties": {"working_directory": {"x-path": "directory"},
    ...                          "extra": {"items": {"x-path": "file"}}}}
    >>> value = {"working_directory": "../other", "extra": ["/srv/app/state/x", "a.md"]}
    >>> bad = outside_paths(value,
    ...                     schema, "/w/app", ["/srv/app/state"], flavor="posix", layer="팀")
    >>> [(p.value, p.resolved, p.pointer, p.layer) for p in bad]
    [('../other', '/w/other', '/working_directory', '팀')]
    """
    fl = flavor or host_flavor()
    roots = [root, *allowed]
    subs = dict(placeholders or {})
    out: list[OutsideFolderPath] = []
    for field in path_fields(schema, value):
        resolved = _resolve(field.value, root, fl, subs, environ)
        inside = resolved is not None and any(
            folder_within(resolved, r, flavor=fl, rules=rules) for r in roots
        )
        if inside and realpath is not None and resolved is not None:
            try:
                real = realpath(resolved)
            except (OSError, ValueError):
                real = resolved
            inside = any(folder_within(real, r, flavor=fl, rules=rules) for r in roots)
        if not inside:
            out.append(
                OutsideFolderPath(
                    value=field.value,
                    resolved=resolved,
                    pointer=pointer_prefix + field.pointer,
                    layer=layer,
                    node_id=node_id,
                )
            )
    return out
