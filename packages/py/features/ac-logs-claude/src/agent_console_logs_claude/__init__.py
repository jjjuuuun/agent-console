"""agent-console-logs-claude: Claude Code 세션 기록 출처·분류기 플러그인(design §4R.1·§4R.7).

- X5 `claude-code-jsonl`(`ClaudeCodeJsonlSource`): `projects/<키>/<세션>.jsonl`과
  `<세션>/subagents/**/agent-*.jsonl`(+ 메타 파일)을 찾아 증분으로 읽는다. 기본 꺼짐(F-5).
  앱에서는 등록된 프로젝트 폴더의 세션만 읽는다(설정 `project_scope`, `in_scope`, `project_key`).
  기본 루트는 CLI 세션(`~/.claude/projects`, 읽기 전용)과 앱 실행 세션
  (`<앱 workspace>/.state/claude/projects`, 설정 `workspace_roots`) 두 곳이다(5.7R.30b).
- X6 `claude-code`(`ClaudeCodeClassifier`): 행 단위 무상태 분류(F-7). 도구 이름 특수 처리·범주·
  hook 등 행 대응은 설정 데이터(F-6, `data/classifier_config.schema.json`).

둘 다 entry point(`agent_console.log_sources`·`agent_console.log_classifiers`)로 등록되며,
`agent_console_logs.LogRegistries().load()`가 찾는다. 서버·웹 없이 쓴다.
"""

from __future__ import annotations

from ._classifier import (
    MCP_PATTERN_GROUPS,
    OMITTED_KEY,
    ClaudeCodeClassifier,
    McpPatternError,
    compile_mcp_pattern,
    omitted_row,
    summary_text,
)
from ._schemas import classifier_config_schema, source_config_schema
from ._source import (
    CLAUDE_CODE_FORMAT,
    CLAUDE_CODE_SOURCE_ID,
    META_KIND_SESSION,
    META_KIND_SUBAGENT,
    ClaudeCodeJsonlSource,
    project_key,
)

__all__ = [
    "CLAUDE_CODE_FORMAT",
    "CLAUDE_CODE_SOURCE_ID",
    "MCP_PATTERN_GROUPS",
    "META_KIND_SESSION",
    "META_KIND_SUBAGENT",
    "OMITTED_KEY",
    "ClaudeCodeClassifier",
    "ClaudeCodeJsonlSource",
    "McpPatternError",
    "classifier_config_schema",
    "compile_mcp_pattern",
    "omitted_row",
    "project_key",
    "source_config_schema",
    "summary_text",
]
