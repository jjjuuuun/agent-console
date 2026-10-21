"""리소스 정의 하나를 등록된 종류로 검사한다(저장 전 검사용, design §R12.3·§R9.5).

종류 이름은 이 모듈에 없다. 종류를 레지스트리에서 찾아 그 `validate`를 부르고,
이슈 메시지에 config 값이 새지 않도록 이슈가 가리키는 위치의 값을 메시지에서 지운다
(플러그인 종류가 실수로 값을 메시지에 넣어도 응답·로그에 남지 않게).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from agent_console_contracts import Issue, Resource, ResourceAttachment
from agent_console_registry import Registry, UnknownExtensionError
from agent_console_secret_rules import SecretRules, default_rules

from ._base import effective_resource
from ._interfaces import ResourceLookup, ResourceType

MASK = "***"
"""메시지에서 값을 지운 자리에 넣는 표시."""

MIN_SCRUB_LENGTH = 3
"""이보다 짧은 값은 지우지 않는다(한두 글자를 지우면 메시지 자체가 망가진다)."""


def _unescape(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def value_at(document: Any, pointer: str | None) -> Any:
    """JSON Pointer(`/env/API_KEY`)가 가리키는 값. 없거나 잘못된 포인터면 None."""
    if not pointer:
        return None
    if not pointer.startswith("/"):
        return None
    node = document
    for raw in pointer[1:].split("/"):
        token = _unescape(raw)
        if isinstance(node, dict):
            if token not in node:
                return None
            node = node[token]
        elif isinstance(node, list):
            if not token.isdigit() or int(token) >= len(node):
                return None
            node = node[int(token)]
        else:
            return None
    return node


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def scrub_issue_values(issues: Iterable[Issue], config: Any) -> list[Issue]:
    """이슈 `path`가 config 안의 값을 가리키면 그 값(문자열들)을 메시지에서 `***`로 바꾼다.

    Args:
        issues: 종류가 낸 이슈.
        config: 검사한 리소스의 `config`(이슈 `path`의 기준 문서).

    Returns:
        메시지만 바꾼 이슈 사본 목록(path·code·details는 그대로).
    """
    out: list[Issue] = []
    for issue in issues:
        secrets = sorted(
            {s for s in _strings(value_at(config, issue.path)) if len(s) >= MIN_SCRUB_LENGTH},
            key=len,
            reverse=True,
        )
        message = issue.message
        for s in secrets:
            message = message.replace(s, MASK)
        changed = message != issue.message
        out.append(issue.model_copy(update={"message": message}) if changed else issue)
    return out


def validate_resource(resource: Resource, types: Registry[ResourceType]) -> list[Issue]:
    """리소스 정의를 그 종류의 `validate`로 검사한다(저장 전 검사).

    Args:
        resource: 검사할 리소스 정의.
        types: 리소스 종류 레지스트리(key = 리소스 `type`).

    Returns:
        이슈 목록. 종류가 등록되지 않았으면 warning `resource.unknown_type` 하나(나중에 플러그인을
        설치할 수 있으므로 저장을 막을지는 호출자가 정한다). 종류 검사가 예외를 던지면 error
        `resource.type_failed`. 메시지에는 config 값이 들어가지 않는다(`scrub_issue_values`).
    """
    details = {"resource": resource.id, "resource_type": resource.type}
    try:
        rtype = types.get(resource.type)
    except UnknownExtensionError:
        return [
            Issue(
                severity="warning",
                code="resource.unknown_type",
                message="등록되지 않은 리소스 종류입니다",
                details=details,
            )
        ]
    try:
        found = list(rtype.validate(resource))
    except Exception as exc:
        return [
            Issue(
                severity="error",
                code="resource.type_failed",
                message=f"리소스 종류 검사 중 오류: {type(exc).__name__}",
                details=details,
            )
        ]
    return scrub_issue_values(found, resource.config)


OVERRIDE_FIELD = "config_override"
"""첨부에서 config 덮어쓰기가 든 필드 이름(이슈 path에 쓴다)."""

OVERRIDE_SECRET_SUSPECTED = "resource.override_secret_suspected"
"""리소스를 모르는 첨부의 덮어쓰기에 비밀로 의심되는 평문이 있음(error)."""


def _overridden(override: dict[str, Any], config_path: str | None) -> bool:
    """이슈 path(config 기준)가 덮어쓴 최상위 키 아래인가."""
    if not config_path or not config_path.startswith("/"):
        return False
    return _unescape(config_path[1:].split("/", 1)[0]) in override


def _override_path(root: str, override: dict[str, Any], config_path: str | None) -> str:
    """config 기준 이슈 path → 덮어쓰기 기준(`<root>/...`, root = 덮어쓰기 위치).

    이슈가 덮어쓴 최상위 키 아래가 아니면 덮어쓰기 자체(`<root>`)를 가리킨다.
    """
    return root + (config_path or "") if _overridden(override, config_path) else root


def validate_attachment(
    attachment: ResourceAttachment,
    *,
    types: Registry[ResourceType],
    resources: ResourceLookup,
    path: str = "",
    override_path: str | None = None,
    ref_path: str | None = None,
    secret_rules: SecretRules | None = None,
) -> list[Issue]:
    """첨부의 `config_override`를 리소스 config에 얕게 덮어쓴 결과를 종류 검사로 검사한다.

    덮어쓰기가 만든 문제만 낸다: 리소스 자체에도 있는 이슈(같은 code·path)는 그 리소스의 문제이므로
    여기서 내지 않는다(단, 덮어쓴 키 아래의 이슈는 항상 낸다). 덮어쓰기가 없으면 빈 목록.

    Args:
        attachment: 검사할 첨부.
        types: 리소스 종류 레지스트리.
        resources: 리소스 정의 조회.
        path: 문서 안 첨부 위치 JSON Pointer(예: `/resources/0`).
        override_path: 덮어쓰기 위치(기본 `<path>/config_override`). 첨부가 다른 모양(예: 연결
            config)에서 왔을 때 지정한다.
        ref_path: 리소스 id 위치(기본 `<path>/ref`).
        secret_rules: 리소스가 없을 때 쓰는 비밀 의심 규칙(`ac-secret-rules`, 기본 규칙 +
            사용자 추가분). 없으면 기본 규칙.

    Returns:
        이슈 목록. path는 `<override_path>/...`(덮어쓴 키 아래면 그 위치). 리소스가 없으면
        warning `resource.not_found`(path = ref 위치)와, 비밀 의심 규칙
        (`secret_rules`)에 걸린 값마다 error
        `resource.override_secret_suspected`(path = 그 값 위치). 종류가 없으면 warning
        `resource.unknown_type`(ref 위치). 메시지에는 값이 없다(`scrub_issue_values`).
    """
    override = attachment.config_override
    if not override:
        return []
    details = {"resource": attachment.ref}
    root = override_path if override_path is not None else f"{path}/{OVERRIDE_FIELD}"
    ref_at = ref_path if ref_path is not None else f"{path}/ref"
    resource = resources.get_resource(attachment.ref)
    if resource is None:
        # 종류(스키마)를 모르므로 비밀 의심 규칙으로 본다(리소스를 나중에 만드는 흐름은 허용).
        rules = secret_rules if secret_rules is not None else default_rules()
        suspected = [
            Issue(
                severity="error",
                code=OVERRIDE_SECRET_SUSPECTED,
                message="비밀로 의심되는 값입니다(리소스 없음). secret:// 참조를 쓰세요",
                path=finding.path,
                details=details,
            )
            for finding in rules.find_suspected(override, path=root)
        ]
        return [
            Issue(
                severity="warning",
                code="resource.not_found",
                message="리소스가 없어 종류 검사 대신 비밀 의심 규칙으로만 검사했습니다",
                path=ref_at,
                details=details,
            ),
            *suspected,
        ]
    effective = effective_resource(resource, attachment)
    found = validate_resource(effective, types)
    base = {(i.code, i.path) for i in validate_resource(resource, types)}
    out: list[Issue] = []
    for issue in found:
        if issue.code == "resource.unknown_type":
            out.append(issue.model_copy(update={"path": ref_at}))
            continue
        if (issue.code, issue.path) in base and not _overridden(override, issue.path):
            continue  # 리소스 자체의 문제(덮어쓰기와 무관)
        where = _override_path(root, override, issue.path)
        out.append(issue.model_copy(update={"path": where}))
    return out
