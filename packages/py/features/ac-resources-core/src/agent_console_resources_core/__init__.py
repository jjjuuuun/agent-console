"""agent-console-resources-core: 기본 리소스 종류 플러그인(design §R12.3, §2R.8).

entry point `agent_console.resource_types`로만 등록된다. `ac-resources`는 이 이름들을 모른다.

공개 API:
    - ``InstructionType`` (`instruction` → 칸 `instructions`: 문자열 목록)
    - ``FileType`` (`file` → 칸 `files`: `{name, content, encoding, media_type}` 목록),
      ``safe_relative_name``
    - ``McpServerType`` (`mcp-server` → 칸 `mcp_servers`: `{name, type, command, args, env, url,
      headers}` 목록, 비밀은 `secret://`만), ``SECRET_FIELDS``
    - ``ToolPermissionType`` (`tool-permission` → 칸 `tools`: `{tools, disallowed_tools, commands}`
      목록), ``PERMISSION_FIELDS``
    - ``SkillType`` (`skill`, 여러 파일 본문 → 칸 `skills`: `{name, files}` 목록), ``skill_name``,
      ``skill_files``, ``SKILL_NAME_PATTERN``
    - ``RuleType`` (`rule` → 칸 `rules`: `{name, paths, text, instruction, files}` 목록, 받지 않는
      백엔드에는 대체 칸 `instructions`), ``render_rule_file``, ``DEFAULT_PATHS_HEADER``,
      ``DEFAULT_RULES_DIR``, ``RULE_NAME_PATTERN``
    - ``HookType`` (`hook` → 칸 `hooks`: `{name, event, matcher?, command, timeout_seconds?}` 목록,
      이벤트 이름은 자유 문자열), ``hook_config_schema``, ``DEFAULT_EVENT_EXAMPLES``
"""

from agent_console_resources_core.file import FileType, safe_relative_name
from agent_console_resources_core.hook import DEFAULT_EVENT_EXAMPLES, HookType, hook_config_schema
from agent_console_resources_core.instruction import InstructionType
from agent_console_resources_core.mcp_server import SECRET_FIELDS, McpServerType
from agent_console_resources_core.rule import (
    DEFAULT_PATHS_HEADER,
    DEFAULT_RULES_DIR,
    RULE_NAME_PATTERN,
    RuleType,
    render_rule_file,
)
from agent_console_resources_core.skill import (
    SKILL_NAME_PATTERN,
    SkillType,
    skill_files,
    skill_name,
)
from agent_console_resources_core.tool_permission import PERMISSION_FIELDS, ToolPermissionType

__all__ = [
    "DEFAULT_EVENT_EXAMPLES",
    "DEFAULT_PATHS_HEADER",
    "DEFAULT_RULES_DIR",
    "PERMISSION_FIELDS",
    "RULE_NAME_PATTERN",
    "SECRET_FIELDS",
    "SKILL_NAME_PATTERN",
    "FileType",
    "HookType",
    "InstructionType",
    "McpServerType",
    "RuleType",
    "SkillType",
    "ToolPermissionType",
    "hook_config_schema",
    "render_rule_file",
    "safe_relative_name",
    "skill_files",
    "skill_name",
]
