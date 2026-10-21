"""`skill` 종류: 여러 파일 본문(SKILL.md + 부속 파일)을 가진 skill 하나(design §2R.8).

칸 `skills` = `{name, files: [{name, content, encoding, media_type?}]}` 목록. 이 종류는 파일을
쓰지 않는다 — 항목의 `files`를 실행 폴더에 쓰고 경로로 바꾸는 일은 agent 노드가 한다
(`ac-nodes-core.write_item_trees`). 어느 파일이 "주 파일"인지는 이 종류가 정하지 않는다(파일 이름은
본문 폴더의 상대 경로 그대로다). 실행 백엔드가 그 폴더를 자기 형식으로 전달한다.
"""

from __future__ import annotations

import base64
import mimetypes
import re
from collections.abc import Mapping
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

from .file import safe_relative_name

__all__ = ["SKILL_NAME_PATTERN", "SkillType", "skill_files", "skill_name"]

SKILL_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
"""skill 이름 형식(폴더 이름으로도 안전한 문자만). 비우면 리소스 id를 쓴다."""

_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "pattern": SKILL_NAME_PATTERN,
            "title": "skill 이름",
            "description": (
                "에이전트가 보는 skill 이름(폴더 이름)입니다. 비우면 리소스 id를 씁니다."
            ),
            **x_ui(
                tier="basic",
                when="에이전트가 부를 skill 이름을 알아보기 쉽게 하고 싶을 때 바꾸세요.",
                example="release-notes",
            ),
        },
    },
    "additionalProperties": False,
}


def skill_name(resource: Resource) -> str:
    """config `name`, 없으면 리소스 id."""
    configured = resource.config.get("name")
    return configured if isinstance(configured, str) and configured else resource.id


def _entry(path: str, data: bytes) -> dict[str, Any]:
    try:
        body, encoding = data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        body, encoding = base64.b64encode(data).decode("ascii"), "base64"
    entry: dict[str, Any] = {"name": path, "content": body, "encoding": encoding}
    media_type = mimetypes.guess_type(path)[0]
    if path.lower().endswith(".md"):
        media_type = "text/markdown"
    if media_type:
        entry["media_type"] = media_type
    return entry


def skill_files(content: Content) -> list[dict[str, Any]]:
    """여러 파일 본문 → 파일 항목 목록(경로 순). 안전하지 않은 경로는 뺀다."""
    if not isinstance(content, Mapping):
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(content):
        data = content[path]
        if not isinstance(path, str) or not safe_relative_name(path):
            continue
        out.append(_entry(path, bytes(data)))
    return out


class SkillType(SchemaResourceType):
    """여러 파일 skill. `skills` 칸에 `{name, files}` 한 항목을 낸다."""

    descriptor = ResourceTypeDescriptor(
        id="skill",
        version=1,
        title="Skill",
        description="SKILL.md와 부속 파일(스크립트·참고 문서)로 된 skill. "
        "실행 폴더에 복사돼 실행 백엔드가 전달한다.",
        config_schema=_CONFIG_SCHEMA,
        content=ResourceContentSpec(
            media_types=["text/markdown", "text/plain"], editor="markdown", multi_file=True
        ),
        slot_key="name",
        combine="append",
        contributes=[KnownResourceSlots.SKILLS],
        ui_hints=UiHints(icon="스"),
    )

    def extra_issues(self, resource: Resource) -> list[Issue]:
        """이름(리소스 id로 대신할 때 포함)이 형식에 맞지 않으면 오류."""
        if re.fullmatch(SKILL_NAME_PATTERN, skill_name(resource)):
            return []
        return [
            Issue(
                severity="error",
                code="resource.invalid_config",
                message="skill 이름은 영문·숫자·._- 로 된 64자 이하여야 합니다",
                path="/name",
                details={"resource": resource.id, "resource_type": resource.type},
            )
        ]

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        """`skills` 칸에 `[{name, files}]`. 파일이 없으면 기여하지 않는다."""
        files = skill_files(content)
        if not files:
            return []
        item: dict[str, Any] = {"name": skill_name(resource), "files": files}
        return [Contribution(KnownResourceSlots.SKILLS, [item])]
