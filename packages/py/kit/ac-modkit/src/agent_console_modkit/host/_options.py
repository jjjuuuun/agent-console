"""모듈 옵션 읽기 전용 조회 `GET <prefix>/modules/{module_id}/options`와 YAML 조각(5.2R.29).

모듈 옵션은 설치자 설정 파일(``modules.options.<id>``)에서만 바꾼다. 쓰기 경로는 없다. 응답 모양은
호스트가 정한다(``payload``·``response_model`` 주입). 기본 본문은 ``ModuleOptions.to_dict()`` +
``yaml_snippet``이다.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from agent_console_modkit._assemble import Assembly
from agent_console_modkit._options import OPTIONS_MASK, SecretPathFinder, _mask_at

from ._security import DEFAULT_ERROR_STATUS, error_body

OPTIONS_KEY_PATH: tuple[str, ...] = ("modules", "options")
"""설정 파일에서 모듈 옵션이 놓이는 위치(그 아래 모듈 id)."""

NOT_FOUND = "not_found"


MASKED_LINE_NOTE = "<가린 값 — secret://이름으로 넣으세요>"
"""조각에서 가린 줄 뒤에 붙는 안내(그 줄은 주석이다)."""

_SENTINEL = "__agent_console_masked_{}__"


def _comment_masked_lines(text: str, sentinels: Mapping[str, None], root_depth: int) -> str:
    """가린 값 줄을 주석으로 바꾼다.

    가린 줄만 남은 객체·목록은 그 키 줄도 주석으로 바꾼다(붙여 넣으면 키가 빠져 기본값이 된다 —
    빈 ``{}``·``[]``나 null로 바뀌어 동작이 조용히 달라지지 않게). 모듈 id 줄(``root_depth``)만
    남으면 ``{}``(모두 기본값)로 닫는다.
    """
    lines: list[str] = []
    for line in text.splitlines():
        hit = next((sv for sv in sentinels if sv in line), None)
        if hit is None:
            lines.append(line)
            continue
        indent = line[: len(line) - len(line.lstrip())]
        body = line.strip().replace(f"'{hit}'", hit).replace(hit, MASKED_LINE_NOTE)
        lines.append(f"{indent}# {body}")

    def depth(line: str) -> int:
        return len(line) - len(line.lstrip())

    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        stripped = line.strip()
        if not stripped.endswith(":") or stripped.startswith("#"):
            continue
        children = []
        for nxt in lines[i + 1 :]:
            if nxt.strip() and depth(nxt) <= depth(line):
                break
            children.append(nxt.strip())
        if not children or not all(c.startswith("#") for c in children):
            continue
        if depth(line) == root_depth:
            lines[i] = f"{line} {{}}"
        else:
            lines[i] = f"{line[: depth(line)]}# {stripped}"
    return "\n".join(lines) + "\n"


def options_yaml_snippet(
    module_id: str,
    values: Mapping[str, Any],
    *,
    masked: Sequence[str] = (),
    key_path: Sequence[str] = OPTIONS_KEY_PATH,
) -> str:
    """설정 파일에 붙일 YAML 조각(``modules: options: <id>: …``, 들여쓰기 2칸).

    가린 위치(``masked``)의 줄은 **주석**으로 낸다(``# token: <가린 값 — secret://이름으로
    넣으세요>``). 그대로 붙여 넣어도 비밀 원문이나 가림 문자열이 설정 값이 되지 않는다(그 키는 빠져
    기본값이 된다). 가린 줄만 남은 객체·목록은 그 키 줄도 주석으로 바꾼다(빈 값·null로 조용히
    바뀌지 않게). 모듈 값 전체가 가려지면 ``<id>: {}``(모두 기본값)다.

    Args:
        module_id: 모듈 id.
        values: 지금 값(가린 자리 값은 무엇이든 쓰지 않는다).
        masked: 가린 위치(JSON Pointer).
        key_path: 모듈 id 위의 키 경로.

    Returns:
        끝에 줄바꿈이 있는 YAML 문자열. 값이 비면 ``<id>: {}``.

    >>> print(options_yaml_snippet("mod-x", {"limit": 3, "names": ["a"]}), end="")
    modules:
      options:
        mod-x:
          limit: 3
          names:
            - a
    """
    from ruamel.yaml import YAML

    copy: dict[str, Any] = json.loads(json.dumps(dict(values), default=str))
    sentinels: dict[str, None] = {}
    for i, pointer in enumerate(masked):
        mark = _SENTINEL.format(i)
        if _mask_at(copy, pointer, mark):
            sentinels[mark] = None
    doc: Any = {module_id: copy}
    for key in reversed(list(key_path)):
        doc = {key: doc}
    yaml = YAML(typ="safe", pure=True)
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096
    buf = io.StringIO()
    yaml.dump(doc, buf)
    text = buf.getvalue()
    if not sentinels:
        return text
    return _comment_masked_lines(text, sentinels, root_depth=2 * len(list(key_path)))


def default_module_options_payload(
    assembly: Assembly,
    *,
    secret_paths: Callable[[], SecretPathFinder | None] | None = None,
    hide_paths: Callable[[], bool] | None = None,
    mask: str = OPTIONS_MASK,
) -> Callable[[str], dict[str, Any] | None]:
    """``assembly.module_options`` → dict 본문(``{module_id, schema, values, yaml_snippet}``).

    Args:
        assembly: 조립 결과(꺼진 모듈의 옵션도 보인다).
        secret_paths: 부를 때마다 비밀 의심 위치 함수를 돌려준다(포트처럼 늦게 정해지는 것용).
        hide_paths: 부를 때마다 경로 필드를 가릴지.
        mask: ``values``의 가린 자리 문자열(호스트가 쓰는 비밀 규칙의 가림 문자열과 맞춘다).
    """

    def payload(module_id: str) -> dict[str, Any] | None:
        view = assembly.module_options(
            module_id,
            secret_paths=secret_paths() if secret_paths is not None else None,
            hide_paths=hide_paths() if hide_paths is not None else False,
            mask=mask,
        )
        if view is None:
            return None
        body = view.to_dict()
        body["yaml_snippet"] = (
            options_yaml_snippet(view.module_id, view.values, masked=view.masked)
            if view.schema is not None
            else ""
        )
        return body

    return payload


def build_module_options_router(
    *,
    payload: Callable[[str], Any | None],
    prefix: str = "",
    response_model: Any = None,
    responses: Mapping[int | str, dict[str, Any]] | None = None,
    error_status: Mapping[str, int] = DEFAULT_ERROR_STATUS,
) -> APIRouter:
    """`GET <prefix>/modules/{module_id}/options` 라우터(읽기 전용).

    Args:
        payload: 모듈 id → 응답 본문(모르는 id면 None → 404 ``not_found``).
        prefix: API 접두.
        response_model: OpenAPI·검증용 응답 모델.
        responses: OpenAPI 추가 응답 문서.
        error_status: 오류 코드 → HTTP 상태.
    """
    router = APIRouter(prefix=prefix)

    @router.get(
        "/modules/{module_id}/options",
        response_model=response_model,
        responses=dict(responses or {}),
    )
    async def module_options(module_id: str) -> Any:
        """모듈 옵션(스키마·가린 지금 값·설정 파일용 YAML 조각). 바꾸려면 설정 파일을 고친다."""
        body = payload(module_id)
        if body is None:
            return Response(
                content=error_body(NOT_FOUND, f"모듈이 없습니다: {module_id}"),
                status_code=error_status.get(NOT_FOUND, 404),
                media_type="application/json",
                headers={"cache-control": "no-store"},
            )
        return body

    return router


__all__ = [
    "MASKED_LINE_NOTE",
    "OPTIONS_KEY_PATH",
    "build_module_options_router",
    "default_module_options_payload",
    "options_yaml_snippet",
]
