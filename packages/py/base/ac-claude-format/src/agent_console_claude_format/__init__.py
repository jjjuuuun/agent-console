"""agent-console-claude-format: Claude Code `.claude` 산출물 읽기·쓰기 변환(순수 함수).

설계: design §2R.7.

파일을 읽거나 쓰지 않는다. 텍스트·바이트·JSON 값을 받아 값 객체를 돌려주고, 그 반대로 만든다.
가져오기(`ac-imports`)와 내보내기(`ac-exports`의 `claude-dir`)가 같은 변환을 쓴다.

공개 API:
    - 데이터: ``ClaudeMapping``(정의 종류·리소스 종류 이름), ``ClaudeLayout``(산출물 경로)
    - frontmatter: ``parse_frontmatter``, ``render_frontmatter``, ``str_list``, ``json_safe``,
      ``dump_json``
    - 에이전트 파일: ``AgentFile``, ``parse_agent_md``, ``render_agent_md``, ``agent_document``,
      ``agent_file_from_document``
    - skill 폴더: ``SkillFolder``, ``parse_skill``, ``render_skill``, ``valid_skill_name``
    - 규칙 파일: ``RuleFile``, ``parse_rule``, ``render_rule``
    - 설정: ``ClaudeSettings``, ``HookSpec``, ``parse_settings``, ``render_settings``,
      ``parse_hooks``, ``render_hooks``
    - MCP: ``parse_mcp``, ``render_mcp``, ``mcp_config_from_entry``, ``mcp_entry_from_config``,
      ``McpEntry``, ``env_placeholder``, ``parse_env_ref``

왕복 규칙: ``render(parse(x))``는 ``x``와 의미가 같다(키 순서·공백·목록 표기 차이만 있을 수 있다).
"""

from ._agent import (
    AGENT_DOCUMENT_FIELDS,
    FRONTMATTER_ATTRIBUTE,
    INHERIT_MODEL,
    AgentFile,
    agent_document,
    agent_file_from_document,
    parse_agent_md,
    render_agent_md,
)
from ._frontmatter import dump_json, json_safe, parse_frontmatter, render_frontmatter, str_list
from ._mapping import ClaudeLayout, ClaudeMapping
from ._mcp import (
    MCP_SERVERS_KEY,
    SECRET_REF_PREFIX,
    McpEntry,
    SecretStyle,
    env_placeholder,
    mcp_config_from_entry,
    mcp_entry_from_config,
    parse_env_ref,
    parse_mcp,
    render_mcp,
)
from ._rule import PATHS_KEY, RuleFile, parse_rule, render_rule
from ._settings import (
    COMMAND_HOOK_TYPE,
    ClaudeSettings,
    HookSpec,
    parse_hooks,
    parse_settings,
    render_hooks,
    render_settings,
)
from ._skill import SKILL_NAME_PATTERN, SkillFolder, parse_skill, render_skill, valid_skill_name

__all__ = [
    "AGENT_DOCUMENT_FIELDS",
    "COMMAND_HOOK_TYPE",
    "FRONTMATTER_ATTRIBUTE",
    "INHERIT_MODEL",
    "MCP_SERVERS_KEY",
    "PATHS_KEY",
    "SECRET_REF_PREFIX",
    "SKILL_NAME_PATTERN",
    "AgentFile",
    "ClaudeLayout",
    "ClaudeMapping",
    "ClaudeSettings",
    "HookSpec",
    "McpEntry",
    "RuleFile",
    "SecretStyle",
    "SkillFolder",
    "agent_document",
    "agent_file_from_document",
    "dump_json",
    "env_placeholder",
    "json_safe",
    "mcp_config_from_entry",
    "mcp_entry_from_config",
    "parse_agent_md",
    "parse_env_ref",
    "parse_frontmatter",
    "parse_hooks",
    "parse_mcp",
    "parse_rule",
    "parse_settings",
    "parse_skill",
    "render_agent_md",
    "render_frontmatter",
    "render_hooks",
    "render_mcp",
    "render_rule",
    "render_settings",
    "render_skill",
    "str_list",
    "valid_skill_name",
]
