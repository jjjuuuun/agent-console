"""agent-console-nodes-core: 기본 노드·연결 종류·위임 방식 플러그인(design §R3, §R1.2a, §R12).

엔진에는 entry point(`agent_console.node_types`, `agent_console.edge_types`,
`agent_console.delegation_strategies`)로만 등록된다. 엔진·`ac-teams`는 이 이름들을 모르고
디스크립터 속성으로만 판단한다.

공개 API:
    - 노드 타입: ``AgentNode``(``agent``), ``UserNode``(``user``, 중간 검토 ``ReviewConfig``),
      ``ResourceNode``(``resource``)
    - 중첩 팀 노드 타입(design §5R.7): ``TeamNode``(``team``, ``binds{kind: graph, field:
      team_ref}``, config ``TeamNodeConfig{team_ref, version, input_key, reply, reply_separator,
      settings}``, 자식 Run으로 실행), 답변 고르기 ``pick_replies``, 대화 세션 경로 키
      ``session_path_key``·``child_sessions``·``SESSION_PATH_SEPARATOR``, 기다림 이유
      ``TEAM_CHILD_WAITING``, 역할 ``TEAM_ROLE``
    - 연결 종류: ``SubagentEdge``(``subagent``), ``HandoffEdge``(``handoff``), ``DataEdge``
      (``data``, handoff 이전 이름), ``UsesEdge``(``uses``), ``MessageEdge``(``message``),
      ``ReplyEdge``(``reply``), ``AskUserEdge``(``ask_user``)
    - 독립 위임 연결 종류: ``DelegateEdge``(``delegate``, invocation ``host`` =
      ``HOST_STRATEGY``, config ``DelegateEdgeConfig{strategy, result}``). 위임 방식 ``host`` 구현은
      별도 패키지 ``agent-console-delegation-host``다.
    - 반복 연결 종류(design §5R.4): ``LoopEdge``(``loop``, 디스크립터 ``cycle``, config
      ``LoopEdgeConfig.max_iterations``), 기본 최대 반복 ``DEFAULT_LOOP_MAX_ITERATIONS``
    - 조건·실패 연결 종류(design §5R.5): ``WhenEdge``(``when``, config
      ``WhenEdgeConfig.conditions``, 판단 대상 ``condition_subject``, 거짓 사유
      ``CONDITION_FALSE``), ``OnErrorEdge``(``on_error``)
    - 상호작용 종류(X15) 디스크립터: ``QUESTION``, ``TOOL_PERMISSION``, ``REVIEW``,
      ``review_response_schema``, ``TOOL_PERMISSION_DECISIONS``
    - 위임 방식(X12): ``SdkSubagentsStrategy``(``sdk-subagents``, composable), ``subagent_specs``.
      에이전트 노드는 위임 대상을 방식별로 묶어, 모두 composable이면 각 방식의 ``contribute``를 합쳐
      백엔드를 한 번 부르고(혼합 위임), 방식이 하나면 그 방식의 ``run``을 부른다.
    - config 모델: ``AgentNodeConfig``, ``UserNodeConfig``, ``ResourceNodeConfig``,
      ``SubagentEdgeConfig``, ``UsesEdgeConfig``, ``MessageEdgeConfig``, ``ReplyEdgeConfig``
    - 프롬프트 합치기: ``assemble_prompt``, ``PromptInput``,
      ``PromptFormat``(유효 설정 ``prompt_input_*``)
    - 실행 폴더 파일: ``write_files``, ``write_item_trees``(항목 `files` 트리), ``run_folder``,
      ``safe_relative_name``, ``safe_part``, ``ITEM_FILES_KEY``, ``ITEM_TREES_DIR``
    - 앱이 주입하는 서비스 키: ``AGENT_LOOKUP``(``AgentLookup``), ``WORKSPACE_SETTINGS``,
      ``DEFAULT_BACKEND``, ``ERROR_FIXES``(``ErrorFixer``, 노드 실패 해결 버튼),
      ``WORKING_DIRECTORY``, ``SCOPE_LAYERS``, ``RESOURCE_LOOKUP``, ``RUN_FILES_ROOT``,
      ``SESSIONS``, ``TEAM_LOOKUP``(중첩 팀 조회), 레지스트리 이름 ``RESOURCE_TYPES_EXTENSION``,
      어댑터 ``FunctionResources``
    - 상수: ``DEFAULT_MESSAGE_KEY``, ``SDK_SUBAGENTS``, 오류 코드 ``NodesCoreErrorCodes``, 포트 이름
"""

