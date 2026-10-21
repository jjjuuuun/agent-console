"""`file` 종류: 참고 파일(md·html·텍스트 등).

칸 `files` = `{name, content, encoding, media_type}` 목록. 이 종류는 파일을 쓰지 않는다 —
실행 폴더에 쓰고 경로를 넘기는 일은 agent 노드가 한다(design §R12.4).
`name`은 실행 폴더 기준 상대 경로이며 쓰는 쪽에서도 폴더 밖으로 나가지 않는지 다시 확인해야 한다.
"""

from __future__ import annotations

import base64
from pathlib import PurePosixPath
from typing import Any

from agent_console_contracts import (
    Issue,
    KnownResourceSlots,
    Resource,
    ResourceContentSpec,
    ResourceTypeDescriptor,
    UiHints,
    x_ui,
)
from agent_console_resources import Content, ContributeContext, Contribution, SchemaResourceType

__all__ = ["FileType", "safe_relative_name"]

_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "minLength": 1,
            "title": "파일 이름",
            "description": (
                "에이전트 실행 폴더에 둘 상대 경로입니다. 비우면 본문 파일 이름을 씁니다."
            ),
            **x_ui(
                tier="basic",
                when="에이전트가 파일을 특정 경로에서 찾아야 할 때 바꾸세요.",
                example="docs/spec.md",
            ),
        },
        "media_type": {
            "type": "string",
            "title": "형식",
            "description": "파일 형식(MIME)입니다. 비우면 본문 파일의 형식을 씁니다.",
            **x_ui(tier="advanced", example="text/markdown"),
        },
    },
    "additionalProperties": False,
}


def safe_relative_name(name: str) -> bool:
    """상대 경로이고 `..`·드라이브·역슬래시·제어 문자(NUL 포함)가 없으면 참."""
    if not name or "\\" in name or ":" in name or name.startswith("/"):
        return False
    if any(ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F for ch in name):
        return False
    return all(part not in ("..", ".", "") for part in name.split("/"))


def _name_of(resource: Resource) -> str:
    configured = resource.config.get("name")
    if isinstance(configured, str) and configured:
        return configured
    if resource.content is not None:
        return PurePosixPath(resource.content.file.replace("\\", "/")).name
    return resource.id


class FileType(SchemaResourceType):
    """참고 파일 하나(본문 파일)를 `files` 칸에 낸다."""

    descriptor = ResourceTypeDescriptor(
        id="file",
        version=1,
        title="참고 파일",
        description="에이전트가 읽을 참고 파일(md·html·텍스트). 실행 폴더에 복사돼 전달된다.",
        config_schema=_CONFIG_SCHEMA,
        content=ResourceContentSpec(
            media_types=["text/markdown", "text/html", "text/plain", "application/json"],
            editor="text",
        ),
        slot_key="name",
        combine="append",
        contributes=[KnownResourceSlots.FILES],
        ui_hints=UiHints(icon="파"),
    )

    def extra_issues(self, resource: Resource) -> list[Issue]:
        """본문이 없거나 이름이 안전하지 않으면 이슈."""
        details = {"resource": resource.id, "resource_type": resource.type}
        issues: list[Issue] = []
        if resource.content is None:
            issues.append(
                Issue(
                    severity="error",
                    code="resource.content_missing",
                    message="파일 본문이 없습니다",
                    details=details,
                )
            )
        if not safe_relative_name(_name_of(resource)):
            issues.append(
                Issue(
                    severity="error",
                    code="resource.unsafe_path",
                    message="파일 이름은 실행 폴더 안의 상대 경로여야 합니다",
                    path="/name",
                    details=details,
                )
            )
        return issues

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        """`files` 칸에 `[{name, content, encoding, media_type}]`. 본문을 못 읽었으면 없음."""
        if content is None or not isinstance(content, str | bytes):
            return []  # 본문 없음, 또는 여러 파일 본문(이 종류는 단일 파일)
        if isinstance(content, bytes):
            try:
                body, encoding = content.decode("utf-8"), "utf-8"
            except UnicodeDecodeError:
                body, encoding = base64.b64encode(content).decode("ascii"), "base64"
        else:
            body, encoding = content, "utf-8"
        media_type = resource.config.get("media_type") or (
            resource.content.media_type if resource.content is not None else None
        )
        entry: dict[str, Any] = {"name": _name_of(resource), "content": body, "encoding": encoding}
        if media_type:
            entry["media_type"] = media_type
        return [Contribution(KnownResourceSlots.FILES, [entry])]