from agent_console_nodes_core._common import (
    AGENT_LOOKUP_UNAVAILABLE_MESSAGE,
    AGENT_ROLE,
    ASKS_PORT,
    DELEGATED_PORT,
    DELEGATES_PORT,
    HEARS_PORT,
    IN_PORT,
    OUT_PORT,
    PROVIDES_PORT,
    RESOURCE_ROLE,
    RESOURCES_PORT,
    REVIEW_PORT,
    SAYS_PORT,
    TEAM_LOOKUP_UNAVAILABLE_MESSAGE,
    TEAM_ROLE,
    USER_ROLE,
    NodesCoreErrorCodes,
    as_text,
)
from agent_console_nodes_core.agent import (
    AgentNode,
    AgentNodeConfig,
    PromptFormat,
    PromptInput,
    assemble_prompt,
)
from agent_console_nodes_core.conditional import (
    CONDITION_FALSE,
    OnErrorEdge,
    WhenEdge,
    WhenEdgeConfig,
    condition_subject,
)
from agent_console_nodes_core.delegation import SDK_SUBAGENTS, SdkSubagentsStrategy, subagent_specs
from agent_console_nodes_core.edges import (
    DEFAULT_MESSAGE_KEY,
    HOST_STRATEGY,
    AskUserEdge,
    AskUserEdgeConfig,
    DataEdge,
    DelegateEdge,
    DelegateEdgeConfig,
    HandoffEdge,
    MessageEdge,
    MessageEdgeConfig,
    ReplyEdge,
    ReplyEdgeConfig,
    SubagentEdge,
    SubagentEdgeConfig,
    UsesEdge,
    UsesEdgeConfig,
)
from agent_console_nodes_core.files import (
    ITEM_FILES_KEY,
    ITEM_TREES_DIR,
    run_folder,
    safe_part,
    safe_relative_name,
    write_files,
    write_item_trees,
)
from agent_console_nodes_core.interactions import (
    QUESTION,
    REVIEW,
    TOOL_PERMISSION,
    TOOL_PERMISSION_DECISIONS,
    review_response_schema,
)
from agent_console_nodes_core.lookups import FunctionResources
from agent_console_nodes_core.loops import DEFAULT_LOOP_MAX_ITERATIONS, LoopEdge, LoopEdgeConfig
from agent_console_nodes_core.places import ResourceNode, ResourceNodeConfig
from agent_console_nodes_core.services import (
    AGENT_LOOKUP,
    DEFAULT_BACKEND,
    ERROR_FIXES,
    RESOURCE_LOOKUP,
    RESOURCE_TYPES_EXTENSION,
    RUN_FILES_ROOT,
    SCOPE_LAYERS,
    SESSIONS,
    TEAM_LOOKUP,
    WORKING_DIRECTORY,
    WORKSPACE_SETTINGS,
    AgentLookup,
    ErrorFixer,
)
from agent_console_nodes_core.team import (
    SESSION_PATH_SEPARATOR,
    TEAM_CHILD_WAITING,
    TeamNode,
    TeamNodeConfig,
    child_sessions,
    pick_replies,
    session_path_key,
)
from agent_console_nodes_core.user import ReviewConfig, UserNode, UserNodeConfig

__all__ = [
    "AGENT_LOOKUP",
    "AGENT_LOOKUP_UNAVAILABLE_MESSAGE",
    "AGENT_ROLE",
    "ASKS_PORT",
    "CONDITION_FALSE",
    "DEFAULT_BACKEND",
    "DEFAULT_LOOP_MAX_ITERATIONS",
    "DEFAULT_MESSAGE_KEY",
    "DELEGATED_PORT",
    "DELEGATES_PORT",
    "ERROR_FIXES",
    "HEARS_PORT",
    "HOST_STRATEGY",
    "IN_PORT",
    "ITEM_FILES_KEY",
    "ITEM_TREES_DIR",
    "OUT_PORT",
    "PROVIDES_PORT",
    "QUESTION",
    "RESOURCES_PORT",
    "RESOURCE_LOOKUP",
    "RESOURCE_ROLE",
    "RESOURCE_TYPES_EXTENSION",
    "REVIEW",
    "REVIEW_PORT",
    "RUN_FILES_ROOT",
    "SAYS_PORT",
    "SCOPE_LAYERS",
    "SDK_SUBAGENTS",
    "SESSIONS",
    "SESSION_PATH_SEPARATOR",
    "TEAM_CHILD_WAITING",
    "TEAM_LOOKUP",
    "TEAM_LOOKUP_UNAVAILABLE_MESSAGE",
    "TEAM_ROLE",
    "TOOL_PERMISSION",
    "TOOL_PERMISSION_DECISIONS",
    "USER_ROLE",
    "WORKING_DIRECTORY",
    "WORKSPACE_SETTINGS",
    "AgentLookup",
    "AgentNode",
    "AgentNodeConfig",
    "AskUserEdge",
    "AskUserEdgeConfig",
    "DataEdge",
    "DelegateEdge",
    "DelegateEdgeConfig",
    "ErrorFixer",
    "FunctionResources",
    "HandoffEdge",
    "LoopEdge",
    "LoopEdgeConfig",
    "MessageEdge",
    "MessageEdgeConfig",
    "NodesCoreErrorCodes",
    "OnErrorEdge",
    "PromptFormat",
    "PromptInput",
    "ReplyEdge",
    "ReplyEdgeConfig",
    "ResourceNode",
    "ResourceNodeConfig",
    "ReviewConfig",
    "SdkSubagentsStrategy",
    "SubagentEdge",
    "SubagentEdgeConfig",
    "TeamNode",
    "TeamNodeConfig",
    "UserNode",
    "UserNodeConfig",
    "UsesEdge",
    "UsesEdgeConfig",
    "WhenEdge",
    "WhenEdgeConfig",
    "as_text",
    "assemble_prompt",
    "child_sessions",
    "condition_subject",
    "pick_replies",
    "review_response_schema",
    "run_folder",
    "safe_part",
    "safe_relative_name",
    "session_path_key",
    "subagent_specs",
    "write_files",
    "write_item_trees",
]
