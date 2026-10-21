/* eslint-disable */
/**
 * 자동 생성 파일 — 직접 수정하지 말 것.
 * 소스: packages/py/base/ac-contracts (Pydantic 모델) → schema/agent-console.schema.json → 이 파일.
 * 다시 생성: uv run poe contracts   드리프트 검사: uv run poe contracts-check
 */

/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "NetworkPolicy".
 */
export type NetworkPolicy = "allow" | "deny";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AttachmentMode".
 */
export type AttachmentMode = "add" | "replace" | "remove";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "SessionPolicy".
 */
export type SessionPolicy = "continue" | "fresh";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AnyKnownRunEvent".
 */
export type AnyKnownRunEvent =
  | RunLifecycleEvent
  | NodeStatusEvent
  | EdgeTraversedEvent
  | AgentSessionStartedEvent
  | AgentTextDeltaEvent
  | AgentMessageEvent
  | AgentToolCallEvent
  | AgentToolResultEvent
  | AgentSubagentEvent
  | AgentUsageEvent
  | LogWarningEvent
  | RunReplyEvent
  | UsageRateLimitEvent
  | InteractionRequestedEvent
  | InteractionAnsweredEvent
  | InteractionClosedEvent
  | EdgeSkippedEvent
  | LoopIterationEvent
  | LoopExhaustedEvent
  | RunChildStartedEvent
  | RunChildFinishedEvent;
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "RunStatus".
 */
export type RunStatus =
  | "queued"
  | "running"
  | "paused"
  | "waiting"
  | "completed"
  | "failed"
  | "cancelled"
  | "interrupted";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "NodeRunStatus".
 */
export type NodeRunStatus =
  "pending" | "queued" | "running" | "waiting" | "succeeded" | "failed" | "skipped" | "cancelled";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ConditionMode".
 */
export type ConditionMode = "all" | "any";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "InteractionStatus".
 */
export type InteractionStatus = "pending" | "answered" | "expired" | "cancelled";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ItemAction".
 */
export type ItemAction = "created" | "overwritten" | "renamed" | "skipped" | "failed";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ConflictPolicy".
 */
export type ConflictPolicy = "skip" | "overwrite" | "rename";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ReadinessTone".
 */
export type ReadinessTone = "ok" | "warn" | "error" | "unknown";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "IssueSeverity".
 */
export type IssueSeverity = "error" | "warning" | "info";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "JoinRule".
 */
export type JoinRule = "any" | "all";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "BusyPolicy".
 */
export type BusyPolicy = "queue" | "reject";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ReplyDisplay".
 */
export type ReplyDisplay = "separate" | "merged" | "final_only";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ChatTitlePolicy".
 */
export type ChatTitlePolicy = "first_message" | "manual";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "SendKey".
 */
export type SendKey = "enter" | "mod_enter";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "QueueAfterRestart".
 */
export type QueueAfterRestart = "ask" | "run" | "drop";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "DiffOp".
 */
export type DiffOp = "add" | "remove" | "replace";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "DefinitionScope".
 */
export type DefinitionScope = "project" | "shared";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ProjectDeleteMode".
 */
export type ProjectDeleteMode = "move_to_shared" | "delete_definitions";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "OnTimeout".
 */
export type OnTimeout = "expire" | "cancel_run";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "EdgeScheduling".
 */
export type EdgeScheduling = "flow" | "none" | "entry" | "exit";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ExportConflictPolicy".
 */
export type ExportConflictPolicy = "skip" | "overwrite" | "fail";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ExportFileAction".
 */
export type ExportFileAction = "create" | "overwrite" | "skip" | "conflict";
/**
 * 알려진 RunEvent 판별 유니온(`type`으로 구분).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "KnownRunEvent".
 */
export type KnownRunEvent =
  | RunLifecycleEvent
  | NodeStatusEvent
  | EdgeTraversedEvent
  | AgentSessionStartedEvent
  | AgentTextDeltaEvent
  | AgentMessageEvent
  | AgentToolCallEvent
  | AgentToolResultEvent
  | AgentSubagentEvent
  | AgentUsageEvent
  | LogWarningEvent
  | RunReplyEvent
  | UsageRateLimitEvent
  | InteractionRequestedEvent
  | InteractionAnsweredEvent
  | InteractionClosedEvent
  | EdgeSkippedEvent
  | LoopIterationEvent
  | LoopExhaustedEvent
  | RunChildStartedEvent
  | RunChildFinishedEvent;
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogUngroupedPolicy".
 */
export type LogUngroupedPolicy = "cwd" | "repo_root" | "none";
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ModuleStatus".
 */
export type ModuleStatus = string;
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UsageTrust".
 */
export type UsageTrust = string;
/**
 * 클라이언트 → 서버 메시지 유니온.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "WsClientMessage".
 */
export type WsClientMessage = SubscribeMessage | UnsubscribeMessage;
/**
 * 서버 → 클라이언트 메시지 유니온.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "WsServerMessage".
 */
export type WsServerMessage =
  | RunEventMessage
  | ConversationUpdatedMessage
  | InteractionUpdatedMessage
  | LogsIngestedMessage
  | ErrorMessage;

/**
 * Agent Console 공용 계약. 자동 생성 — 직접 수정하지 말 것(uv run poe contracts).
 */
export interface AgentConsoleContracts {}
/**
 * 에이전트 하나입니다. 이름·역할과 실행 설정을 담습니다.
 *
 * 비운 설정은 공통 설정·팀 설정 값을 따릅니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "Agent".
 */
export interface Agent {
  kind?: "agent";
  /**
   * 가리킬 때 쓰는 고유 이름입니다. 파일 이름으로도 쓰며 영문·숫자·-·_만 씁니다.
   */
  id: string;
  /**
   * 파일 형식 번호입니다. 직접 바꾸지 않습니다.
   */
  schema_version?: number;
  /**
   * 에이전트를 부르는 이름입니다. 팀 그래프와 채팅에 이 이름이 보입니다.
   */
  name: string;
  /**
   * 언제 이 에이전트에게 맡길지 적습니다. 위임할 때 대상을 고르는 단서가 됩니다.
   */
  description?: string;
  /**
   * 이 에이전트가 하는 일을 한 줄로 적습니다. 목록과 노드에 함께 보입니다.
   */
  role?: string;
  /**
   * 찾기·거르기에 쓰는 꼬리표입니다.
   */
  labels?: string[];
  /**
   * 다른 도구가 읽는 자유 속성입니다. 보통은 비워 둡니다.
   */
  attributes?: {
    [k: string]: unknown;
  };
  /**
   * 이 정의가 속한 프로젝트입니다. 비우면 공용이라 모든 프로젝트에서 보입니다.
   */
  project?: string | null;
  /**
   * 에이전트를 실제로 돌릴 실행 방식입니다. 비우면 팀 설정이나 공통 설정의 값을 씁니다.
   */
  backend?: string | null;
  /**
   * 에이전트가 쓸 모델입니다. 목록에서 고르거나 직접 입력합니다. 비우면 팀·공통 설정 값입니다.
   */
  model?: string | null;
  /**
   * 에이전트의 기본 지침입니다. 비우면 팀 설정이나 공통 설정의 값을 씁니다.
   */
  system_prompt?: string | null;
  /**
   * 에이전트가 쓸 수 있는 도구 이름입니다. 비우면 실행 백엔드의 기본 도구를 씁니다.
   */
  tools?: string[] | null;
  /**
   * 에이전트가 쓰지 못하게 막을 도구 이름입니다.
   */
  disallowed_tools?: string[] | null;
  /**
   * 에이전트가 쓸 폴더·명령·네트워크 범위입니다. 여기서 정하면 공통·팀 설정의 범위를 통째로 바꿉니다.
   */
  limits?: Limits | null;
  /**
   * 실행 중 hook(도구 실행 전후에 도는 명령)·MCP(외부 도구 서버) 호출을 기록할지 정합니다.
   */
  observe?: ObserveSettings | null;
  /**
   * 붙인 지침·파일·외부 도구 서버(MCP) 등입니다. 공통·팀 설정에서 붙인 것과 함께 쓰입니다.
   */
  resources?: ResourceAttachment[] | null;
  /**
   * 에이전트가 일하는 폴더입니다. 비우면 프로젝트나 서버 설정의 작업 폴더를 씁니다.
   */
  working_directory?: string | null;
  /**
   * 넘겨받은 값을 프롬프트로 합치는 틀입니다. {inputs}·{message}·{node}를 쓰고, 비우면 {inputs} 그대로입니다.
   */
  prompt_template?: string | null;
  /**
   * 값이 여러 개 들어올 때 값 하나를 적는 틀입니다. {source}(보낸 노드 이름)·{value}·{index} 등을 씁니다.
   */
  prompt_input_template?: string | null;
  /**
   * 값이 하나만 들어올 때 쓰는 틀입니다. 변수는 여러 값일 때와 같습니다.
   */
  prompt_single_input_template?: string | null;
  /**
   * 여러 값을 이을 때 사이에 넣는 문자열입니다. 기본은 빈 줄 하나입니다.
   */
  prompt_input_separator?: string | null;
  /**
   * 다음 턴에 대화를 이어 쓸지(continue) 매번 새로 시작할지(fresh) 정합니다. 비우면 이어 씁니다.
   */
  session?: SessionPolicy | null;
  /**
   * 고른 실행 백엔드가 따로 받는 설정입니다. 비밀 값은 secret://이름으로만 적습니다.
   */
  backend_options?: {
    [k: string]: unknown;
  } | null;
  [k: string]: unknown;
}
/**
 * 에이전트가 쓸 디렉터리·명령·네트워크. 비운 항목은 상위 설정이나 안전한 기본값을 따른다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "Limits".
 */
export interface Limits {
  /**
   * 에이전트가 읽고 쓸 수 있는 폴더입니다. {workspace}는 작업 공간 경로로 바뀝니다.
   */
  directories?: string[] | null;
  /**
   * 에이전트가 실행할 수 있는 명령입니다. 비우면 공통·팀 설정 값이나 안전한 기본값을 씁니다.
   */
  commands?: string[] | null;
  /**
   * 외부 네트워크 접근을 허용(allow)할지 막을지(deny) 정합니다.
   */
  network?: NetworkPolicy | null;
  [k: string]: unknown;
}
/**
 * 실행 중에 hook(도구 실행 전후에 도는 명령)·MCP(외부 도구 서버) 호출 등을 기록합니다.
 *
 * 비운 항목은 공통 설정·팀 설정 값을 따릅니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ObserveSettings".
 */
export interface ObserveSettings {
  /**
   * 수집기마다 켜고 끄며 설정합니다. 고를 수 있는 수집기는 실행 백엔드가 알려 줍니다.
   */
  collectors?: {
    [k: string]: CollectorSetting;
  } | null;
  /**
   * hook(도구 실행 전후에 도는 명령)의 입력·출력·결정·시간까지 기록합니다. 기본은 꺼짐입니다.
   */
  hook_probe?: boolean | null;
  /**
   * 이전 형식입니다. hook(도구 실행 전후에 도는 명령) 실행을 기록합니다. 새 설정은 관측 수집기를 씁니다.
   */
  hooks?: boolean | null;
  /**
   * 이전 형식입니다. MCP(외부 도구 서버) 호출을 기록합니다. 새 설정은 관측 수집기를 씁니다.
   */
  mcp?: boolean | null;
  /**
   * 기록할 hook(도구 실행 전후에 도는 명령) 이벤트 이름입니다. 비우면 실행 백엔드 기본 목록입니다.
   */
  hook_events?: string[] | null;
  [k: string]: unknown;
}
/**
 * 관측 수집기 하나를 켤지와 그 설정입니다. 비운 항목은 공통 설정·팀 설정 값을 따릅니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "CollectorSetting".
 */
export interface CollectorSetting {
  /**
   * 이 수집기로 기록할지 정합니다. 비우면 공통·팀 설정의 값을 따릅니다.
   */
  enabled?: boolean | null;
  /**
   * 수집기마다 정한 추가 설정입니다. 비우면 수집기 기본값을 씁니다.
   */
  config?: {
    [k: string]: unknown;
  } | null;
  [k: string]: unknown;
}
/**
 * 리소스 붙이기 하나입니다. 공통 설정·팀·에이전트·노드마다 목록으로 둡니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ResourceAttachment".
 */
export interface ResourceAttachment {
  /**
   * 붙일 리소스입니다.
   */
  ref: string;
  mode?: AttachmentMode;
  /**
   * 이 첨부에서만 바꿀 리소스 설정 값입니다.
   */
  config_override?: {
    [k: string]: unknown;
  } | null;
  [k: string]: unknown;
}
/**
 * 모든 에이전트가 함께 쓰는 기본 설정입니다.
 *
 * 팀이나 에이전트에서 따로 정하지 않은 항목은 여기 값을 씁니다. 처음 쓸 때 실행 백엔드를
 * 먼저 고르고, 모든 에이전트의 모델·도구·권한을 한꺼번에 바꾸고 싶을 때 고치세요.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AgentDefaults".
 */
export interface AgentDefaults {
  /**
   * 에이전트를 실제로 돌릴 실행 방식입니다. 비우면 팀 설정이나 공통 설정의 값을 씁니다.
   */
  backend?: string | null;
  /**
   * 에이전트가 쓸 모델입니다. 목록에서 고르거나 직접 입력합니다. 비우면 팀·공통 설정 값입니다.
   */
  model?: string | null;
  /**
   * 에이전트의 기본 지침입니다. 비우면 팀 설정이나 공통 설정의 값을 씁니다.
   */
  system_prompt?: string | null;
  /**
   * 에이전트가 쓸 수 있는 도구 이름입니다. 비우면 실행 백엔드의 기본 도구를 씁니다.
   */
  tools?: string[] | null;
  /**
   * 에이전트가 쓰지 못하게 막을 도구 이름입니다.
   */
  disallowed_tools?: string[] | null;
  /**
   * 에이전트가 쓸 폴더·명령·네트워크 범위입니다. 여기서 정하면 공통·팀 설정의 범위를 통째로 바꿉니다.
   */
  limits?: Limits | null;
  /**
   * 실행 중 hook(도구 실행 전후에 도는 명령)·MCP(외부 도구 서버) 호출을 기록할지 정합니다.
   */
  observe?: ObserveSettings | null;
  /**
   * 붙인 지침·파일·외부 도구 서버(MCP) 등입니다. 공통·팀 설정에서 붙인 것과 함께 쓰입니다.
   */
  resources?: ResourceAttachment[] | null;
  /**
   * 에이전트가 일하는 폴더입니다. 비우면 프로젝트나 서버 설정의 작업 폴더를 씁니다.
   */
  working_directory?: string | null;
  /**
   * 넘겨받은 값을 프롬프트로 합치는 틀입니다. {inputs}·{message}·{node}를 쓰고, 비우면 {inputs} 그대로입니다.
   */
  prompt_template?: string | null;
  /**
   * 값이 여러 개 들어올 때 값 하나를 적는 틀입니다. {source}(보낸 노드 이름)·{value}·{index} 등을 씁니다.
   */
  prompt_input_template?: string | null;
  /**
   * 값이 하나만 들어올 때 쓰는 틀입니다. 변수는 여러 값일 때와 같습니다.
   */
  prompt_single_input_template?: string | null;
  /**
   * 여러 값을 이을 때 사이에 넣는 문자열입니다. 기본은 빈 줄 하나입니다.
   */
  prompt_input_separator?: string | null;
  /**
   * 다음 턴에 대화를 이어 쓸지(continue) 매번 새로 시작할지(fresh) 정합니다. 비우면 이어 씁니다.
   */
  session?: SessionPolicy | null;
  /**
   * 고른 실행 백엔드가 따로 받는 설정입니다. 비밀 값은 secret://이름으로만 적습니다.
   */
  backend_options?: {
    [k: string]: unknown;
  } | null;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AgentMessageEvent".
 */
export interface AgentMessageEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "agent.message";
  payload: AgentMessagePayload;
}
/**
 * `agent.message` payload(완성된 메시지).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AgentMessagePayload".
 */
export interface AgentMessagePayload {
  role: string;
  text: string;
  message_id?: string | null;
  structured?: unknown;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AgentSessionStartedEvent".
 */
export interface AgentSessionStartedEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "agent.session_started";
  payload: AgentSessionStartedPayload;
}
/**
 * `agent.session_started` payload.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AgentSessionStartedPayload".
 */
export interface AgentSessionStartedPayload {
  session_id: string;
  backend: string;
  model?: string | null;
}
/**
 * 에이전트가 실행될 때 쓰는 설정입니다.
 *
 * 비운 항목은 더 넓은 설정(공통 설정, 팀 설정, 에이전트 순)에서 정한 값을 따릅니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AgentSettings".
 */
export interface AgentSettings {
  /**
   * 에이전트를 실제로 돌릴 실행 방식입니다. 비우면 팀 설정이나 공통 설정의 값을 씁니다.
   */
  backend?: string | null;
  /**
   * 에이전트가 쓸 모델입니다. 목록에서 고르거나 직접 입력합니다. 비우면 팀·공통 설정 값입니다.
   */
  model?: string | null;
  /**
   * 에이전트의 기본 지침입니다. 비우면 팀 설정이나 공통 설정의 값을 씁니다.
   */
  system_prompt?: string | null;
  /**
   * 에이전트가 쓸 수 있는 도구 이름입니다. 비우면 실행 백엔드의 기본 도구를 씁니다.
   */
  tools?: string[] | null;
  /**
   * 에이전트가 쓰지 못하게 막을 도구 이름입니다.
   */
  disallowed_tools?: string[] | null;
  /**
   * 에이전트가 쓸 폴더·명령·네트워크 범위입니다. 여기서 정하면 공통·팀 설정의 범위를 통째로 바꿉니다.
   */
  limits?: Limits | null;
  /**
   * 실행 중 hook(도구 실행 전후에 도는 명령)·MCP(외부 도구 서버) 호출을 기록할지 정합니다.
   */
  observe?: ObserveSettings | null;
  /**
   * 붙인 지침·파일·외부 도구 서버(MCP) 등입니다. 공통·팀 설정에서 붙인 것과 함께 쓰입니다.
   */
  resources?: ResourceAttachment[] | null;
  /**
   * 에이전트가 일하는 폴더입니다. 비우면 프로젝트나 서버 설정의 작업 폴더를 씁니다.
   */
  working_directory?: string | null;
  /**
   * 넘겨받은 값을 프롬프트로 합치는 틀입니다. {inputs}·{message}·{node}를 쓰고, 비우면 {inputs} 그대로입니다.
   */
  prompt_template?: string | null;
  /**
   * 값이 여러 개 들어올 때 값 하나를 적는 틀입니다. {source}(보낸 노드 이름)·{value}·{index} 등을 씁니다.
   */
  prompt_input_template?: string | null;
  /**
   * 값이 하나만 들어올 때 쓰는 틀입니다. 변수는 여러 값일 때와 같습니다.
   */
  prompt_single_input_template?: string | null;
  /**
   * 여러 값을 이을 때 사이에 넣는 문자열입니다. 기본은 빈 줄 하나입니다.
   */
  prompt_input_separator?: string | null;
  /**
   * 다음 턴에 대화를 이어 쓸지(continue) 매번 새로 시작할지(fresh) 정합니다. 비우면 이어 씁니다.
   */
  session?: SessionPolicy | null;
  /**
   * 고른 실행 백엔드가 따로 받는 설정입니다. 비밀 값은 secret://이름으로만 적습니다.
   */
  backend_options?: {
    [k: string]: unknown;
  } | null;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AgentSubagentEvent".
 */
export interface AgentSubagentEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "agent.subagent_started" | "agent.subagent_stopped";
  payload: AgentSubagentPayload;
}
/**
 * `agent.subagent_started|stopped` payload.
 *
 * `name`은 위임 대상 노드 id. 종료 이벤트의 `usage`는 백엔드가 주는 만큼만(예: 총 토큰만).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AgentSubagentPayload".
 */
export interface AgentSubagentPayload {
  subagent_id: string;
  name?: string | null;
  /**
   * 위임 도구 호출 id(부모 연결 키).
   */
  tool_use_id?: string | null;
  task_type?: string | null;
  task_preview?: string | null;
  /**
   * 종료 상태 문자열(백엔드가 줌).
   */
  status?: string | null;
  usage?: Usage | null;
  tool_uses?: number | null;
  duration_ms?: number | null;
  result_preview?: string | null;
}
/**
 * 토큰·비용 사용량. 값을 모르면 null(화면은 대시로 표시).
 *
 * 알려진 키 외에 백엔드가 숫자 키를 더 붙일 수 있다(화면은 키 이름 그대로 표시).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "Usage".
 */
export interface Usage {
  input_tokens?: number | null;
  output_tokens?: number | null;
  cache_read_tokens?: number | null;
  cache_creation_tokens?: number | null;
  cost_usd?: number | null;
  /**
   * 입력·출력 구분 없는 총 토큰(예: 서브에이전트 TaskUsage). 구분 값이 있으면 그쪽이 정밀하다.
   */
  total_tokens?: number | null;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AgentTextDeltaEvent".
 */
export interface AgentTextDeltaEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "agent.text_delta";
  payload: AgentTextDeltaPayload;
}
/**
 * `agent.text_delta` payload. 출력 패널이 누적한다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AgentTextDeltaPayload".
 */
export interface AgentTextDeltaPayload {
  text: string;
  message_id?: string | null;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AgentToolCallEvent".
 */
export interface AgentToolCallEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "agent.tool_call";
  payload: AgentToolCallPayload;
}
/**
 * `agent.tool_call` payload.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AgentToolCallPayload".
 */
export interface AgentToolCallPayload {
  tool_use_id: string;
  name: string;
  input?: unknown;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AgentToolResultEvent".
 */
export interface AgentToolResultEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "agent.tool_result";
  payload: AgentToolResultPayload;
}
/**
 * `agent.tool_result` payload.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AgentToolResultPayload".
 */
export interface AgentToolResultPayload {
  tool_use_id: string;
  is_error?: boolean;
  output_preview?: string;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AgentUsageEvent".
 */
export interface AgentUsageEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "agent.usage";
  payload: AgentUsagePayload;
}
/**
 * `agent.usage` payload. `usage`는 이 노드 시도(attempt)의 **누적값**이다(더하지 말고 교체).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AgentUsagePayload".
 */
export interface AgentUsagePayload {
  usage: Usage;
  model?: string | null;
}
/**
 * 팀 구성의 답변 자리 하나(답변 연결). 속성은 엣지 타입 `reply_fields`로 config에서 읽는다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AnswerSlot".
 */
export interface AnswerSlot {
  edge_id: string;
  /**
   * 답변을 내는 노드(답변 연결의 출발 노드).
   */
  node_id: string;
  agent_id?: string | null;
  label?: string | null;
  order?: number | null;
  final?: boolean;
  stream?: boolean;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "RunLifecycleEvent".
 */
export interface RunLifecycleEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type:
    | "run.created"
    | "run.started"
    | "run.paused"
    | "run.resumed"
    | "run.waiting"
    | "run.completed"
    | "run.failed"
    | "run.cancelled"
    | "run.interrupted";
  payload: RunStatusPayload;
}
/**
 * `run.*` 이벤트 payload.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "RunStatusPayload".
 */
export interface RunStatusPayload {
  status: RunStatus;
  error?: ErrorInfo | null;
  totals?: Usage | null;
  duration_ms?: number | null;
}
/**
 * 오류 정보. REST 오류 응답, WS `error`, 노드 실패에 공통으로 쓴다.
 *
 * `code`는 기계가 읽는 문자열(고정 목록 아님, 알려진 값은 `ErrorCodes`).
 * `message`는 사람이 읽는 문장.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ErrorInfo".
 */
export interface ErrorInfo {
  code: string;
  message: string;
  details?: {
    [k: string]: unknown;
  };
  /**
   * 해결 버튼(0.8.0). null = 제안 없음(화면은 메시지만 보인다).
   */
  fix?: Fix | null;
}
/**
 * 오류·이슈를 고치는 방법(버튼 목록). 오류를 만드는 쪽(서버)이 채운다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "Fix".
 */
export interface Fix {
  actions?: FixAction[];
}
/**
 * 해결 버튼 하나: 문구 + 이동할 곳 + 열었을 때 초점을 둘 필드.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "FixAction".
 */
export interface FixAction {
  /**
   * 버튼 문구(사용자 언어).
   */
  label: string;
  target: FixTarget;
  /**
   * 열린 폼에서 초점을 둘 필드(그 폼 문서 기준 JSON Pointer, 예: /backend).
   */
  focus?: string | null;
}
/**
 * 해결 버튼이 데려갈 화면. 서버는 웹 경로를 모른다.
 *
 * `role`은 웹 라우트 **역할** 문자열(정의 종류 역할, 설정 역할 등)이고 웹이 경로로 푼다. 그 역할을
 * 맡은 화면이 없으면(모듈 꺼짐) 웹은 버튼을 숨긴다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "FixTarget".
 */
export interface FixTarget {
  /**
   * 웹 라우트 역할 이름(열린 문자열).
   */
  role: string;
  /**
   * 그 화면에서 열 항목 id(예: 팀 구성 id).
   */
  id?: string | null;
  /**
   * 화면 안 위치(예: 설정 섹션 id, 노드 id). 해석은 그 화면.
   */
  section?: string | null;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "NodeStatusEvent".
 */
export interface NodeStatusEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type:
    | "node.queued"
    | "node.started"
    | "node.waiting"
    | "node.resumed"
    | "node.completed"
    | "node.failed"
    | "node.skipped"
    | "node.cancelled";
  payload: NodeStatusPayload;
}
/**
 * `node.*` 이벤트 payload. waiting이면 `wait`, 종료면 usage·duration_ms·error.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "NodeStatusPayload".
 */
export interface NodeStatusPayload {
  status: NodeRunStatus;
  node_type?: string | null;
  iteration?: number | null;
  /**
   * 호출 회차(위임자가 부른 NodeRun이면).
   */
  call?: number | null;
  outputs_preview?: string | null;
  usage?: Usage | null;
  duration_ms?: number | null;
  error?: ErrorInfo | null;
  wait?: WaitInfo | null;
  /**
   * node.resumed: 대기한 시간(ms).
   */
  waited_ms?: number | null;
  /**
   * node.skipped 등의 사유(열린 문자열, 예: 이어 가기의 상류 `resumed`).
   */
  reason?: string | null;
}
/**
 * 노드가 waiting일 때 무엇을 기다리는지(`node.waiting` payload의 `wait`).
 *
 * 상호작용 대기면 `reason` = 상호작용 종류 id, `data.interaction_ids` = 대기 중 상호작용 id 목록
 * .
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "WaitInfo".
 */
export interface WaitInfo {
  /**
   * 대기 이유 문자열(고정 목록 아님).
   */
  reason: string;
  message?: string;
  options?: string[];
  data?: {
    [k: string]: unknown;
  };
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "EdgeTraversedEvent".
 */
export interface EdgeTraversedEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "edge.traversed";
  payload: EdgeTraversedPayload;
}
/**
 * `edge.traversed` payload.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "EdgeTraversedPayload".
 */
export interface EdgeTraversedPayload {
  edge_id: string;
  source: Endpoint;
  target: Endpoint;
  value_preview?: string | null;
  /**
   * 연결 종류 id(엣지 kind). 모르면 null.
   */
  kind?: string | null;
  /**
   * 조건 연결이면 판정 근거. 없으면 null.
   */
  condition?: ConditionOutcome | null;
}
/**
 * 연결의 한쪽 끝입니다: 노드와 그 포트 이름.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "Endpoint".
 */
export interface Endpoint {
  /**
   * 연결 끝의 노드 id입니다.
   */
  node: string;
  /**
   * 연결 끝의 포트 이름입니다.
   */
  port: string;
}
/**
 * 조건 묶음의 판정 결과와 근거(`edge.traversed`·`edge.skipped` payload `condition`).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ConditionOutcome".
 */
export interface ConditionOutcome {
  /**
   * 최종 결과(`negate` 반영 뒤).
   */
  result: boolean;
  /**
   * 항목을 묶은 방식. all·any가 함께 있으면 null(항목의 mode).
   */
  combinator?: ConditionMode | null;
  /**
   * 결과를 뒤집었는지.
   */
  negate?: boolean | null;
  /**
   * 항목별 근거. null = 근거를 싣지 않음.
   */
  items?: ConditionItemOutcome[] | null;
}
/**
 * 조건 항목 하나의 판정 근거.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ConditionItemOutcome".
 */
export interface ConditionItemOutcome {
  path: string;
  op: string;
  /**
   * 비교한 기대 값(조건 데이터 그대로).
   */
  value?: unknown;
  /**
   * 비교한 실제 값(비밀이 가려지고 서버가 정한 길이 상한으로 잘린 값).
   */
  actual?: unknown;
  /**
   * 이 항목의 판정.
   */
  result: boolean;
  /**
   * 이 항목이 속한 목록(all·any가 함께 있을 때 구분).
   */
  mode?: ConditionMode | null;
  /**
   * 거짓·판정 불가의 사유(열린 문자열). 알려진 값: missing(경로에 값 없음), unknown_operator(등록되지 않은 연산자), invalid_value(값이 value_schema에 맞지 않음), error(연산자 실패).
   */
  reason?: string | null;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogWarningEvent".
 */
export interface LogWarningEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "log.warning";
  payload: LogWarningPayload;
}
/**
 * `log.warning` payload.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogWarningPayload".
 */
export interface LogWarningPayload {
  message: string;
  details?: {
    [k: string]: unknown;
  };
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "RunReplyEvent".
 */
export interface RunReplyEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "run.reply";
  payload: RunReplyPayload;
}
/**
 * `run.reply` payload: 답변 연결(`scheduling = exit`)의 출발 노드가 낸 답변.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "RunReplyPayload".
 */
export interface RunReplyPayload {
  edge_id: string;
  node_id: string;
  label?: string | null;
  order?: number | null;
  final?: boolean;
  text: string;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UsageRateLimitEvent".
 */
export interface UsageRateLimitEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "usage.rate_limit";
  payload: UsageRateLimitPayload;
}
/**
 * `usage.rate_limit` payload. 창 id·상태는 공급자 문자열 그대로다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UsageRateLimitPayload".
 */
export interface UsageRateLimitPayload {
  /**
   * 창 id(고정 목록 아님).
   */
  window: string;
  status?: string | null;
  /**
   * 사용률(0~1).
   */
  utilization?: number | null;
  /**
   * Unix epoch 초.
   */
  resets_at?: number | null;
  overage_status?: string | null;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "InteractionRequestedEvent".
 */
export interface InteractionRequestedEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "interaction.requested";
  payload: InteractionRequestedPayload;
}
/**
 * `interaction.requested` payload.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "InteractionRequestedPayload".
 */
export interface InteractionRequestedPayload {
  interaction: Interaction;
}
/**
 * 상호작용 하나. payload·response는 저장 전에 비밀이 가려진 값이다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "Interaction".
 */
export interface Interaction {
  id: string;
  run_id: string;
  /**
   * 자식 Run(중첩 팀) 안의 요청이면 맨 위 Run id(0.7.0). 응답 대기 목록은 `root_run_id or run_id` 기준으로 모은다.
   */
  root_run_id?: string | null;
  conversation_id?: string | null;
  node_id: string;
  /**
   * 요청 시점의 노드 표시 이름(표시용, 없으면 node_id를 보인다).
   */
  node_label?: string | null;
  /**
   * 요청한 노드 경로. 서브에이전트 요청이면 [위임자 노드, 대상 노드].
   */
  node_path?: string[];
  attempt?: number;
  /**
   * 요청한 에이전트 정의 id.
   */
  actor?: string | null;
  /**
   * 상호작용 종류 id(X15 디스크립터, 고정 목록 아님).
   */
  kind: string;
  status: InteractionStatus;
  title?: string;
  message?: string;
  /**
   * 종류의 request_schema 형식.
   */
  payload?: {
    [k: string]: unknown;
  };
  /**
   * 이 요청의 응답 JSON Schema(응답 검증 기준).
   */
  response_schema?: {
    [k: string]: unknown;
  };
  response?: {
    [k: string]: unknown;
  } | null;
  /**
   * 닫은 주체. 알려진 값: user, timeout, system.
   */
  answered_by?: string | null;
  /**
   * 닫힌 이유. 알려진 값: cancelled, timeout, interrupted, node_finished.
   */
  close_reason?: string | null;
  /**
   * Unix epoch 초.
   */
  created_at: number;
  expires_at?: number | null;
  closed_at?: number | null;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "InteractionAnsweredEvent".
 */
export interface InteractionAnsweredEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "interaction.answered";
  payload: InteractionAnsweredPayload;
}
/**
 * `interaction.answered` payload. 응답 원문 대신 미리보기만 싣는다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "InteractionAnsweredPayload".
 */
export interface InteractionAnsweredPayload {
  interaction_id: string;
  kind: string;
  answered_by?: string | null;
  response_preview?: string | null;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "InteractionClosedEvent".
 */
export interface InteractionClosedEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "interaction.closed";
  payload: InteractionClosedPayload;
}
/**
 * `interaction.closed` payload(응답 없이 닫힘).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "InteractionClosedPayload".
 */
export interface InteractionClosedPayload {
  interaction_id: string;
  kind: string;
  status: "expired" | "cancelled";
  reason?: string | null;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "EdgeSkippedEvent".
 */
export interface EdgeSkippedEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "edge.skipped";
  payload: EdgeSkippedPayload;
}
/**
 * `edge.skipped` payload: 연결이 지나가지 않았다(조건 거짓·반복 한도 등).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "EdgeSkippedPayload".
 */
export interface EdgeSkippedPayload {
  edge_id: string;
  source: Endpoint;
  target: Endpoint;
  /**
   * 연결 종류 id(엣지 kind). 모르면 null.
   */
  kind?: string | null;
  /**
   * 지나가지 않은 사유(열린 문자열, 예: condition_false).
   */
  reason?: string | null;
  /**
   * 조건 연결이면 판정 근거. 없으면 null.
   */
  condition?: ConditionOutcome | null;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LoopIterationEvent".
 */
export interface LoopIterationEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "loop.iteration";
  payload: LoopIterationPayload;
}
/**
 * `loop.iteration` payload: 사이클 연결이 반복 영역을 다시 열었다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LoopIterationPayload".
 */
export interface LoopIterationPayload {
  /**
   * 지나간 사이클 연결 id.
   */
  edge_id: string;
  /**
   * 새로 연 회차(첫 반복이 1).
   */
  iteration: number;
  /**
   * 다시 연 반복 영역의 노드 id.
   */
  nodes?: string[];
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LoopExhaustedEvent".
 */
export interface LoopExhaustedEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "loop.exhausted";
  payload: LoopExhaustedPayload;
}
/**
 * `loop.exhausted` payload: 반복 한도에 닿아 사이클 연결이 더 지나가지 않는다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LoopExhaustedPayload".
 */
export interface LoopExhaustedPayload {
  edge_id: string;
  /**
   * 한도에 닿은 때의 회차.
   */
  iteration: number;
  /**
   * 적용한 한도.
   */
  max_iterations?: number | null;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "RunChildStartedEvent".
 */
export interface RunChildStartedEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "run.child_started";
  payload: RunChildStartedPayload;
}
/**
 * `run.child_started` payload: 노드가 자식 Run(중첩 팀)을 시작했다.
 *
 * 이 이벤트의 `status` 필드는 없다: 부모 Run 상태가 아니다(부모 상태는 `run.<상태>` 이벤트만).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "RunChildStartedPayload".
 */
export interface RunChildStartedPayload {
  child_run_id: string;
  /**
   * 자식 Run을 만든 부모 그래프의 노드 id.
   */
  node_id: string;
  /**
   * 자식 팀 구성 id.
   */
  graph_id?: string | null;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "RunChildFinishedEvent".
 */
export interface RunChildFinishedEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: "run.child_finished";
  payload: RunChildFinishedPayload;
}
/**
 * `run.child_finished` payload: 자식 Run이 끝났다. `status`는 **자식** Run 상태다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "RunChildFinishedPayload".
 */
export interface RunChildFinishedPayload {
  child_run_id: string;
  node_id: string;
  status: RunStatus;
}
/**
 * 정의 하나를 쓴 결과(프리셋 적용·가져오기 공통).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "AppliedItemInfo".
 */
export interface AppliedItemInfo {
  /**
   * 출처 안 경로·키.
   */
  source: string;
  /**
   * 정의 종류 이름.
   */
  kind: string;
  /**
   * 출처 안 id 또는 제안 id.
   */
  id: string;
  /**
   * 워크스페이스에 쓴 id.
   */
  target_id?: string | null;
  action: ItemAction;
  error?: string | null;
}
/**
 * `POST /presets/{id}/apply` 요청.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ApplyPresetRequest".
 */
export interface ApplyPresetRequest {
  on_conflict?: ConflictPolicy;
  /**
   * 만든 정의에 찍을 프로젝트 id(0.8.0). 생략 = 공용(지금과 같음).
   */
  project?: string | null;
}
/**
 * `POST /presets/{id}/apply` 응답.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ApplyPresetResult".
 */
export interface ApplyPresetResult {
  preset_id: string;
  items?: AppliedItemInfo[];
  warnings?: string[];
}
/**
 * 실행 백엔드 능력.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "BackendCapabilities".
 */
export interface BackendCapabilities {
  streaming?: boolean;
  tools?: boolean;
  hooks?: boolean;
  mcp?: boolean;
  resume?: boolean;
  cancel?: boolean;
  /**
   * 요청 안의 서브에이전트 목록을 한 세션에서 실행할 수 있다.
   */
  subagents?: boolean;
  /**
   * 받을 수 있는 실행 묶음 칸 이름.
   */
  resource_slots?: string[];
  /**
   * 열 수 있는 상호작용 종류 id. null = 제한 없음.
   */
  interactions?: string[] | null;
  /**
   * 서브에이전트(위임받는 노드)마다 따로 받는 실행 묶음 칸. `resource_slots`에 있지만 여기 없는 칸은 위임자 세션에 합쳐진다(세션 공유, 묶음 미리보기가 경고). null = 구분 정보 없음(경고하지 않음).
   */
  subagent_slots?: string[] | null;
  /**
   * 칸 이름 → 그 칸에 대한 백엔드 설명(예: 받지 않는 이유, 설정으로 꺼져 있음). `resource.slot_unsupported` 경고의 `details.reason`·문구에 붙는다. null = 설명 없음.
   */
  slot_notes?: {
    [k: string]: string;
  } | null;
  enforce?: EnforceCapabilities;
  /**
   * 플랫폼이 만든 도구(위임 도구 등)를 모델에게 주고 호출을 플랫폼으로 돌려줄 수 있다(독립 위임에 필요).
   */
  host_tools?: boolean;
  /**
   * 정적 점검(인증·설정 확인, 모델·네트워크 호출 없음)을 지원한다. `GET /backends/{id}/status`가 이 값이 false면 상태 unknown을 낸다.
   */
  status?: boolean;
  /**
   * 연결 테스트(가장 짧은 실제 호출 한 번)를 지원한다. false면 `POST /backends/{id}/probe`가 409 `backend.probe_unsupported`.
   */
  probe?: boolean;
}
/**
 * 백엔드가 실제로 강제할 수 있는 실행 범위 항목. false면 화면이 경고한다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "EnforceCapabilities".
 */
export interface EnforceCapabilities {
  directories?: boolean;
  commands?: boolean;
  network?: boolean;
}
/**
 * 실행 백엔드 디스크립터(X3).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "BackendDescriptor".
 */
export interface BackendDescriptor {
  id: string;
  title: string;
  description?: string;
  /**
   * backend_options의 JSON Schema.
   */
  config_schema?: {
    [k: string]: unknown;
  };
  capabilities?: BackendCapabilities;
  /**
   * 이 백엔드에서 쓸 수 있는 관측 수집기(X7). 설정 화면이 폼을 그린다.
   */
  collectors?: CollectorDescriptor[];
  /**
   * 비용 안내 한 줄(예: 구독 사용량을 씁니다). 비우면 표시 안 함.
   */
  cost_note?: string;
  /**
   * 연결 테스트 호출의 비용 안내 한 줄(확인 대화상자에 보임). 비우면 `cost_note`를 쓴다.
   */
  probe_cost_note?: string;
  ui_hints?: UiHints | null;
}
/**
 * 관측 수집기 디스크립터. 실행 중 SDK 콜백·메시지에서 이벤트를 모은다.
 *
 * 수집기는 백엔드별 프로토콜로 구현되고 `backend`로 걸러진다. 설정은
 * `AgentSettings.observe.collectors{id: {enabled?, config?}}`(생략 = 상속)다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "CollectorDescriptor".
 */
export interface CollectorDescriptor {
  id: string;
  title: string;
  /**
   * 이 수집기를 쓰는 실행 백엔드 id.
   */
  backend: string;
  description?: string | null;
  config_schema?: {
    [k: string]: unknown;
  };
  /**
   * 내는 실행 이벤트 type 또는 접두사(예: hook.*, mcp.*).
   */
  emits?: string[];
}
/**
 * 표시용 선택 힌트. 없어도 화면이 동작해야 한다(기본: 카테고리 해시 색 + 제목 첫 글자).
 *
 * 값 목록은 고정하지 않는다. 화면은 해석할 수 없는 값을 무시하고 기본 표시로 돌아간다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UiHints".
 */
export interface UiHints {
  /**
   * 짧은 아바타 글자입니다(1~2자, 이모지 포함).
   */
  icon?: string | null;
  /**
   * CSS 색이나 색 이름입니다. 모르는 값이면 기본 색입니다.
   */
  color?: string | null;
  /**
   * 연결선을 점선으로 그립니다(연결 종류용).
   */
  dashed?: boolean | null;
  /**
   * 팔레트·목록에 보이지 않게 합니다(조립용 종류).
   */
  hidden?: boolean | null;
  /**
   * 노드 모양 힌트입니다(예: card, chip). 모르면 기본 모양입니다.
   */
  shape?: string | null;
  /**
   * 화면이 쓸 전용 그리기 방식 이름입니다. 모르는 이름이면 일반 폼으로 그립니다.
   */
  renderer?: string | null;
  /**
   * 노드 종류의 기본 방향입니다(lr, tb, rl, bt, auto). 사용자 설정이 우선합니다.
   */
  direction?: string | null;
  /**
   * 연결 종류의 기본 선 모양입니다. 사용자 설정이 우선하고 모르는 값은 무시합니다.
   */
  edge_shape?: string | null;
  /**
   * 이름 옆에 붙는 짧은 글자입니다(예: 체험, 베타). 비우면 배지가 없습니다.
   */
  badge?: string | null;
  [k: string]: unknown;
}
/**
 * ``POST /backends/{id}/probe`` 요청(본문 생략 가능).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "BackendProbeRequest".
 */
export interface BackendProbeRequest {
  /**
   * 기다릴 최대 초. null = 서버 기본. 서버 상한을 넘으면 상한으로 잘린다.
   */
  timeout_s?: number | null;
}
/**
 * 연결 테스트 결과. 실행 기록·이벤트에 남지 않는다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "BackendProbeResult".
 */
export interface BackendProbeResult {
  backend_id: string;
  ok: boolean;
  /**
   * 호출에 걸린 시간(밀리초). null = 재지 않음.
   */
  latency_ms?: number | null;
  /**
   * 실패 사유 코드(열린 어휘, 예: auth_missing, auth_failed, timeout, network). 성공이면 null.
   */
  reason?: string | null;
  /**
   * 결과 문장(사용자 언어, 비밀 가림을 거침).
   */
  message?: string;
  /**
   * 확인 정보(예: 모델 id). 키·토큰 같은 비밀 값은 넣지 않는다.
   */
  details?: {
    [k: string]: unknown;
  };
  /**
   * 해결 버튼. 비면 없음.
   */
  fixes?: FixAction[];
  /**
   * 끝난 시각(epoch 초).
   */
  finished_at: number;
}
/**
 * 실행 백엔드의 정적 점검 상태(모델·네트워크 호출 없음).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "BackendReadiness".
 */
export interface BackendReadiness {
  backend_id: string;
  /**
   * 상태 이름(백엔드가 정하는 열린 어휘, 예: auth_ready, auth_missing). 화면은 비교하지 않고 tone·summary로 그린다. 점검을 지원하지 않으면 unknown.
   */
  state: string;
  tone: ReadinessTone;
  /**
   * 상태 줄 문구(사용자 언어).
   */
  summary?: string;
  /**
   * 칩에 쓸 짧은 문구(8자 이하 권장). 비면 화면이 summary를 줄인다.
   */
  short_summary?: string;
  /**
   * 보충 설명(예: 구독 방식 책임 문구).
   */
  detail?: string;
  /**
   * 해결 버튼(문구 + 이동할 곳). 비면 버튼 없음.
   */
  fixes?: FixAction[];
  /**
   * 점검 시각(epoch 초).
   */
  checked_at: number;
  /**
   * 항목별 점검 결과(접힌 상세에 보임). 값 없음.
   */
  checks?: ReadinessCheck[];
}
/**
 * 정적 점검 항목 하나(예: "API 키 환경변수: 있음"). 값은 담지 않는다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ReadinessCheck".
 */
export interface ReadinessCheck {
  /**
   * 항목 id(백엔드가 정함, 열린 문자열).
   */
  id: string;
  /**
   * 항목 이름(사용자 언어).
   */
  title: string;
  /**
   * 이 항목이 충족됐는지.
   */
  ok: boolean;
  /**
   * 보충 한 줄(출처 이름 등, 비밀 값 없음). null = 없음.
   */
  note?: string | null;
}
/**
 * `backend.unresolved`(HTTP 422) 오류의 `error.details`(0.8.0).
 *
 * 실행을 만들기 전에 백엔드를 쓰는 노드의 백엔드가 비었을 때 낸다. Run·턴 기록은 남지 않는다.
 * 해결 버튼은 `ErrorInfo.fix`에 있다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "BackendUnresolvedDetails".
 */
export interface BackendUnresolvedDetails {
  nodes?: UnresolvedBackendNode[];
  /**
   * 지금 고를 수 있는 백엔드(등록된 디스크립터).
   */
  options?: BackendDescriptor[];
}
/**
 * 실행 백엔드가 정해지지 않은 노드 하나(사전 점검 결과).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UnresolvedBackendNode".
 */
export interface UnresolvedBackendNode {
  /**
   * 노드 id.
   */
  id: string;
  /**
   * 화면 이름(노드 label, 없으면 정의 이름). 문구는 이 값으로 부른다.
   */
  label?: string;
}
/**
 * `GET /bootstrap`.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "BootstrapResponse".
 */
export interface BootstrapResponse {
  token: string;
  server_version: string;
  contracts_version: string;
}
/**
 * 노드 실행 묶음 미리보기(`GET /graphs/{id}/nodes/{node}/bundle-preview`, 초안 `POST`).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "BundlePreview".
 */
export interface BundlePreview {
  bundle: ResourceBundle;
  /**
   * 묶음 경고(받지 않는 칸, 세션 공유 칸 등).
   */
  warnings?: Issue[];
}
/**
 * 실행 묶음. 칸 이름 → 값. 칸 이름은 문자열이며 플러그인이 새 칸을 만들 수 있다.
 *
 * 알려진 칸 이름은 `KnownResourceSlots`(문서 상수)에 있다. 백엔드는
 * `BackendCapabilities.resource_slots`로 받을 칸을 선언한다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ResourceBundle".
 */
export interface ResourceBundle {
  slots?: {
    [k: string]: unknown;
  };
  sources?: {
    [k: string]: BundleSource[];
  };
}
/**
 * 실행 묶음 칸 하나에 기여한 첨부의 출처.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "BundleSource".
 */
export interface BundleSource {
  /**
   * 리소스 id.
   */
  ref: string;
  /**
   * 첨부가 들어온 설정 층 id.
   */
  layer?: string | null;
  mode?: AttachmentMode;
  /**
   * 리소스 종류 id.
   */
  resource_type?: string | null;
}
/**
 * 검증 이슈(그래프·정의 검증 결과).
 *
 * 대상: `node_id`가 있으면 그 노드, `edge_id`가 있으면 그 엣지, 둘 다 없으면 그래프 전체.
 * `path`는 RFC 6901 JSON Pointer이며 기준은 대상에 따라 다르다:
 * 노드 → 노드의 `config`, 엣지 → 엣지의 `config`, 그래프 → 그래프 문서.
 * 빈 문자열은 기준 객체 자체.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "Issue".
 */
export interface Issue {
  severity: IssueSeverity;
  code: string;
  message: string;
  node_id?: string | null;
  edge_id?: string | null;
  path?: string | null;
  details?: {
    [k: string]: unknown;
  };
  /**
   * 서버가 계산한 수정 제안(없으면 제안 버튼 없음).
   */
  suggestions?: IssueSuggestion[];
  /**
   * 이 이슈가 있으면 실행이 거부되는지. 검증한 쪽이 정한다. null = 정하지 않음(이 경우 severity가 error인 것만 실행을 막는다).
   */
  blocks_run?: boolean | null;
  /**
   * 해결 버튼(다른 화면으로 이동, 0.8.0). 그래프 안 수정은 suggestions. null = 없음.
   */
  fix?: Fix | null;
}
/**
 * 검증 이슈의 수정 제안 하나. 화면은 이슈 코드가 아니라 이 데이터로 제안 버튼을 그린다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "IssueSuggestion".
 */
export interface IssueSuggestion {
  id: string;
  /**
   * 버튼 문구.
   */
  label: string;
  patch?: GraphPatch;
}
/**
 * 그래프 초안에 적용할 변경(노드·엣지 추가, 엣지 삭제). 적용은 클라이언트가 초안에 한다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "GraphPatch".
 */
export interface GraphPatch {
  add_nodes?: NodeSpec[];
  add_edges?: EdgeSpec[];
  remove_edge_ids?: string[];
}
/**
 * 팀 안의 노드 하나입니다. 노드 종류에 따라 하는 일과 설정 항목이 다릅니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "NodeSpec".
 */
export interface NodeSpec {
  /**
   * 팀 안에서 노드를 가리키는 고유 이름입니다. 자동으로 만들어집니다.
   */
  id: string;
  /**
   * 노드가 하는 일의 종류입니다. 종류마다 설정 항목이 다릅니다.
   */
  type: string;
  /**
   * 노드 종류의 버전입니다. 비우면 최신 버전을 씁니다.
   */
  type_version?: number | null;
  /**
   * 팀 안에서 이 노드를 부르는 이름입니다. 비우면 연결된 정의의 이름을 씁니다.
   */
  label?: string | null;
  /**
   * 노드 종류가 정한 설정입니다. 에이전트 노드는 에이전트 설정을 덮어씁니다.
   */
  config?: {
    [k: string]: unknown;
  };
  /**
   * 캔버스 위 노드 위치입니다. 끌어서 옮기면 바뀝니다.
   */
  position?: Position | null;
  /**
   * 노드를 묶어 보이는 그룹 이름입니다.
   */
  group?: string | null;
  /**
   * 들어오는 값이 하나만 와도 시작할지(any) 모두 기다릴지(all) 정합니다.
   */
  join?: JoinRule | null;
  /**
   * 화면 배치(방향·포트 위치)입니다. 실행 결과에는 영향이 없습니다.
   */
  layout?: NodeLayout | null;
  [k: string]: unknown;
}
/**
 * 캔버스 좌표.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "Position".
 */
export interface Position {
  /**
   * 캔버스 가로 좌표입니다.
   */
  x: number;
  /**
   * 캔버스 세로 좌표입니다.
   */
  y: number;
}
/**
 * 노드 하나의 화면 배치입니다.
 *
 * 비우면 팀 배치, 편집기 설정, 노드 종류 기본값 순으로 따릅니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "NodeLayout".
 */
export interface NodeLayout {
  /**
   * 노드의 입력→출력 방향입니다(lr, tb, rl, bt, auto). 비우면 팀 설정을 따릅니다.
   */
  direction?: string | null;
  /**
   * 포트를 노드의 어느 면에 둘지입니다(키 in:이름·out:이름, 값 left·right·top·bottom·auto).
   */
  ports?: {
    [k: string]: string;
  } | null;
  [k: string]: unknown;
}
/**
 * 두 노드를 잇는 연결 하나입니다. 출발 노드의 포트에서 도착 노드의 포트로 이어집니다.
 *
 * 연결 종류에 따라 일이 넘어가는 방식이 다릅니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "EdgeSpec".
 */
export interface EdgeSpec {
  /**
   * 팀 안에서 연결을 가리키는 고유 이름입니다. 자동으로 만들어집니다.
   */
  id: string;
  source: Endpoint;
  target: Endpoint;
  /**
   * 연결이 하는 일의 종류입니다. 종류마다 설정 항목이 다릅니다.
   */
  kind: string;
  /**
   * 연결선 위에 보일 짧은 이름입니다.
   */
  label?: string | null;
  /**
   * 연결 종류가 정한 설정입니다(예: 지나갈 조건, 답변 이름).
   */
  config?: {
    [k: string]: unknown;
  };
  /**
   * 연결선 모양·경유점·라벨 위치입니다. 실행 결과에는 영향이 없습니다.
   */
  layout?: EdgeLayout | null;
  [k: string]: unknown;
}
/**
 * 연결선 하나의 화면 배치입니다. 비우면 팀 배치와 편집기 설정을 따릅니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "EdgeLayout".
 */
export interface EdgeLayout {
  /**
   * 연결선 모양 이름입니다(예: bezier, smoothstep). 비우면 팀 설정을 따릅니다.
   */
  shape?: string | null;
  /**
   * 꺾이는 모서리를 얼마나 둥글게 할지입니다(0~24).
   */
  radius?: number | null;
  /**
   * 경유점이 없을 때 선이 꺾이는 위치를 비율로 정합니다(0~1).
   */
  bend?: number | null;
  /**
   * 연결선이 지나갈 캔버스 위 점입니다(최대 16개).
   */
  waypoints?: Position[] | null;
  /**
   * 라벨을 선의 어느 지점에 둘지 비율로 정합니다(0.1~0.9).
   */
  label_t?: number | null;
  /**
   * 선에서 떨어뜨린 라벨의 가로·세로 거리입니다.
   */
  label_offset?: Position | null;
  [k: string]: unknown;
}
/**
 * 턴의 답변 하나(`run.reply` 이벤트에서 만든다).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ChatReply".
 */
export interface ChatReply {
  edge_id: string;
  node_id: string;
  agent_id?: string | null;
  label?: string | null;
  order?: number | null;
  final?: boolean;
  text: string;
}
/**
 * 채팅 동작입니다. 공통 설정에서 정하고, 팀마다 다르게 정할 수 있습니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ChatSettings".
 */
export interface ChatSettings {
  busy_policy?: BusyPolicy;
  reply_display?: ReplyDisplay;
  title?: ChatTitlePolicy;
  send_key?: SendKey;
  /**
   * 대화 목록의 정렬 방식입니다. 비우면 답을 기다리는 대화가 먼저 옵니다.
   */
  list_sort?: string | null;
  /**
   * 답을 기다리는 질문이 하나이고 글로 답할 수 있으면 입력창에 쓴 내용을 그 답으로 보냅니다.
   */
  answer_with_composer?: boolean;
  queue_after_restart?: QueueAfterRestart;
  /**
   * 중간에 끊긴 턴에 [이 지점부터 다시 실행] 버튼을 보입니다.
   */
  offer_resume?: boolean;
  [k: string]: unknown;
}
/**
 * `GET /conversations/{id}/turns` 항목. 대화 한 턴 = Run 하나.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ChatTurn".
 */
export interface ChatTurn {
  run_id: string;
  user_text: string;
  replies?: ChatReply[];
  /**
   * 이 턴에서 열린 상호작용(대기·닫힘 모두).
   */
  interactions?: Interaction[];
  status: RunStatus;
  usage?: Usage | null;
  started_at?: number | null;
  ended_at?: number | null;
  /**
   * 끊긴 턴을 이어 간 턴이면 원래 Run id.
   */
  resumed_from?: string | null;
}
/**
 * 조건 하나입니다. 결과의 '볼 값'을 '비교 방법'으로 '비교할 값'과 견줍니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ConditionItem".
 */
export interface ConditionItem {
  /**
   * 결과에서 비교할 값의 위치입니다(예: /output, /structured/verdict, /iteration).
   */
  path: string;
  /**
   * 값을 어떻게 비교할지입니다(예: 같음, 포함). 고를 수 있는 방법은 서버가 알려 줍니다.
   */
  op: string;
  /**
   * 볼 값과 견줄 값입니다. 비교 방법에 따라 비워 둡니다(예: 값이 있는지 볼 때).
   */
  value?: unknown;
  [k: string]: unknown;
}
/**
 * 조건 연산자 디스크립터(X22, `GET /condition-operators`). 조건 편집 화면이 이것으로 그린다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ConditionOperatorDescriptor".
 */
export interface ConditionOperatorDescriptor {
  id: string;
  title: string;
  description?: string;
  /**
   * `ConditionItem.value`의 JSON Schema. 빈 객체 = 아무 값(또는 값 없음).
   */
  value_schema?: {
    [k: string]: unknown;
  };
  /**
   * 비교할 실제 값의 JSON 형식 이름(string·number·integer·boolean·array·object·null). null = 제한 없음. 화면 힌트이며 다른 형식이면 연산자는 거짓을 돌려준다.
   */
  applies_to?: string[] | null;
  ui_hints?: UiHints | null;
}
/**
 * 연결을 지나갈 조건입니다.
 *
 * '모두 참'과 '하나라도 참'을 함께 쓰면 둘 다 맞아야 하고, 조건이 하나도 없으면 항상 지나갑니다.
 * '결과 뒤집기'를 켜면 결과를 반대로 씁니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ConditionSpec".
 */
export interface ConditionSpec {
  /**
   * 여기 적은 조건이 모두 맞아야 지나갑니다.
   */
  all?: ConditionItem[] | null;
  /**
   * 여기 적은 조건 중 하나만 맞아도 지나갑니다.
   */
  any?: ConditionItem[] | null;
  /**
   * 켜면 조건이 맞지 않을 때 지나갑니다. 비우면 꺼짐입니다.
   */
  negate?: boolean | null;
  [k: string]: unknown;
}
/**
 * 본문 파일 변경 하나(해시만 비교). 한쪽 해시가 없으면 추가·삭제.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ContentChange".
 */
export interface ContentChange {
  path: string;
  before_hash?: string | null;
  after_hash?: string | null;
}
/**
 * 대화. 팀 구성 하나를 골라 이어 가는 채팅.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "Conversation".
 */
export interface Conversation {
  id: string;
  /**
   * 고른 팀 구성(그래프) id.
   */
  graph_id: string;
  title?: string;
  created_at: number;
  updated_at: number;
  last_run_id?: string | null;
  /**
   * 노드 id → 백엔드 세션(이어 쓰기).
   */
  sessions?: {
    [k: string]: SessionRef;
  };
  archived?: boolean;
  /**
   * 프로젝트 id(0.8.0, 불투명 문자열). null = 프로젝트 없음.
   */
  project_id?: string | null;
}
/**
 * 백엔드 세션 참조(다음 턴 이어 쓰기).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "SessionRef".
 */
export interface SessionRef {
  backend: string;
  session_id: string;
  data?: {
    [k: string]: unknown;
  };
}
/**
 * `GET /conversations` 목록 항목, WS `conversation.updated` 내용.
 *
 * 목록 질의 `?project=`(0.8.0)는 같은 `project_id`인 대화만 준다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ConversationSummary".
 */
export interface ConversationSummary {
  id: string;
  graph_id: string;
  title?: string;
  created_at: number;
  updated_at: number;
  last_run_id?: string | null;
  /**
   * 마지막 턴 Run 상태.
   */
  last_status?: RunStatus | null;
  archived?: boolean;
  /**
   * 대기열에 있는 메시지 수.
   */
  queued?: number;
  /**
   * 대기열 중 재시작으로 멈춘(held) 메시지 수(queued에 포함).
   */
  held?: number;
  /**
   * 응답을 기다리는 상호작용 수(대화 목록·사이드바 배지).
   */
  pending_interactions?: number;
  /**
   * 프로젝트 id(0.8.0, 불투명 문자열). null = 프로젝트 없음.
   */
  project_id?: string | null;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ConversationUpdatedMessage".
 */
export interface ConversationUpdatedMessage {
  /**
   * 요청 상관 id(선택).
   */
  id?: string | null;
  type: "conversation.updated";
  payload: ConversationUpdatedPayload;
}
/**
 * 토픽 `conversation:<id>`: 새 턴·제목·상태·대기 중 상호작용 수가 바뀜.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ConversationUpdatedPayload".
 */
export interface ConversationUpdatedPayload {
  conversation: ConversationSummary;
}
/**
 * `POST /conversations` 요청. 응답은 `Conversation`(201).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "CreateConversationRequest".
 */
export interface CreateConversationRequest {
  graph_id: string;
  title?: string | null;
  /**
   * 대화의 프로젝트 id(0.8.0, 웹의 현재 프로젝트). 생략 = 프로젝트 없음.
   */
  project_id?: string | null;
}
/**
 * `POST /runs` 요청. 응답은 Run(202).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "CreateRunRequest".
 */
export interface CreateRunRequest {
  graph_id: string;
  /**
   * 생략하면 현재 저장된 버전.
   */
  version_hash?: string | null;
  /**
   * 그래프 입력 포트 이름 → 값. 입력 포트가 없으면 {}.
   */
  input?: {
    [k: string]: unknown;
  };
  /**
   * 시작 경로. 알려진 값은 RUN_ORIGINS(확장 가능).
   */
  origin?: string;
  /**
   * 이 실행의 프로젝트 id(0.8.0). 생략 = 프로젝트 없음. 존재 확인은 연동 모듈이 한다.
   */
  project_id?: string | null;
}
/**
 * 사이클을 허용하는 연결 종류의 반복 정책(0.7.0).
 *
 * 이 정책이 있는 연결 종류(사이클 연결)는 흐름 사이클을 닫을 수 있다. 엔진·검증은 연결 이름이
 * 아니라 이 속성이 있는지로 판단한다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "CyclePolicy".
 */
export interface CyclePolicy {
  /**
   * 기본 최대 반복 횟수. 엣지 config `max_iterations` → 설정 `flow.max_iterations` → 이 값 순으로 정한다.
   */
  max_iterations: number;
  /**
   * 화면 표시 문구(예: 회차 한도 칩).
   */
  title?: string | null;
}
/**
 * 노드 타입이 정의 하나에서 만들어진다는 표시(편집기 팔레트 근거).
 *
 * 예: 정의 종류 `kind`의 항목 하나를 끌어 놓으면 노드 config의 `field`에 그 id가 들어간다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "DefinitionBinding".
 */
export interface DefinitionBinding {
  /**
   * 정의 종류 이름(저장소 kind).
   */
  kind: string;
  /**
   * 정의 id를 넣을 노드 config 키.
   */
  field: string;
}
/**
 * 두 버전 비교 결과(`GET /{kind}/{id}/versions/{a}/diff/{b}`).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "DefinitionDiff".
 */
export interface DefinitionDiff {
  kind: string;
  id: string;
  from_hash: string;
  to_hash: string;
  changes?: DiffChange[];
  content_changes?: ContentChange[];
}
/**
 * 정의 문서 변경 하나. 비밀 위치면 `secret` = true이고 before·after는 가린 값이다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "DiffChange".
 */
export interface DiffChange {
  op: DiffOp;
  /**
   * 정의 문서 기준 RFC 6901 JSON Pointer(예: /nodes/3/label).
   */
  path: string;
  /**
   * 이전 값(add면 없음).
   */
  before?: unknown;
  /**
   * 새 값(remove면 없음).
   */
  after?: unknown;
  secret?: boolean;
}
/**
 * 정의 하나를 가리키는 키(종류 이름 + id). 표시 이름은 선택.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "DefinitionKey".
 */
export interface DefinitionKey {
  /**
   * 정의 종류 이름(예: agent, graph, resource).
   */
  kind: string;
  id: string;
  name?: string;
}
/**
 * 정의 하나의 범위 바꾸기(필드 `project` 하나를 고쳐 저장). null = 공용.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "DefinitionMove".
 */
export interface DefinitionMove {
  /**
   * 정의 종류 이름(예: agent, graph, resource).
   */
  kind: string;
  id: string;
  name?: string;
  /**
   * 지금 범위(null = 공용).
   */
  from?: string | null;
  /**
   * 옮길 범위(null = 공용).
   */
  to?: string | null;
  /**
   * 옮기려는 그 정의면 true. false는 참조 때문에 함께 옮기기를 권하는 정의.
   */
  required?: boolean;
}
/**
 * 정의를 쓰는 곳 하나(사용처 화면, 삭제 확인).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "DefinitionReference".
 */
export interface DefinitionReference {
  /**
   * 쓰는 쪽 정의 종류 이름.
   */
  kind: string;
  id: string;
  name?: string;
  /**
   * 그래프 안에서 쓰는 노드(그래프일 때).
   */
  node_ids?: string[];
  /**
   * 설정 층 첨부로 쓰면 그 층 id.
   */
  layer?: string | null;
}
/**
 * 정의 버전 이력 항목. 목록(`GET /graphs/{id}/versions`)은 `content` 없이,
 * 단건(`GET /graphs/{id}/versions/{version_hash}`)은 `content`를 담는다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "DefinitionVersion".
 */
export interface DefinitionVersion {
  kind: string;
  id: string;
  version_hash: string;
  saved_at: number;
  message?: string;
  content?: {
    [k: string]: unknown;
  } | null;
}
/**
 * 위임 설정입니다. 고른 위임 방식이 깊이를 정하지 않을 때 씁니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "DelegationSettings".
 */
export interface DelegationSettings {
  /**
   * 맡긴 일을 다시 맡기는 단계가 몇 번까지 이어질 수 있는지입니다. 비우면 위임 방식 기본값.
   */
  max_depth?: number | null;
  /**
   * 팀 안에 팀을 넣을 수 있는 깊이입니다. 비우면 제한이 없습니다.
   */
  max_nesting?: number | null;
  [k: string]: unknown;
}
/**
 * 위임 방식 디스크립터. 혼합 그래프 검증 규칙은 이 값으로 계산한다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "DelegationStrategyDescriptor".
 */
export interface DelegationStrategyDescriptor {
  id: string;
  title: string;
  description?: string;
  config_schema?: {
    [k: string]: unknown;
  };
  /**
   * 위임받는 노드에 적용되는 AgentSettings 필드(나머지는 화면에서 회색).
   */
  member_fields: string[];
  /**
   * 위임 깊이 한도. null = 제한 없음.
   */
  max_depth: number | null;
  /**
   * 위임받는 노드가 흐름 연결을 내보낼 수 있는지.
   */
  allows_outgoing_flow?: boolean;
  /**
   * 위임자 백엔드에 필요한 능력 이름(BackendCapabilities 필드).
   */
  requires_backend_capability?: string | null;
  /**
   * 위임받는 노드가 열 수 있는 상호작용 종류. null = 제한 없음.
   */
  member_interaction_kinds?: string[] | null;
  /**
   * 다른 composable 위임 방식과 한 위임자에서 합쳐 실행할 수 있다(혼합 위임). false인 방식이 다른 방식과 섞이면 `team.mixed_strategies`.
   */
  composable?: boolean;
  /**
   * 위임받는 노드가 위임자 세션 안에서 실행되는지(0.8.0). false면 대상이 자기 세션에서 돌아 위임자 세션에 대상의 상호작용 권한을 더하지 않는다.
   */
  shares_session?: boolean;
  ui_hints?: UiHints | null;
}
/**
 * `POST /projects/{id}/delete-plan` 응답: 삭제하면 무엇이 바뀌는지(저장하지 않음).
 *
 * 삭제는 `DELETE /projects/{id}?mode=<ProjectDeleteMode>`(생략 = `default_mode`)로 한다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "DeletePlan".
 */
export interface DeletePlan {
  project_id: string;
  /**
   * 이 프로젝트 전용 정의(공용으로 옮기거나 함께 삭제).
   */
  definitions?: DefinitionKey[];
  default_mode?: ProjectDeleteMode;
  warnings?: Issue[];
}
/**
 * 저장하지 않은 초안 그래프로 계산하는 요청(검증·계획 미리보기). 저장하지 않는다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "DraftGraphRequest".
 */
export interface DraftGraphRequest {
  graph: Graph;
}
/**
 * 팀 구성입니다. 노드(에이전트 등)와 그 사이 연결로 일이 흘러가는 순서를 정합니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "Graph".
 */
export interface Graph {
  kind?: "graph";
  /**
   * 가리킬 때 쓰는 고유 이름입니다. 파일 이름으로도 쓰며 영문·숫자·-·_만 씁니다.
   */
  id: string;
  /**
   * 파일 형식 번호입니다. 직접 바꾸지 않습니다.
   */
  schema_version?: number;
  /**
   * 팀 구성을 부르는 이름입니다. 목록과 채팅에 보입니다.
   */
  name: string;
  /**
   * 이 팀이 하는 일을 적습니다. 목록에 함께 보입니다.
   */
  description?: string;
  /**
   * 찾기·거르기에 쓰는 꼬리표입니다.
   */
  labels?: string[];
  /**
   * 다른 도구가 읽는 자유 속성입니다. 보통은 비워 둡니다.
   */
  attributes?: {
    [k: string]: unknown;
  };
  /**
   * 이 팀의 에이전트·채팅·위임 설정입니다. 비운 항목은 공통 설정을 따릅니다.
   */
  settings?: GraphSettings | null;
  /**
   * 팀이 받는 입력입니다. 실행할 때 포트 이름마다 값을 넣습니다.
   */
  inputs?: PortDef[];
  /**
   * 팀이 내보내는 출력입니다.
   */
  outputs?: PortDef[];
  /**
   * 팀에 놓인 노드입니다. 캔버스에서 고칩니다.
   */
  nodes?: NodeSpec[];
  /**
   * 노드 사이의 연결입니다. 캔버스에서 고칩니다.
   */
  edges?: EdgeSpec[];
  /**
   * 노드를 묶어 보이는 그룹입니다.
   */
  groups?: {
    [k: string]: unknown;
  }[];
  /**
   * 이전 형식의 실행 범위입니다. 새 설정은 팀 설정의 실행 범위를 씁니다.
   */
  limits?: Limits | null;
  /**
   * 편집기 화면 상태(보기 위치·배치 등)입니다. 직접 고치지 않아도 됩니다.
   */
  ui?: {
    [k: string]: unknown;
  };
  /**
   * 이 정의가 속한 프로젝트입니다. 비우면 공용이라 모든 프로젝트에서 보입니다.
   */
  project?: string | null;
  [k: string]: unknown;
}
/**
 * 팀 구성 층 설정: 에이전트 설정과 채팅·편집기·위임·상호작용 설정. 비우면 공통 설정.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "GraphSettings".
 */
export interface GraphSettings {
  /**
   * 에이전트를 실제로 돌릴 실행 방식입니다. 비우면 팀 설정이나 공통 설정의 값을 씁니다.
   */
  backend?: string | null;
  /**
   * 에이전트가 쓸 모델입니다. 목록에서 고르거나 직접 입력합니다. 비우면 팀·공통 설정 값입니다.
   */
  model?: string | null;
  /**
   * 에이전트의 기본 지침입니다. 비우면 팀 설정이나 공통 설정의 값을 씁니다.
   */
  system_prompt?: string | null;
  /**
   * 에이전트가 쓸 수 있는 도구 이름입니다. 비우면 실행 백엔드의 기본 도구를 씁니다.
   */
  tools?: string[] | null;
  /**
   * 에이전트가 쓰지 못하게 막을 도구 이름입니다.
   */
  disallowed_tools?: string[] | null;
  /**
   * 에이전트가 쓸 폴더·명령·네트워크 범위입니다. 여기서 정하면 공통·팀 설정의 범위를 통째로 바꿉니다.
   */
  limits?: Limits | null;
  /**
   * 실행 중 hook(도구 실행 전후에 도는 명령)·MCP(외부 도구 서버) 호출을 기록할지 정합니다.
   */
  observe?: ObserveSettings | null;
  /**
   * 붙인 지침·파일·외부 도구 서버(MCP) 등입니다. 공통·팀 설정에서 붙인 것과 함께 쓰입니다.
   */
  resources?: ResourceAttachment[] | null;
  /**
   * 에이전트가 일하는 폴더입니다. 비우면 프로젝트나 서버 설정의 작업 폴더를 씁니다.
   */
  working_directory?: string | null;
  /**
   * 넘겨받은 값을 프롬프트로 합치는 틀입니다. {inputs}·{message}·{node}를 쓰고, 비우면 {inputs} 그대로입니다.
   */
  prompt_template?: string | null;
  /**
   * 값이 여러 개 들어올 때 값 하나를 적는 틀입니다. {source}(보낸 노드 이름)·{value}·{index} 등을 씁니다.
   */
  prompt_input_template?: string | null;
  /**
   * 값이 하나만 들어올 때 쓰는 틀입니다. 변수는 여러 값일 때와 같습니다.
   */
  prompt_single_input_template?: string | null;
  /**
   * 여러 값을 이을 때 사이에 넣는 문자열입니다. 기본은 빈 줄 하나입니다.
   */
  prompt_input_separator?: string | null;
  /**
   * 다음 턴에 대화를 이어 쓸지(continue) 매번 새로 시작할지(fresh) 정합니다. 비우면 이어 씁니다.
   */
  session?: SessionPolicy | null;
  /**
   * 고른 실행 백엔드가 따로 받는 설정입니다. 비밀 값은 secret://이름으로만 적습니다.
   */
  backend_options?: {
    [k: string]: unknown;
  } | null;
  /**
   * 이 팀의 채팅 동작입니다. 비운 항목은 공통 설정을 따릅니다.
   */
  chat?: ChatSettings | null;
  /**
   * 이 팀을 편집할 때의 기본 동작입니다.
   */
  editor?: EditorSettings | null;
  /**
   * 이 팀에서 일을 맡기는 깊이 한도입니다.
   */
  delegation?: DelegationSettings | null;
  /**
   * 실행 중 질문·승인 요청을 기다리는 방식입니다.
   */
  interaction?: InteractionSettings | null;
  /**
   * 설정 항목마다 공통·팀·에이전트 설정을 합치는 방법을 바꿉니다(예: /limits → intersect).
   */
  settings_merge?: {
    [k: string]: string;
  } | null;
  /**
   * 반복 횟수와 노드 실행 총 한도입니다.
   */
  flow?: FlowSettings | null;
  [k: string]: unknown;
}
/**
 * 팀 구성 편집기 동작입니다. 새 연결의 기본 종류, 연결선 모양, 노드 방향을 정합니다.
 *
 * 모양과 방향을 비워 두면 연결선이 노드를 피해 가는 자동 경로로 그립니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "EditorSettings".
 */
export interface EditorSettings {
  /**
   * 새 연결을 그을 때 먼저 고를 연결 종류입니다. 비우면 이을 수 있는 첫 종류입니다.
   */
  default_edge_kind?: string | null;
  /**
   * 방향을 정하지 않은 팀의 노드 방향입니다(lr, tb, rl, bt, auto). 새 팀은 auto(연결선이 노드를 피해 감)입니다. 비우면 노드 종류 기본값, 없으면 lr.
   */
  default_direction?: string | null;
  /**
   * 팀이 모양을 정하지 않았을 때의 연결선 모양입니다(예: bezier, smoothstep, auto). 비우면 자동 경로(연결선이 노드를 피해 감)입니다.
   */
  default_edge_shape?: string | null;
  /**
   * 첫 에이전트를 놓을 때 입구·답변 연결을 한 번 만들어 줍니다. 비우면 켬입니다.
   */
  auto_connect_io?: boolean | null;
  [k: string]: unknown;
}
/**
 * 실행 중 상호작용(되묻기·승인·검토) 대기 설정.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "InteractionSettings".
 */
export interface InteractionSettings {
  /**
   * 실행 중 질문·승인 요청에 답을 기다리는 시간입니다. 비우면 무기한 기다립니다.
   */
  timeout_seconds?: number | null;
  on_timeout?: OnTimeout;
  [k: string]: unknown;
}
/**
 * 반복·실행 한도입니다. 팀 설정에서 비운 항목은 공통 설정 값을 따릅니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "FlowSettings".
 */
export interface FlowSettings {
  /**
   * 되돌아가는 연결이 반복할 수 있는 최대 횟수입니다. 비우면 연결 종류 기본값입니다.
   */
  max_iterations?: number | null;
  /**
   * 한 실행에서 노드가 도는 총횟수 한도입니다. 넘으면 실행을 실패로 끝냅니다. 비우면 제한이 없습니다.
   */
  max_node_runs?: number | null;
  [k: string]: unknown;
}
/**
 * 이름 있는 입출력 포트 하나.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "PortDef".
 */
export interface PortDef {
  /**
   * 입력·출력을 가리키는 이름입니다. 연결과 실행 입력이 이 이름을 씁니다.
   */
  name: string;
  /**
   * 화면에 보일 이름입니다. 비우면 포트 이름을 씁니다.
   */
  label?: string | null;
  /**
   * 이 포트로 무엇이 오가는지 적습니다.
   */
  description?: string | null;
  /**
   * 이 포트 값의 형식(JSON Schema)입니다. 연결이 맞지 않으면 경고합니다.
   */
  schema?: {
    [k: string]: unknown;
  } | null;
}
/**
 * 초안 그래프의 노드 하나로 계산하는 요청(유효 설정·묶음 미리보기). 저장하지 않는다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "DraftNodeRequest".
 */
export interface DraftNodeRequest {
  graph: Graph;
  node_id: string;
}
/**
 * `POST /graphs/{id}/duplicate` 요청. 응답은 새 그래프 `VersionedGraph`(201).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "DuplicateGraphRequest".
 */
export interface DuplicateGraphRequest {
  /**
   * 새 팀 구성 id. 이미 있으면 409 already_exists.
   */
  id: string;
  /**
   * 새 팀 구성 이름.
   */
  name: string;
}
/**
 * 어떤 노드 역할끼리 이을 수 있는지. 빈 목록 = 제한 없음.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "EdgeConnects".
 */
export interface EdgeConnects {
  /**
   * 출발 노드 역할 목록.
   */
  source?: string[];
  /**
   * 도착 노드 역할 목록.
   */
  target?: string[];
}
/**
 * 이 연결의 출발 노드가 실행 중 열 수 있는 상호작용 종류.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "EdgeInteraction".
 */
export interface EdgeInteraction {
  /**
   * 상호작용 종류 id 목록. 엣지 config kinds로 좁힐 수 있다.
   */
  kinds?: string[];
}
/**
 * 이 연결로 이어진 아래 노드를 위 노드 실행 안에서 부를 때 쓸 위임 방식.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "EdgeInvocation".
 */
export interface EdgeInvocation {
  /**
   * 위임 방식(X12) id. 엣지 config strategy로 덮어쓸 수 있다.
   */
  strategy: string;
}
/**
 * 연결 종류의 기본 포트 이름. 편집기 토글(입구·답변·묻기)이 엣지를 만들 때 쓴다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "EdgePortPair".
 */
export interface EdgePortPair {
  /**
   * 출발 노드 포트 이름.
   */
  source?: string | null;
  /**
   * 도착 노드 포트 이름.
   */
  target?: string | null;
}
/**
 * 엣지 타입(연결 종류) 디스크립터(X2). 엔진·편집기는 이름이 아니라 이 속성으로 구분한다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "EdgeTypeDescriptor".
 */
export interface EdgeTypeDescriptor {
  id: string;
  version?: number;
  title: string;
  description?: string;
  scheduling?: EdgeScheduling;
  invocation?: EdgeInvocation | null;
  /**
   * 연결 가능한 노드 역할. 없으면 제한 없음.
   */
  connects?: EdgeConnects | null;
  interaction?: EdgeInteraction | null;
  /**
   * 새 엣지의 기본 포트. 없으면 노드 타입 포트 순서에서 첫 호환 포트.
   */
  default_ports?: EdgePortPair | null;
  /**
   * 답변 연결이면 답변 속성의 config 위치. null = config에서 읽지 않음.
   */
  reply_fields?: ReplyFields | null;
  /**
   * 있으면 사이클 연결이다: 흐름 사이클을 닫을 수 있고 지나갈 때 반복 영역을 다시 연다. null = 사이클 불가.
   */
  cycle?: CyclePolicy | null;
  /**
   * 출발 노드가 실패해도 지나갈 수 있는 연결(실패 처리). 화면·검증 표시용이며 실제 통과 여부는 연결 종류 구현이 정한다.
   */
  handles_failure?: boolean;
  config_schema?: {
    [k: string]: unknown;
  };
  ui_schema?: {
    [k: string]: unknown;
  };
  ui_hints?: UiHints | null;
}
/**
 * 답변(exit) 연결이 엣지 config의 어디에 답변 속성을 두는지.
 *
 * 값은 엣지 `config` 기준 JSON Pointer다. 플러그인이 선언하며 계약에는 키 이름 기본값이 없다.
 * 생략한 속성은 기본 규칙(label = 엣지 label, order 없음, final = true, stream = false)을 쓴다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ReplyFields".
 */
export interface ReplyFields {
  /**
   * 답변 표시 이름의 위치.
   */
  label?: string | null;
  /**
   * 답변 순서의 위치.
   */
  order?: string | null;
  /**
   * 최종 답변 여부의 위치.
   */
  final?: string | null;
  /**
   * 흘려 보내기 여부의 위치.
   */
  stream?: string | null;
}
/**
 * 층을 병합한 유효 설정. `provenance`는 잎 값의 JSON Pointer → 층 id.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "EffectiveSettings".
 */
export interface EffectiveSettings {
  value: AgentSettings;
  provenance?: {
    [k: string]: string;
  };
  layers?: SettingsLayerInfo[];
  /**
   * 병합 경고(예: 아래 층이 실행 범위를 넓힘). path = 필드.
   */
  warnings?: Issue[];
  /**
   * 이 자리(예: 위임받는 노드)에서 적용되지 않는 필드의 JSON Pointer 목록.
   */
  inapplicable?: string[];
}
/**
 * 유효 설정을 만든 층 하나. 층 목록은 데이터다(코드에 고정된 층 이름 없음).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "SettingsLayerInfo".
 */
export interface SettingsLayerInfo {
  /**
   * 층 id(출처 표시 키).
   */
  id: string;
  /**
   * 화면 이름.
   */
  label?: string;
  /**
   * 층 값이 온 곳(예: 정의 종류/id, 파일). 표시용.
   */
  source?: string | null;
}
/**
 * 팀 구성의 입구 하나(입구 연결의 도착 노드).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "EntrySlot".
 */
export interface EntrySlot {
  edge_id: string;
  node_id: string;
  label?: string | null;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ErrorMessage".
 */
export interface ErrorMessage {
  /**
   * 요청 상관 id(선택).
   */
  id?: string | null;
  type: "error";
  payload: ErrorInfo;
}
/**
 * REST 오류 응답 본문. 모든 4xx/5xx가 이 형식 하나를 쓴다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ErrorResponse".
 */
export interface ErrorResponse {
  error: ErrorInfo;
}
/**
 * 내보낼 파일 하나(내용은 담지 않는다).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ExportFile".
 */
export interface ExportFile {
  /**
   * 내보내기 루트 기준 상대 경로(`/` 구분).
   */
  path: string;
  media_type?: string | null;
  /**
   * 바이트 수.
   */
  size: number;
  action?: ExportFileAction;
}
/**
 * 내보내기 미리보기 결과.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ExportPlan".
 */
export interface ExportPlan {
  files?: ExportFile[];
  warnings?: Issue[];
}
/**
 * `POST /exports/plan`(미리보기)·`POST /exports/archive`(보관 파일) 요청.
 *
 * 미리보기에 `root`를 주면 그 폴더 목적지 기준으로 `ExportFile.action`(overwrite·conflict)을
 * 계산한다. 없으면 보관 파일 기준이라 모두 create다. 보관 파일 요청은 `root`·`subdir`를 무시한다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ExportRequest".
 */
export interface ExportRequest {
  /**
   * 내보내기 형식 id.
   */
  exporter: string;
  items?: ExportSelection[];
  /**
   * 형식의 `config_schema`로 검증되는 옵션.
   */
  options?: {
    [k: string]: unknown;
  };
  /**
   * 폴더 목적지 `ExportRootInfo.id`(미리보기 충돌 계산용).
   */
  root?: string | null;
  /**
   * 루트 기준 상대 폴더. 비우면 루트 바로 아래.
   */
  subdir?: string;
}
/**
 * 내보낼 정의 하나.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ExportSelection".
 */
export interface ExportSelection {
  /**
   * 정의 종류 이름.
   */
  kind: string;
  id: string;
}
/**
 * `POST /exports/write` 응답. `files[].action`은 실제로 한 동작이다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ExportResult".
 */
export interface ExportResult {
  files?: ExportFile[];
  warnings?: Issue[];
}
/**
 * 폴더 쓰기를 허용한 루트 하나(`GET /exports/roots`, 설치자 설정 `exports.roots`).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ExportRootInfo".
 */
export interface ExportRootInfo {
  id: string;
  label?: string;
  /**
   * 절대 경로(표시용).
   */
  path: string;
}
/**
 * `POST /exports/write` 요청. 허용 루트 아래 `subdir`에만 쓴다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ExportWriteRequest".
 */
export interface ExportWriteRequest {
  /**
   * 내보내기 형식 id.
   */
  exporter: string;
  items?: ExportSelection[];
  /**
   * 형식의 `config_schema`로 검증되는 옵션.
   */
  options?: {
    [k: string]: unknown;
  };
  /**
   * `ExportRootInfo.id`(필수).
   */
  root: string;
  /**
   * 루트 기준 상대 폴더. 비우면 루트 바로 아래.
   */
  subdir?: string;
  on_conflict?: ExportConflictPolicy;
}
/**
 * 내보내기 형식 디스크립터(`GET /exporters`).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ExporterDescriptor".
 */
export interface ExporterDescriptor {
  /**
   * 내보내기 형식 id(레지스트리 키).
   */
  id: string;
  title: string;
  description?: string;
  /**
   * 옵션(`ExportRequest.options`)의 JSON Schema.
   */
  config_schema?: {
    [k: string]: unknown;
  };
  /**
   * 이 형식이 내보낼 수 있는 정의 종류 이름.
   */
  kinds?: string[];
}
/**
 * `feature_unavailable`(HTTP 409) 오류의 `error.details`.
 *
 * 켜진 모듈 안에서 선택 포트를 줄 모듈이 없어 그 동작만 꺼졌을 때 쓴다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "FeatureUnavailableDetails".
 */
export interface FeatureUnavailableDetails {
  /**
   * 요청을 받은 모듈 id.
   */
  module: string;
  /**
   * 빠진 포트 이름.
   */
  port: string;
}
/**
 * `GET /graphs` 목록 항목.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "GraphSummary".
 */
export interface GraphSummary {
  id: string;
  name: string;
  description?: string;
  labels?: string[];
  version_hash: string;
  saved_at?: number | null;
  node_count: number;
  edge_count: number;
  /**
   * 입구 노드 표시 이름(입구 연결의 도착 노드). null = 계산하지 않음.
   */
  entry_labels?: string[] | null;
  /**
   * 검증 요약. null = 계산하지 않음(`?validate=false` 등).
   */
  validation?: GraphValidationSummary | null;
  /**
   * 정의의 프로젝트 id(0.8.0). null = 공용. 웹이 이 값으로 목록을 거른다.
   */
  project?: string | null;
}
/**
 * 팀 구성 검증 결과 요약(엔진 검증 + 팀 검증을 합친 것).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "GraphValidationSummary".
 */
export interface GraphValidationSummary {
  /**
   * 실행을 막는 이슈가 있는지.
   */
  blocks_run: boolean;
  error_count?: number;
  warning_count?: number;
  /**
   * 나온 이슈 코드(중복 없음, 표시·필터용).
   */
  codes?: string[];
}
/**
 * 이 팀의 화면 배치 기본값입니다(노드 방향·연결선 모양).
 *
 * 비우면 편집기 설정, 노드·연결 종류 기본값 순으로 따릅니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "GraphUiLayout".
 */
export interface GraphUiLayout {
  /**
   * 이 팀의 기본 노드 방향입니다(lr, tb, rl, bt, auto). 비우면 편집기 설정을 따릅니다.
   */
  direction?: string | null;
  /**
   * 이 팀의 기본 연결선 모양입니다(예: bezier, smoothstep, auto). 비우면 편집기 설정을 따릅니다.
   */
  edge_shape?: string | null;
  /**
   * 연결 종류마다 다른 모양을 씁니다. 팀 기본 모양보다 우선합니다.
   */
  edge_shape_by_kind?: {
    [k: string]: string;
  } | null;
  [k: string]: unknown;
}
/**
 * 여러 실행 집계 "누가 누구에게 몇 번" 한 칸.
 *
 * 0.6.0부터 셀 모양 `{from, to, via?, count}`(로그 handoff)도 함께 싣는다.
 * `from`=`source`, `to`=`target`, `via`=`kind`이고 한쪽만 주면 다른 쪽을 채운다(하위 호환).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "HandoffCount".
 */
export interface HandoffCount {
  /**
   * 넘긴 쪽 에이전트 정의 id(없으면 노드 id).
   */
  source: string;
  /**
   * 받은 쪽 에이전트 정의 id(없으면 노드 id).
   */
  target: string;
  /**
   * 연결 종류 id 또는 span 종류.
   */
  kind?: string | null;
  count: number;
  /**
   * = source(셀 모양 별칭).
   */
  from?: string | null;
  /**
   * = target(셀 모양 별칭).
   */
  to?: string | null;
  /**
   * = kind(전달 수단, 셀 모양 별칭).
   */
  via?: string | null;
}
/**
 * `GET /runs/handoffs` 응답: 여러 실행의 위임·넘기기 집계.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "HandoffMatrix".
 */
export interface HandoffMatrix {
  cells?: HandoffCount[];
  /**
   * 집계에 쓴 실행 수.
   */
  runs?: number;
}
/**
 * `GET /health`: 준비 신호(서버가 요청을 받을 수 있으면 200). 토큰 없이 읽는다, 비밀 없음.
 *
 * 셸·스크립트가 서버 기동을 기다릴 때 폴링한다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "HealthResponse".
 */
export interface HealthResponse {
  status?: "ok";
  server_version: string;
  contracts_version: string;
}
/**
 * 가져올 수 있는 항목 하나.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ImportCandidate".
 */
export interface ImportCandidate {
  /**
   * 이 미리보기 안의 후보 키(가져오기 요청에 쓴다).
   */
  id: string;
  /**
   * 원본 경로(표시용).
   */
  path: string;
  /**
   * 만들 정의 종류 이름(저장소 kind).
   */
  kind: string;
  /**
   * 리소스면 리소스 종류 id.
   */
  resource_type?: string | null;
  name: string;
  /**
   * 워크스페이스에 쓸 제안 id.
   */
  suggested_id: string;
  /**
   * 바이트.
   */
  size?: number | null;
  content_hash?: string | null;
  /**
   * 같은 id의 정의가 이미 있음.
   */
  conflict?: boolean;
  warnings?: ImportWarning[];
}
/**
 * 후보 하나의 경고(예: 비밀 의심). 값은 싣지 않고 위치만 싣는다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ImportWarning".
 */
export interface ImportWarning {
  code: string;
  message: string;
  /**
   * 문제가 된 키·경로(값 아님).
   */
  keys?: string[];
}
/**
 * `POST /resources/import/preview` 응답.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ImportPreview".
 */
export interface ImportPreview {
  source: string;
  /**
   * 스캔한 원본 위치(표시용).
   */
  root?: string | null;
  candidates?: ImportCandidate[];
  /**
   * 후보가 되지 못한 항목의 경고(예: 링크라서 건너뜀 `import.skipped_link`, keys = 원본 경로). 가져오기를 막지 않는다.
   */
  warnings?: ImportWarning[];
}
/**
 * `POST /resources/import/preview` 요청. 원본을 읽기만 하고 아무것도 쓰지 않는다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ImportPreviewRequest".
 */
export interface ImportPreviewRequest {
  source: string;
}
/**
 * `POST /resources/import` 요청. 후보는 서버가 다시 스캔해 확인한다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ImportRequest".
 */
export interface ImportRequest {
  source: string;
  items?: ImportSelection[];
  /**
   * 만든 정의에 찍을 프로젝트 id(0.8.0). 생략 = 공용(지금과 같음).
   */
  project?: string | null;
}
/**
 * 가져올 후보 하나와 충돌 처리.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ImportSelection".
 */
export interface ImportSelection {
  candidate_id: string;
  /**
   * 쓸 id. 비우면 제안 id.
   */
  target_id?: string | null;
  on_conflict?: ConflictPolicy;
}
/**
 * `POST /resources/import` 응답.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ImportResult".
 */
export interface ImportResult {
  source: string;
  items?: AppliedItemInfo[];
}
/**
 * `GET /resources/import/sources` 항목: 가져올 수 있는 출처 디스크립터 하나.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ImportSourceDescriptor".
 */
export interface ImportSourceDescriptor {
  /**
   * 출처 id(서버가 정함).
   */
  id: string;
  title: string;
  description?: string;
  /**
   * 원본 위치(표시용).
   */
  path?: string | null;
  /**
   * 지금 읽을 수 있는지.
   */
  available?: boolean;
}
/**
 * 노드가 열 수 있는 상호작용(나가는 연결의 `interaction` 속성에서 계산).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "InteractionGrant".
 */
export interface InteractionGrant {
  /**
   * 허용 상호작용 종류 id.
   */
  kinds?: string[];
  /**
   * 응답 대기 한도. null = 설정값을 따른다.
   */
  timeout_seconds?: number | null;
  /**
   * 한도 초과 시 동작. null = 설정값을 따른다.
   */
  on_timeout?: OnTimeout | null;
}
/**
 * 상호작용 종류 디스크립터. 화면은 이것으로 카드·폼을 그린다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "InteractionKindDescriptor".
 */
export interface InteractionKindDescriptor {
  id: string;
  version?: number;
  title: string;
  description?: string;
  /**
   * 요청 payload의 JSON Schema.
   */
  request_schema?: {
    [k: string]: unknown;
  };
  /**
   * 기본 응답 JSON Schema. 요청마다 자기 것으로 바꿀 수 있다.
   */
  response_schema?: {
    [k: string]: unknown;
  };
  /**
   * 채팅 입력창 답을 넣을 응답 위치(JSON Pointer). null이면 입력창 답변 불가.
   */
  free_text_path?: string | null;
  /**
   * 만료·취소 때 요청자에게 돌려줄 응답.
   */
  expire_response?: {
    [k: string]: unknown;
  } | null;
  /**
   * renderer = 화면 렌더러 이름(모르면 스키마 폼).
   */
  ui_hints?: UiHints | null;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "InteractionUpdatedMessage".
 */
export interface InteractionUpdatedMessage {
  /**
   * 요청 상관 id(선택).
   */
  id?: string | null;
  type: "interaction.updated";
  payload: InteractionUpdatedPayload;
}
/**
 * 토픽 `interactions`: 구독 직후 현재 대기 목록을 하나씩 보낸 뒤, 상태가 바뀔 때마다 보낸다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "InteractionUpdatedPayload".
 */
export interface InteractionUpdatedPayload {
  interaction: Interaction;
}
/**
 * `POST /logs/aggregate` 본문. 차원·지표·필터 이름은 열린 문자열.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogAggregateRequest".
 */
export interface LogAggregateRequest {
  group_by?: string[];
  metric: string;
  filter?: {
    [k: string]: unknown;
  };
  /**
   * day·hour 차원의 시간대(IANA). 없으면 서버.
   */
  tz?: string | null;
}
/**
 * 집계 결과 한 줄. 값이 없는 지표는 null이다(0으로 채우지 않음).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogAggregateRow".
 */
export interface LogAggregateRow {
  /**
   * 차원 이름 → 값.
   */
  keys?: {
    [k: string]: string | null;
  };
  value?: number | null;
}
/**
 * 오프라인 보관본(`GET /logs/archive?format=json`, 형식 버전 1).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogArchive".
 */
export interface LogArchive {
  /**
   * 보관본 형식 버전.
   */
  version?: number;
  exported_at: number;
  filter?: {
    [k: string]: unknown;
  };
  taxonomy?: LogTaxonomy;
  lanes?: LogLane[];
  sessions?: LogSessionSummary[];
  events?: LogEvent[];
  /**
   * 이벤트 uid → 근거 연결.
   */
  evidence_links?: {
    [k: string]: LogEvidenceLink[];
  };
  truncated?: boolean;
}
/**
 * 로그 범주의 표시 이름·설명·보이기·색. 분류 체계에 없는 범주도 이름 = id로 보인다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogTaxonomy".
 */
export interface LogTaxonomy {
  /**
   * 범주마다 표시 이름·설명·색·보이기를 정합니다.
   */
  categories?: {
    [k: string]: LogCategory;
  };
  /**
   * 필터 칩 등에 보일 범주 순서입니다. 빠진 범주는 뒤에 이름 순으로 붙습니다.
   */
  order?: string[] | null;
  [k: string]: unknown;
}
/**
 * 범주 하나의 표시 정보. 비운 항목은 기본 분류 체계 값을 따른다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogCategory".
 */
export interface LogCategory {
  /**
   * 범주를 화면에 보일 이름입니다. 비우면 범주 id를 씁니다.
   */
  label?: string | null;
  /**
   * 이 범주가 무엇을 뜻하는지 적습니다.
   */
  description?: string | null;
  /**
   * 끄면 목록·타임라인에서 기본으로 숨깁니다.
   */
  visible?: boolean | null;
  /**
   * danger면 이 범주를 오류로 표시합니다(그 밖에 warning, success, info, neutral).
   */
  tone?: string | null;
  /**
   * 색 이름이나 CSS 색입니다. 화면이 알아보지 못하면 기본 색입니다.
   */
  color?: string | null;
  [k: string]: unknown;
}
/**
 * 에이전트 줄(thread)의 표시 정보. 서브에이전트면 부모가 있다. label이 없으면 id를 보인다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogLane".
 */
export interface LogLane {
  id: string;
  label?: string | null;
  parent_id?: string | null;
}
/**
 * `GET /logs/sessions` 항목: 세션 하나의 요약.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogSessionSummary".
 */
export interface LogSessionSummary {
  session: string;
  sources?: string[];
  /**
   * 첫 입력 등에서 뽑은 짧은 제목.
   */
  title?: string;
  cwd?: string;
  repo_root?: string;
  /**
   * 프로젝트 묶음.
   */
  project?: LogProjectRef | null;
  first_time?: number | null;
  last_time?: number | null;
  events?: number;
  errors?: number;
  /**
   * 에이전트 줄(thread) 수.
   */
  thread_count?: number;
  models?: string[];
  /**
   * 응답(message_id)별 한 번만 센 토큰 합.
   */
  tokens?: LogTokenTotals | null;
}
/**
 * 프로젝트 묶음(묶기 규칙을 적용한 결과).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogProjectRef".
 */
export interface LogProjectRef {
  id: string;
  label?: string;
}
/**
 * 토큰 합 분해. 값이 없으면 null(0으로 채우지 않음).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogTokenTotals".
 */
export interface LogTokenTotals {
  input?: number | null;
  output?: number | null;
  cache_read?: number | null;
  cache_creation?: number | null;
  total?: number | null;
}
/**
 * 정규화 로그 이벤트 하나(색인 사본, 비밀 가림 후).
 *
 * 목록(`LogEventPage`·`LogTimeline`)에서는 `detail`·`raw`가 null이고 `summary`만 있다.
 * 본문은 상세(`LogEventDetail.event`)에서만 싣는다.
 * 원본 경로는 출처 기준 상대 경로(`ref`)만 싣는다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogEvent".
 */
export interface LogEvent {
  /**
   * 안정 식별자(identity의 sha256 앞 24자).
   */
  uid: string;
  /**
   * 색인 순번(키셋 페이지 커서의 기준).
   */
  seq: number;
  /**
   * 로그 출처 id(진단 이벤트는 `diagnostic`).
   */
  source: string;
  /**
   * 출처 안 단위(루트 기준 상대 경로, run id 등).
   */
  ref?: string;
  /**
   * 색인에 들어온 시각(Unix epoch 초).
   */
  observed_at: number;
  /**
   * 범주 id(열린 문자열, 분류 체계로 표시).
   */
  category: string;
  title?: string;
  /**
   * 목록용 짧은 본문(최대 수백 자).
   */
  summary?: string;
  /**
   * 단계(예: info, start, complete).
   */
  stage?: string;
  /**
   * 출처가 준 상태(열린 문자열, 예: ok, failed). 오류 판정에 쓰지 않는다.
   */
  status?: string;
  /**
   * 에이전트 줄 id(메인·서브에이전트 세션 등).
   */
  thread?: string;
  role?: string;
  actor?: string;
  /**
   * 보낸 쪽.
   */
  from?: string[];
  /**
   * 받는 쪽.
   */
  to?: string[];
  /**
   * 전달 수단(예: 위임 도구 이름).
   */
  via?: string;
  tool?: string;
  /**
   * 도구 호출 id(start·complete 짝의 키).
   */
  call_id?: string;
  turn_id?: string;
  /**
   * 모델 응답 id(여러 행으로 나뉜 응답을 묶음).
   */
  message_id?: string;
  session?: string;
  cwd?: string;
  /**
   * worktree면 본 저장소 경로(수집 때 계산).
   */
  repo_root?: string;
  model?: string;
  /**
   * 플랫폼 실행 id(플랫폼 실행 출처·상관).
   */
  run_id?: string;
  node_path?: string[];
  /**
   * 원본 시각(Unix epoch 초). 모르면 null.
   */
  time?: number | null;
  /**
   * 명시 id 짝(같은 thread+call_id의 start/complete)으로 계산한 소요 시간.
   */
  duration_ms?: number | null;
  /**
   * 근거(observed·inferred 등).
   */
  evidence?: string;
  /**
   * 범주 + 분류기 태그.
   */
  tags?: string[];
  documents?: LogDocumentRef[];
  /**
   * 상관 근거 이름 → 값(명시 id만, 시간상 이웃은 잇지 않음).
   */
  correlation?: {
    [k: string]: string | string[];
  };
  /**
   * 표시용 본문(상세에서만, 크기 제한 적용).
   */
  detail?: unknown;
  /**
   * 원문(상세에서만, 크기 제한·비밀 가림 적용).
   */
  raw?: unknown;
}
/**
 * 이벤트가 가리키는 문서(SKILL.md·SPEC.md 등). 이름만 언급된 것은 읽음으로 보지 않는다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogDocumentRef".
 */
export interface LogDocumentRef {
  /**
   * 문서 경로(출처가 준 그대로, 원본 기준 상대 경로 권장).
   */
  path: string;
  /**
   * 문서 종류(예: skill, spec, document).
   */
  kind?: string;
  /**
   * 이벤트와의 관계(예: mentioned, read, written).
   */
  action?: string;
}
/**
 * 같은 명시 id를 공유하는 다른 이벤트(agent_bench `link_events`).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogEvidenceLink".
 */
export interface LogEvidenceLink {
  uid: string;
  title?: string;
  /**
   * 상관 근거 이름(예: call_id, session).
   */
  basis: string;
  value: string;
}
/**
 * 로그 분류기 디스크립터(X6). 분류기는 행 단위 무상태다(F-7).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogClassifierDescriptor".
 */
export interface LogClassifierDescriptor {
  id: string;
  /**
   * 다룰 수 있는 출처 형식.
   */
  formats?: string[];
  title: string;
  description?: string | null;
  config_schema?: {
    [k: string]: unknown;
  };
}
/**
 * 위젯을 모은 로그 대시보드.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogDashboard".
 */
export interface LogDashboard {
  /**
   * 대시보드를 가리키는 고유 이름입니다.
   */
  id: string;
  /**
   * 대시보드 목록에 보일 이름입니다.
   */
  title: string;
  /**
   * 대시보드에 놓인 위젯입니다.
   */
  widgets?: LogWidget[];
  [k: string]: unknown;
}
/**
 * 대시보드 위젯 하나.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogWidget".
 */
export interface LogWidget {
  /**
   * 대시보드 안에서 위젯을 가리키는 고유 이름입니다.
   */
  id: string;
  /**
   * 위젯 모양입니다(예: 표, 막대). 모르는 종류는 표로 보입니다.
   */
  kind: string;
  /**
   * 위젯 위에 보일 제목입니다.
   */
  title?: string | null;
  query: LogWidgetQuery;
  /**
   * w·h는 격자 칸 수입니다(비우면 기본 크기). 나머지는 위젯 종류가 읽습니다.
   */
  options?: {
    [k: string]: unknown;
  };
  [k: string]: unknown;
}
/**
 * 위젯이 보일 집계: 나눌 차원, 지표, 필터.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogWidgetQuery".
 */
export interface LogWidgetQuery {
  /**
   * 집계를 나눌 기준입니다(예: 도구, 모델).
   */
  group_by?: string[];
  /**
   * 셀 값입니다(예: events = 이벤트 수, tokens.total = 토큰 합계).
   */
  metric: string;
  /**
   * 거를 조건입니다(필터 이름 → 값). 기간은 절대 시각으로 저장됩니다.
   */
  filter?: {
    [k: string]: unknown;
  };
  [k: string]: unknown;
}
/**
 * 집계 차원 하나(`GET /logs/schema`). 화면은 이름을 몰라도 이 목록으로 고른다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogDimensionInfo".
 */
export interface LogDimensionInfo {
  id: string;
  title?: string | null;
  description?: string | null;
  /**
   * 차원 성격(예: time = 시간 차원). 모르는 값은 무시한다.
   */
  kind?: string | null;
}
/**
 * `GET /logs/events/{uid}` 응답: 본문 포함 이벤트 + 관련 이벤트 + 근거 연결.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogEventDetail".
 */
export interface LogEventDetail {
  event: LogEvent;
  /**
   * 같은 호출·응답의 다른 이벤트(본문 없음).
   */
  related?: LogEvent[];
  evidence_links?: LogEvidenceLink[];
  /**
   * 근거 후보가 한도(1000)를 넘어 잘림(본문 잘림과 별개).
   */
  truncated?: boolean;
  /**
   * detail·raw가 본문 크기 한도(max_detail_bytes)로 잘림.
   */
  detail_truncated?: boolean;
  /**
   * 이 이벤트의 토큰 표본(있으면).
   */
  usage?: TokenSample | null;
}
/**
 * 응답(thread, message_id) 하나의 토큰 표본(F-8: 같은 응답이 여러 행이어도 한 번만 센다).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "TokenSample".
 */
export interface TokenSample {
  thread?: string;
  message_id?: string;
  model?: string;
  time?: number | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cache_read_input_tokens?: number | null;
  cache_creation_input_tokens?: number | null;
}
/**
 * `GET /logs/events` 응답(키셋 페이지).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogEventPage".
 */
export interface LogEventPage {
  items?: LogEvent[];
  /**
   * 전체 개수(계산하지 않으면 null).
   */
  total?: number | null;
  /**
   * 다음 페이지 커서. null = 끝.
   */
  next_cursor?: string | null;
}
/**
 * 필터 이름 하나(`GET /logs/schema`). 모르는 필터 이름은 서버가 422로 답한다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogFilterFieldInfo".
 */
export interface LogFilterFieldInfo {
  id: string;
  title?: string | null;
  description?: string | null;
  /**
   * 여러 값을 받는다(쉼표 목록).
   */
  multi?: boolean | null;
}
/**
 * 집계 지표 하나(`GET /logs/schema`).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogMetricInfo".
 */
export interface LogMetricInfo {
  id: string;
  title?: string | null;
  description?: string | null;
  /**
   * 값 단위(예: count, tokens, ms).
   */
  unit?: string | null;
}
/**
 * 경로 패턴(예: ~/work/app/**)에 맞는 로그를 한 프로젝트로 묶습니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogProjectGroup".
 */
export interface LogProjectGroup {
  /**
   * 묶음을 가리키는 고유 이름입니다.
   */
  id: string;
  /**
   * 화면에 보일 묶음 이름입니다. 비우면 id를 씁니다.
   */
  label?: string | null;
  /**
   * 저장소 경로(없으면 작업 폴더)와 맞춰 봅니다. 하위 폴더까지는 /proj/** 처럼 씁니다.
   */
  match?: string[];
  [k: string]: unknown;
}
/**
 * 로그를 프로젝트별로 묶는 규칙. 바꾸면 바로 반영된다(다시 수집할 필요 없음).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogProjectSettings".
 */
export interface LogProjectSettings {
  /**
   * 경로로 로그를 묶는 규칙입니다. 위에서부터 보고 처음 맞는 묶음이 이깁니다.
   */
  groups?: LogProjectGroup[] | null;
  /**
   * 맞는 묶음이 없으면 자기 경로(cwd), 저장소(repo_root), 기타 한 묶음(none)으로 둡니다.
   */
  ungrouped?: LogUngroupedPolicy | null;
  /**
   * git worktree 폴더를 원래 저장소와 한 묶음으로 봅니다. 기본은 켬입니다.
   */
  git_worktrees?: boolean | null;
  [k: string]: unknown;
}
/**
 * `GET /logs/schema`: 위젯 질의·필터 막대가 고를 차원·지표·필터 목록(서버 데이터).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogQuerySchema".
 */
export interface LogQuerySchema {
  dimensions?: LogDimensionInfo[];
  metrics?: LogMetricInfo[];
  filters?: LogFilterFieldInfo[];
}
/**
 * `POST /logs/scan` 응답(수집 한 번의 결과).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogScanReport".
 */
export interface LogScanReport {
  started_at: number;
  finished_at: number;
  sources?: LogSourceScanResult[];
  /**
   * 새로 색인한 이벤트 합.
   */
  new_events?: number;
  /**
   * 지금 색인의 최대 seq.
   */
  max_seq?: number | null;
}
/**
 * 수집 한 번에서 출처 하나의 결과.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogSourceScanResult".
 */
export interface LogSourceScanResult {
  source_id: string;
  /**
   * 새로 색인한 이벤트 수.
   */
  new_events?: number;
  /**
   * 이 출처의 실패 코드(없으면 성공).
   */
  error_code?: string | null;
  /**
   * 실패 설명(비밀을 가린 문장).
   */
  message?: string | null;
  /**
   * 읽은 단위 수.
   */
  refs?: number;
  read_bytes?: number;
  /**
   * 읽은 원본 행 수.
   */
  records?: number;
  /**
   * 해석·분류 실패로 진단 이벤트가 된 행.
   */
  diagnostics?: number;
  pending_bytes?: number | null;
}
/**
 * 읽을 로그 출처, 범주 표시, 프로젝트 묶기, 대시보드. 비운 항목은 기본값을 따른다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogSettings".
 */
export interface LogSettings {
  /**
   * 출처마다 켜고 끄며 설정합니다. 목록에 없는 출처는 출처 기본값을 따릅니다.
   */
  sources?: LogSourceSetting[] | null;
  /**
   * 범주별 표시 이름·색·보이기를 기본값 위에 덮어씁니다.
   */
  taxonomy?: LogTaxonomy | null;
  /**
   * 로그를 경로에 따라 프로젝트별로 묶는 규칙입니다.
   */
  projects?: LogProjectSettings | null;
  /**
   * 위젯을 모은 로그 대시보드입니다.
   */
  dashboards?: LogDashboard[] | null;
  [k: string]: unknown;
}
/**
 * 로그 출처 하나의 사용 여부와 설정. 비운 항목은 출처 기본값을 따른다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogSourceSetting".
 */
export interface LogSourceSetting {
  /**
   * 로그를 읽어 올 곳입니다(예: Claude Code 세션 로그).
   */
  id: string;
  /**
   * 이 출처를 읽을지 정합니다. 비우면 출처의 기본값을 따릅니다.
   */
  enabled?: boolean | null;
  /**
   * 출처마다 정한 설정입니다(예: 읽을 폴더, 분류 방식).
   */
  config?: {
    [k: string]: unknown;
  } | null;
  [k: string]: unknown;
}
/**
 * 로그 출처 디스크립터.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogSourceDescriptor".
 */
export interface LogSourceDescriptor {
  id: string;
  title: string;
  /**
   * 기본 분류기 id.
   */
  format: string;
  description?: string | null;
  config_schema?: {
    [k: string]: unknown;
  };
  /**
   * 설정에 없을 때 켤지(개인 대화 원문을 복사하는 출처는 끔).
   */
  default_enabled?: boolean;
  /**
   * 원본 파일을 읽는다(화면이 '원본은 읽기만 함'을 보인다).
   */
  reads_paths?: boolean;
  /**
   * 설정 방법 안내(마크다운).
   */
  setup_help?: string | null;
  /**
   * 자세한 문서 링크(http(s) URL).
   */
  docs_url?: string | null;
}
/**
 * `GET /logs/sources` 항목.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogSourceInfo".
 */
export interface LogSourceInfo {
  descriptor: LogSourceDescriptor;
  enabled: boolean;
  /**
   * plugin = entry point 출처, runtime = 다른 모듈이 준 출처(열린 문자열).
   */
  origin?: string;
  status?: LogSourceStatus;
}
/**
 * 출처 하나의 수집 상태.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogSourceStatus".
 */
export interface LogSourceStatus {
  last_scan_at?: number | null;
  /**
   * 알고 있는 단위(파일·Run) 수.
   */
  refs?: number;
  /**
   * 예산 때문에 다음 수집으로 미룬 바이트(모르면 null).
   */
  pending_bytes?: number | null;
  /**
   * 마지막 수집 실패 코드.
   */
  error_code?: string | null;
}
/**
 * `GET /logs/sessions/{session}/timeline`: 세션의 보이는 이벤트(time → seq 순), 줄 = thread.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogTimeline".
 */
export interface LogTimeline {
  session: LogSessionSummary;
  /**
   * 줄(thread). parent_id로 서브에이전트 관계를 그린다.
   */
  lanes?: LogLane[];
  events?: LogEvent[];
  /**
   * 세션의 보이는 이벤트 전체 수(잘렸을 때 비교용).
   */
  total?: number | null;
  /**
   * 서버 상한으로 앞부분만 실었다.
   */
  truncated?: boolean;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogsIngestedMessage".
 */
export interface LogsIngestedMessage {
  /**
   * 요청 상관 id(선택).
   */
  id?: string | null;
  type: "logs.ingested";
  payload: LogsIngestedPayload;
}
/**
 * 토픽 `logs`: 로그 수집으로 새 이벤트가 색인됨.
 *
 * 목록 화면은 `max_seq`보다 큰 이벤트를 다시 불러온다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "LogsIngestedPayload".
 */
export interface LogsIngestedPayload {
  /**
   * 새 이벤트가 생긴 출처 id.
   */
  source_ids?: string[];
  /**
   * 새로 색인한 이벤트 수.
   */
  count: number;
  /**
   * 지금 색인의 최대 seq.
   */
  max_seq?: number | null;
}
/**
 * `GET /merge-strategies` 항목: 설정 `settings_merge`에 쓸 수 있는 병합 전략 이름 하나.
 *
 * 목록은 서버의 전략 표(기본 + 플러그인)에서 온다. 계약에 고정 목록은 없다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "MergeStrategyInfo".
 */
export interface MergeStrategyInfo {
  /**
   * 전략 이름(`settings_merge` 값, 스키마 `x-merge` 값).
   */
  id: string;
  /**
   * 짧은 설명(표시용).
   */
  description?: string;
}
/**
 * 백엔드가 제공하는 모델 하나(`list_models()`). 모델 목록은 코드에 없다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ModelInfo".
 */
export interface ModelInfo {
  id: string;
  title?: string | null;
  description?: string | null;
  context_window?: number | null;
  attributes?: {
    [k: string]: unknown;
  };
}
/**
 * `GET /modules` 항목: 설치된 모듈(기능·연동) 하나와 그 상태.
 *
 * 웹은 이 목록과 라우트 `requires`(데이터)로 화면을 조립한다.
 * 목록·종류·역할 이름은 고정하지 않는다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ModuleInfo".
 */
export interface ModuleInfo {
  /**
   * 모듈 id(entry point 이름).
   */
  id: string;
  /**
   * 모듈 종류(열린 문자열, 예: feature, link). 화면은 모르는 값을 그대로 보인다.
   */
  kind: string;
  /**
   * 모듈 패키지 버전.
   */
  version: string;
  /**
   * 이 모듈이 쓰는 계약 하위 모듈 → 버전(`CONTRACT_VERSIONS` 값).
   */
  contracts?: {
    [k: string]: string;
  };
  status: ModuleStatus;
  /**
   * active가 아닌 이유(빠진 포트, 충돌 등). 비밀·예외 원문은 담지 않는다.
   */
  reason?: string | null;
  /**
   * 웹 라우트 `requires`가 가리키는 역할 이름(예: conversations, usage).
   */
  web_roles?: string[];
  /**
   * 제공하는 포트 이름.
   */
  provides?: string[];
  /**
   * 필요한 포트 이름(필수·선택 모두, 상태 판단 근거).
   */
  requires?: string[];
}
/**
 * `GET /modules/{id}/options` 응답: 모듈 옵션의 읽기 전용 보기(0.8.0).
 *
 * 모듈 옵션은 설치자 설정 파일(`modules.options.<id>`)에서만 바꾼다. 쓰기 API는 없다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ModuleOptionsView".
 */
export interface ModuleOptionsView {
  module_id: string;
  /**
   * 옵션 JSON Schema(모듈이 선언). null = 모듈이 스키마를 내지 않음.
   */
  schema?: {
    [k: string]: unknown;
  } | null;
  /**
   * 지금 값. 비밀로 보이는 값은 가려져 있다.
   */
  values?: {
    [k: string]: unknown;
  };
  /**
   * 설정 파일에 붙일 YAML 조각(가린 값 그대로, 들여쓰기 포함).
   */
  yaml_snippet?: string;
}
/**
 * 옮기기 계획(순수 함수 `move_plan`의 결과). 저장하지 않는다.
 *
 * P 전용 → 공용: `moves`에 그 정의가 쓰는 P 전용 정의(참조 닫힘)가 함께 들어간다(기본 선택).
 * 공용 → P 전용: 그 정의를 쓰는 다른 프로젝트·공용 정의는 `warnings`로 알린다(막지 않음).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "MovePlan".
 */
export interface MovePlan {
  target: DefinitionKey;
  /**
   * 옮길 범위(null = 공용).
   */
  to?: string | null;
  moves?: DefinitionMove[];
  /**
   * 옮긴 뒤 생길 범위 경고(project.shared_uses_project 등)나 검사 못 함 정보.
   */
  warnings?: Issue[];
}
/**
 * `POST /projects/move-plan` 요청: 정의 하나를 `to` 범위로 옮길 때의 계획을 계산한다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "MovePlanRequest".
 */
export interface MovePlanRequest {
  kind: string;
  id: string;
  /**
   * 옮길 프로젝트 id. null = 공용으로.
   */
  to?: string | null;
}
/**
 * 노드 1회 실행. 재실행·반복은 attempt/iteration 증가.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "NodeRun".
 */
export interface NodeRun {
  run_id: string;
  node_id: string;
  attempt?: number;
  /**
   * 반복 회차(사이클 연결로 다시 열릴 때마다 1씩).
   */
  iteration?: number;
  /**
   * 호출 회차: 위임자가 이 노드를 실행 안에서 부른 순번(0부터). 스케줄로 실행된 NodeRun은 0.
   */
  call?: number;
  /**
   * 위임자가 불러 실행됐으면 위임자의 노드 경로. null = 스케줄로 실행됨.
   */
  invoked_by?: string[] | null;
  status: NodeRunStatus;
  node_type?: string | null;
  inputs?: {
    [k: string]: unknown;
  };
  outputs?: {
    [k: string]: unknown;
  };
  error?: ErrorInfo | null;
  usage?: Usage | null;
  started_at?: number | null;
  ended_at?: number | null;
  duration_ms?: number | null;
  backend_session_id?: string | null;
}
/**
 * 노드 타입 디스크립터(X1). 편집기 팔레트·노드 모양·설정 폼은 이것만으로 그린다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "NodeTypeDescriptor".
 */
export interface NodeTypeDescriptor {
  id: string;
  version?: number;
  title: string;
  description?: string;
  /**
   * 팔레트 묶음 이름(문자열, 고정 목록 아님).
   */
  category?: string;
  /**
   * 노드 역할 문자열(연결 규칙 `connects`의 근거, 고정 목록 아님).
   */
  role?: string | null;
  /**
   * false면 엔진이 스케줄하지 않는다(리소스 등).
   */
  executable?: boolean;
  /**
   * 이 노드 타입이 정의 하나에서 만들어지면 그 종류와 config 키.
   */
  binds?: DefinitionBinding | null;
  /**
   * config의 JSON Schema(폼 자동 생성).
   */
  config_schema?: {
    [k: string]: unknown;
  };
  /**
   * rjsf uiSchema 힌트(선택).
   */
  ui_schema?: {
    [k: string]: unknown;
  };
  /**
   * 고정 포트. dynamic_ports가 true면 서버에 계산을 요청한다.
   */
  static_ports?: PortSpec | null;
  dynamic_ports?: boolean;
  join?: JoinRule;
  /**
   * 능력 문자열(해석은 엔진·화면 몫, 고정 목록 아님).
   */
  capabilities?: string[];
  /**
   * 끊긴 실행을 이어 갈 때 저장된 입력으로 이 노드부터 다시 실행할 수 있는지.
   */
  rerunnable?: boolean;
  ui_hints?: UiHints | null;
}
/**
 * 노드의 입력·출력 포트 목록.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "PortSpec".
 */
export interface PortSpec {
  inputs?: PortDef[];
  outputs?: PortDef[];
}
/**
 * 브라우저 알림과 소리입니다. 비운 항목은 기본값을 씁니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "NotificationSettings".
 */
export interface NotificationSettings {
  /**
   * 고른 일이 생기면 브라우저 알림을 띄웁니다.
   */
  enabled?: boolean;
  /**
   * 알림과 함께 짧은 소리를 냅니다.
   */
  sound?: boolean;
  /**
   * 알림을 띄울 일입니다(예: interaction.requested = 답을 기다림, run.failed = 실패).
   */
  events?: string[];
  /**
   * 탭을 보고 있는 동안에는 화면에만 표시하고 알림을 띄우지 않습니다.
   */
  only_when_hidden?: boolean;
  [k: string]: unknown;
}
/**
 * 서버가 읽은 플러그인 하나(설정 화면 서버 정보, 읽기 전용).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "PluginInfo".
 */
export interface PluginInfo {
  name: string;
  /**
   * 확장 지점(entry point 그룹) 이름.
   */
  group?: string | null;
  loaded?: boolean;
  /**
   * 로딩 상태(열린 문자열). 알려진 값: loaded, failed(error 있음), skipped(설정 `plugins.enabled`에 없어 읽지 않음), disabled(읽었지만 `plugins.enabled`에 없는 항목이라 등록 해제). 화면은 모르는 값을 그대로 보인다.
   */
  status?: string;
  error?: ErrorInfo | null;
}
/**
 * `POST /conversations/{id}/messages` 요청. 응답은 `Run`(202) 또는 `QueuedMessage`(202).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "PostMessageRequest".
 */
export interface PostMessageRequest {
  text: string;
}
/**
 * `GET /presets` 목록 항목. 프리셋은 데이터이며 지워도 시스템이 동작한다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "PresetSummary".
 */
export interface PresetSummary {
  id: string;
  name: string;
  description?: string;
  labels?: string[];
  item_count?: number;
  /**
   * 항목 요약(종류·id 등). 형식은 프리셋 패키지가 정한다.
   */
  items?: {
    [k: string]: unknown;
  }[];
  /**
   * 카드에 보일 짧은 배지 글자(예: 체험, 추천).
   */
  badges?: string[];
  /**
   * '바로 시작' 순서(작을수록 앞). null = 바로 시작에 없음, 목록 순서대로.
   */
  featured?: number | null;
  /**
   * 적용한 뒤 바로 열 팀 구성 id(프리셋 안 id). null = 열지 않음.
   */
  start_graph?: string | null;
}
/**
 * 프로젝트입니다. 작업 폴더와 연결한 로그, 그 프로젝트에서 쓸 설정을 묶습니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "Project".
 */
export interface Project {
  /**
   * 프로젝트를 부르는 이름입니다. 위쪽 프로젝트 고르기에 보입니다.
   */
  name: string;
  /**
   * 이 프로젝트가 무엇인지 적습니다.
   */
  description?: string;
  /**
   * 이 프로젝트에서 실행하는 에이전트의 작업 폴더. 비우면 서버 설정의 작업 폴더.
   */
  working_directory?: string | null;
  /**
   * 이 프로젝트로 볼 로그 묶음입니다. 비우면 로그를 거르지 않습니다.
   */
  log_projects?: string[];
  /**
   * 이 프로젝트의 에이전트 설정입니다. 비운 항목은 공통 설정을 따릅니다.
   */
  settings?: AgentSettings | null;
  /**
   * 찾기·거르기에 쓰는 꼬리표입니다.
   */
  labels?: string[];
  /**
   * 다른 도구가 읽는 자유 속성입니다. 보통은 비워 둡니다.
   */
  attributes?: {
    [k: string]: unknown;
  };
  kind?: "project";
  /**
   * 가리킬 때 쓰는 고유 이름입니다. 파일 이름으로도 씁니다.
   */
  id: string;
  /**
   * 파일 형식 번호입니다. 직접 바꾸지 않습니다.
   */
  schema_version?: number;
  [k: string]: unknown;
}
/**
 * 새 프로젝트를 만들 때 적는 값입니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ProjectCreate".
 */
export interface ProjectCreate {
  /**
   * 프로젝트를 부르는 이름입니다. 위쪽 프로젝트 고르기에 보입니다.
   */
  name: string;
  /**
   * 이 프로젝트가 무엇인지 적습니다.
   */
  description?: string;
  /**
   * 이 프로젝트에서 실행하는 에이전트의 작업 폴더. 비우면 서버 설정의 작업 폴더.
   */
  working_directory?: string | null;
  /**
   * 이 프로젝트로 볼 로그 묶음입니다. 비우면 로그를 거르지 않습니다.
   */
  log_projects?: string[];
  /**
   * 이 프로젝트의 에이전트 설정입니다. 비운 항목은 공통 설정을 따릅니다.
   */
  settings?: AgentSettings | null;
  /**
   * 찾기·거르기에 쓰는 꼬리표입니다.
   */
  labels?: string[];
  /**
   * 다른 도구가 읽는 자유 속성입니다. 보통은 비워 둡니다.
   */
  attributes?: {
    [k: string]: unknown;
  };
  /**
   * 새 프로젝트의 고유 이름입니다. 영문·숫자·-·_만 쓰며 이미 있는 이름은 못 씁니다.
   */
  id: string;
  [k: string]: unknown;
}
/**
 * 프로젝트 관련 설정입니다. 새로 만드는 에이전트·팀 등을 어느 범위에 둘지 정합니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ProjectPreferences".
 */
export interface ProjectPreferences {
  /**
   * 종류마다 새로 만든 정의를 프로젝트 전용(project)으로 둘지 공용(shared)으로 둘지입니다.
   */
  new_definition_scope?: {
    [k: string]: DefinitionScope;
  };
  fallback?: DefinitionScope;
  [k: string]: unknown;
}
/**
 * `PUT /projects/{id}` 요청. 생략한 필드는 그대로 둔다.
 *
 * `working_directory`·`settings`의 null은 값을 지운다(상속으로 되돌림).
 * `name`의 null은 생략과 같다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ProjectUpdate".
 */
export interface ProjectUpdate {
  name?: string | null;
  description?: string | null;
  working_directory?: string | null;
  log_projects?: string[] | null;
  settings?: AgentSettings | null;
  labels?: string[] | null;
  attributes?: {
    [k: string]: unknown;
  } | null;
}
/**
 * 실행 중이라 대기열에 넣은 메시지(`chat.busy_policy = queue`).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "QueuedMessage".
 */
export interface QueuedMessage {
  queued?: true;
  /**
   * 대기열 항목 id. 취소: DELETE /conversations/{id}/queue/{queued_id}.
   */
  id?: string | null;
  /**
   * 대기열 순번(1 = 다음 차례).
   */
  position: number;
  /**
   * 대기 중인 메시지 본문(목록 표시용).
   */
  text?: string | null;
  /**
   * 재시작으로 멈춘 항목(`chat.queue_after_restart = ask`). 실행·취소를 고른다.
   */
  held?: boolean;
}
/**
 * `POST /node-types/{id}/ports` 요청. 응답은 PortSpec.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ResolvePortsRequest".
 */
export interface ResolvePortsRequest {
  config?: {
    [k: string]: unknown;
  };
}
/**
 * 리소스입니다. 에이전트에 붙여 쓰는 지침·파일·MCP(외부 도구 서버) 등을 담습니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "Resource".
 */
export interface Resource {
  kind?: "resource";
  /**
   * 가리킬 때 쓰는 고유 이름입니다. 파일 이름으로도 쓰며 영문·숫자·-·_만 씁니다.
   */
  id: string;
  /**
   * 파일 형식 번호입니다. 직접 바꾸지 않습니다.
   */
  schema_version?: number;
  /**
   * 지침·파일·MCP 서버(외부 도구 서버)처럼 리소스의 종류입니다. 종류마다 입력 항목이 다릅니다.
   */
  type: string;
  /**
   * 리소스를 부르는 이름입니다. 에이전트에 붙일 때 이 이름으로 고릅니다.
   */
  name: string;
  /**
   * 이 리소스가 무엇인지 적습니다. 목록에 함께 보입니다.
   */
  description?: string;
  /**
   * 찾기·거르기에 쓰는 꼬리표입니다.
   */
  labels?: string[];
  /**
   * 종류가 정한 설정입니다(예: 외부 도구 서버를 띄울 명령).
   */
  config?: {
    [k: string]: unknown;
  };
  /**
   * 지침·규칙 같은 문서형 종류의 본문입니다. 본문은 따로 저장됩니다.
   */
  content?: ResourceContentRef | null;
  /**
   * 다른 도구가 읽는 자유 속성입니다. 보통은 비워 둡니다.
   */
  attributes?: {
    [k: string]: unknown;
  };
  /**
   * 이 정의가 속한 프로젝트입니다. 비우면 공용이라 모든 프로젝트에서 보입니다.
   */
  project?: string | null;
  [k: string]: unknown;
}
/**
 * 문서형 리소스의 본문 파일(정의 파일 옆 폴더 기준 상대 경로).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ResourceContentRef".
 */
export interface ResourceContentRef {
  /**
   * 리소스 폴더 안의 본문 파일 경로입니다.
   */
  file: string;
  /**
   * 본문의 파일 형식(MIME)입니다.
   */
  media_type?: string | null;
  [k: string]: unknown;
}
/**
 * 문서형 리소스 종류의 본문 형식.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ResourceContentSpec".
 */
export interface ResourceContentSpec {
  /**
   * 허용 MIME 형식.
   */
  media_types?: string[];
  /**
   * 편집기 이름(예: text, markdown, html, json). 모르면 text.
   */
  editor?: string;
  /**
   * 본문이 여러 파일(리소스 폴더 아래 상대 경로들)인지.
   */
  multi_file?: boolean;
}
/**
 * 여러 파일 본문(`ResourceContentSpec.multi_file`) 리소스의 파일 하나.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ResourceFile".
 */
export interface ResourceFile {
  /**
   * 리소스 본문 폴더 기준 상대 경로(`/` 구분).
   */
  path: string;
  media_type?: string | null;
  /**
   * 바이트 수.
   */
  size: number;
  /**
   * 내용 해시(16진 소문자).
   */
  sha256: string;
}
/**
 * `GET /resources` 목록 항목.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ResourceSummary".
 */
export interface ResourceSummary {
  id: string;
  type: string;
  name: string;
  description?: string;
  labels?: string[];
  version_hash: string;
  saved_at?: number | null;
  has_content?: boolean;
  /**
   * 붙어 있는 곳의 수(계산하지 않았으면 null).
   */
  usage_count?: number | null;
  /**
   * 정의의 프로젝트 id(0.8.0). null = 공용. 웹이 이 값으로 목록을 거른다.
   */
  project?: string | null;
}
/**
 * 리소스 종류 디스크립터. 플러그인 또는 선언형 데이터로 들어온다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ResourceTypeDescriptor".
 */
export interface ResourceTypeDescriptor {
  id: string;
  version?: number;
  title: string;
  description?: string;
  config_schema?: {
    [k: string]: unknown;
  };
  ui_schema?: {
    [k: string]: unknown;
  };
  /**
   * 문서형이면 본문 형식.
   */
  content?: ResourceContentSpec | null;
  /**
   * 첨부 방식 replace가 같은 자리를 판단하는 config 키.
   */
  slot_key?: string | null;
  /**
   * 같은 칸 여러 첨부의 합치기 전략 이름(병합 전략 표).
   */
  combine?: string;
  /**
   * 채우는 실행 묶음 칸 이름.
   */
  contributes?: string[];
  /**
   * 코드 없이 선언형 데이터로 등록된 종류인지.
   */
  declarative?: boolean;
  ui_hints?: UiHints | null;
}
/**
 * `POST /runs/{run_id}/interactions/{interaction_id}/respond` 요청. 응답은 `Interaction`.
 *
 * `response`는 그 상호작용의 `response_schema`로 검증된다(아니면 422 `validation_failed`).
 * 이미 닫혔으면 409 `interaction_closed`.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "RespondInteractionRequest".
 */
export interface RespondInteractionRequest {
  response: {
    [k: string]: unknown;
  };
}
/**
 * `POST /{kind}/{id}/versions/{hash}/restore` 요청. 복원은 새 버전으로 저장된다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "RestoreVersionRequest".
 */
export interface RestoreVersionRequest {
  /**
   * 버전 메시지. 비우면 서버 기본 문구.
   */
  message?: string | null;
}
/**
 * 이어 갈 수 있는 끊긴 노드 하나.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ResumeNodeOption".
 */
export interface ResumeNodeOption {
  node_id: string;
  label?: string | null;
  /**
   * 노드 타입 디스크립터의 `rerunnable`.
   */
  rerunnable: boolean;
  status: NodeRunStatus;
}
/**
 * `GET /runs/{id}/resume-options` 응답.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ResumeOptions".
 */
export interface ResumeOptions {
  run_id: string;
  nodes?: ResumeNodeOption[];
}
/**
 * `POST /runs/{id}/resume` 요청. 응답은 새 `Run`(origin = resume, `resumed_from`).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ResumeRunRequest".
 */
export interface ResumeRunRequest {
  /**
   * 다시 실행할 노드 id.
   *
   * @minItems 1
   */
  node_ids: [string, ...string[]];
}
/**
 * 검토하는 사람이 고를 결정 하나입니다(예: 승인, 반려). 결정마다 다음 갈 곳을 정합니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ReviewDecision".
 */
export interface ReviewDecision {
  /**
   * 결정을 가리키는 이름입니다. 같은 이름의 출력 포트가 생깁니다.
   */
  id: string;
  /**
   * 검토 카드 버튼에 보일 이름입니다. 비우면 결정 id를 씁니다.
   */
  label?: string;
  /**
   * 켜면 이 결정을 고를 때 내용을 고쳐 보낼 수 있습니다.
   */
  edit?: boolean;
  /**
   * 켜면 이 결정을 고를 때 의견을 적을 칸을 보입니다.
   */
  feedback?: boolean;
  /**
   * 버튼 색 등 표시용 힌트입니다. 화면이 모르는 값은 무시합니다.
   */
  ui_hints?: UiHints | null;
}
/**
 * 그래프 1회 실행. 하위 그래프는 자식 Run(parent_run_id).
 *
 * 목록 `GET /runs` 질의(0.8.0): `project`(같은 `project_id`만), `root_only`(true면 루트 Run만,
 * `root_run_id`가 null인 것). 기존 질의(`graph_id`·`conversation_id`·`root` 등)는 그대로다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "Run".
 */
export interface Run {
  id: string;
  /**
   * 실행한 그래프(팀 구성) id.
   */
  graph_id: string;
  /**
   * 실행 당시 그래프 version_hash.
   */
  graph_version: string;
  status: RunStatus;
  /**
   * 그래프 입력 포트 이름 → 값.
   */
  input: {
    [k: string]: unknown;
  };
  /**
   * 시작 경로. 알려진 값은 RUN_ORIGINS(확장 가능).
   */
  origin: string;
  /**
   * 채팅 대화의 한 턴이면 그 대화 id.
   */
  conversation_id?: string | null;
  /**
   * 자식 Run(중첩 팀)이면 부모 Run id.
   */
  parent_run_id?: string | null;
  /**
   * 자식 Run이면 그 Run을 만든 부모 그래프의 노드 id.
   */
  parent_node_id?: string | null;
  /**
   * 자식 Run이면 맨 위 Run id(0.7.0). null = 이 Run이 루트다. 응답 대기·사용량은 루트 기준으로 모은다.
   */
  root_run_id?: string | null;
  /**
   * 프로젝트 id(0.8.0, 불투명 문자열). null = 프로젝트 없음. `GET /runs?project=`로 같음 비교해 거른다. 자식 Run은 루트 값을 물려받는다.
   */
  project_id?: string | null;
  rerun_of?: string | null;
  from_node?: string | null;
  /**
   * 끊긴 실행을 이어 간 Run이면 원래 Run id(origin = resume).
   */
  resumed_from?: string | null;
  /**
   * Unix epoch 초.
   */
  created_at: number;
  started_at?: number | null;
  ended_at?: number | null;
  error?: ErrorInfo | null;
  totals?: Usage | null;
}
/**
 * 일반 RunEvent. 모든 이벤트가 이 형태로 직렬화·저장된다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "RunEvent".
 */
export interface RunEvent {
  schema_version?: number;
  event_id: string;
  run_id: string;
  seq: number;
  /**
   * Unix epoch 초.
   */
  ts: number;
  /**
   * 이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드].
   */
  node_path: string[];
  /**
   * 노드 이벤트의 시도 번호.
   */
  attempt?: number | null;
  /**
   * 이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.
   */
  actor?: string | null;
  /**
   * observed | inferred 등(확장 가능).
   */
  evidence?: string;
  /**
   * 공급자 원시 메시지(크기 제한·비밀 제거 후).
   */
  raw?: unknown;
  type: string;
  payload?: {
    [k: string]: unknown;
  };
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "RunEventMessage".
 */
export interface RunEventMessage {
  /**
   * 요청 상관 id(선택).
   */
  id?: string | null;
  type: "run.event";
  payload: RunEvent;
}
/**
 * `GET /runs/{id}` 응답. 이후 WS `subscribe run:<id> since_seq=last_seq`로 증분을 받는다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "RunSnapshot".
 */
export interface RunSnapshot {
  run: Run;
  node_runs: NodeRun[];
  last_seq: number;
  /**
   * 이 Run이 만든 자식 Run(중첩 팀). null = 서버가 채우지 않음, [] = 자식 없음.
   */
  children?: Run[] | null;
}
/**
 * 비밀 값으로 의심할 규칙을 더합니다. 기본 규칙에 더하기만 하며 줄일 수는 없습니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "SecretRuleSettings".
 */
export interface SecretRuleSettings {
  /**
   * 이 이름(또는 이 단어가 든 이름)의 값을 비밀로 의심합니다.
   */
  extra_key_names?: string[];
  /**
   * 값이 이 정규식과 맞으면 비밀로 의심합니다. 위험한 패턴은 저장할 때 거부됩니다.
   */
  extra_value_patterns?: string[];
  /**
   * 실행 기록·질문 응답을 저장하기 전에 비밀로 의심되는 값을 가립니다.
   */
  redact_suspected_in_logs?: boolean;
  [k: string]: unknown;
}
/**
 * `GET /server-info` 응답(읽기 전용). 설치자 설정 값 중 비밀이 아닌 것만.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "ServerInfo".
 */
export interface ServerInfo {
  server_version: string;
  contracts_version: string;
  plugins?: PluginInfo[];
  attributes?: {
    [k: string]: unknown;
  };
  /**
   * 워크스페이스 점검 경고(예: 평문 비밀 의심). 값은 담지 않는다.
   */
  warnings?: Issue[];
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "SubscribeMessage".
 */
export interface SubscribeMessage {
  /**
   * 요청 상관 id(선택).
   */
  id?: string | null;
  type: "subscribe";
  payload: SubscribePayload;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "SubscribePayload".
 */
export interface SubscribePayload {
  /**
   * 토픽 이름. 켜진 서버 모듈이 정한다(`ModuleParts.ws_topics`). 기본 모듈: "run:<id>" | "conversation:<id>" | "interactions" | "logs". 모르는 토픽은 `error`.
   */
  topic: string;
  /**
   * 이 seq 다음부터 저장소에서 재생한 뒤 실시간으로 전환.
   */
  since_seq?: number | null;
}
/**
 * 팀 구성 실행 계획 요약(`GET /graphs/{id}/plan`, 초안 `POST /graphs/plan`).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "TeamPlanSummary".
 */
export interface TeamPlanSummary {
  entries?: EntrySlot[];
  answers?: AnswerSlot[];
  /**
   * 노드 id → 그 노드가 열 수 있는 상호작용.
   */
  grants?: {
    [k: string]: InteractionGrant;
  };
}
/**
 * 플랫폼 실행분 토큰 집계 한 줄. 비어 있는 차원은 그 차원으로 나누지 않은 것이다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "TokenRollupRow".
 */
export interface TokenRollupRow {
  agent_id?: string | null;
  graph_id?: string | null;
  model?: string | null;
  /**
   * YYYY-MM-DD(서버 시간대).
   */
  day?: string | null;
  usage: Usage;
  runs?: number | null;
  /**
   * 값의 정밀도 메모(예: 총 토큰만 있음). 화면이 그대로 표시한다.
   */
  precision?: string | null;
}
/**
 * `GET /runs/{id}/trace` 응답.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "Trace".
 */
export interface Trace {
  run_id: string;
  spans?: TraceSpan[];
  links?: TraceLink[];
}
/**
 * 위임 흐름의 구간 하나.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "TraceSpan".
 */
export interface TraceSpan {
  id: string;
  /**
   * 구간 종류 문자열. 알려진 값: node(자기 NodeRun), delegated(위 세션 안 위임), interaction(사용자 대기). 다른 값도 허용(호출 NodeRun·자식 Run 묶음 등, 해석은 화면).
   */
  kind: string;
  /**
   * 부모 span id(같은 세션 안 위임).
   */
  parent_id?: string | null;
  node_id?: string | null;
  node_path?: string[];
  /**
   * 에이전트 정의 id.
   */
  actor?: string | null;
  attempt?: number | null;
  /**
   * 반복 회차.
   */
  iteration?: number | null;
  /**
   * 호출 회차(위임자가 부른 NodeRun이면).
   */
  call?: number | null;
  /**
   * 이 span이 속한 Run이 trace의 Run과 다르면(자식 Run) 그 Run id.
   */
  run_id?: string | null;
  status?: string | null;
  started_at?: number | null;
  ended_at?: number | null;
  usage?: Usage | null;
  /**
   * 백엔드 세션 id(같은/별도 세션 표시).
   */
  session_id?: string | null;
  tool_use_id?: string | null;
  interaction_id?: string | null;
  /**
   * 넘기기 순번(그래프 강조 배지).
   */
  order?: number | null;
  task_preview?: string | null;
  result_preview?: string | null;
}
/**
 * span 사이 화살표(넘기기 등). 부모-자식 관계는 `TraceSpan.parent_id`로 표현한다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "TraceLink".
 */
export interface TraceLink {
  /**
   * 출발 span id.
   */
  source: string;
  /**
   * 도착 span id.
   */
  target: string;
  edge_id?: string | null;
  /**
   * 연결 종류 id(엣지 kind).
   */
  kind?: string | null;
  /**
   * 도착 span이 자식 Run에 있으면 그 Run id.
   */
  run_id?: string | null;
}
/**
 * 화면 동작 설정.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UiPreferences".
 */
export interface UiPreferences {
  /**
   * 동작마다 키 조합을 바꿉니다. 적은 항목만 바뀌고 나머지는 기본 키입니다.
   */
  keybindings?: {
    [k: string]: string;
  } | null;
  notifications?: NotificationSettings;
  usage_indicator?: UsageIndicatorSettings;
  versions?: VersionUiSettings;
  [k: string]: unknown;
}
/**
 * 모든 화면에 보이는 사용량 표시기입니다. 비운 항목은 기본값을 씁니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UsageIndicatorSettings".
 */
export interface UsageIndicatorSettings {
  /**
   * 모든 화면 구석에 남은·쓴 사용량을 작게 보입니다.
   */
  enabled?: boolean;
  /**
   * 표시기를 놓을 곳입니다. 모르는 값이면 사이드바 아래에 보입니다.
   */
  placement?: string;
  /**
   * 보일 사용량 창. 비우면 출처가 준 순서의 앞쪽부터 보일 창 수만큼 보입니다.
   */
  windows?: string[];
  /**
   * 보일 창을 고르지 않았을 때 앞에서부터 몇 개를 보일지입니다(1~6).
   */
  max_items?: number;
  /**
   * 항목에 보일 요소(순서대로). 알려진 값: label, value, gauge, reset, trust, observed. 모르는 값은 무시합니다.
   */
  fields?: string[];
  /**
   * 숫자와 게이지를 사용한 양/남은 양 중 무엇으로 보일지. 남은 양으로 보려면 remaining.
   */
  value_mode?: "remaining" | "used";
  /**
   * 사용률이 기준 이상이면 게이지를 그 색으로 칠합니다(가장 높은 기준이 이깁니다). 기본은 0% 초록·70% 노랑·90% 빨강입니다. 비우면 색을 바꾸지 않습니다.
   */
  color_rules?: UsageIndicatorColorRule[];
  /**
   * 받은 사용량이 하나도 없으면 표시기를 숨깁니다.
   */
  hide_when_empty?: boolean;
  /**
   * 브라우저 탭·창 제목에도 첫 항목을 붙입니다.
   */
  also_in_title?: boolean;
  [k: string]: unknown;
}
/**
 * 사용률 임계 색 규칙 한 줄.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UsageIndicatorColorRule".
 */
export interface UsageIndicatorColorRule {
  /**
   * 사용률(0~1)이 이 값 이상이면 규칙을 적용합니다.
   */
  at: number;
  /**
   * 칠할 색 이름입니다(예: warning, danger). 모르는 값은 기본 색으로 그립니다.
   */
  tone: string;
  [k: string]: unknown;
}
/**
 * 버전 비교 화면 설정입니다. 비운 항목은 기본값을 씁니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "VersionUiSettings".
 */
export interface VersionUiSettings {
  /**
   * 버전 비교에서 노드·연결 등을 부를 때 찾을 이름 키입니다(앞에서부터). 비우면 label, name, title, id.
   */
  item_label_keys?: string[] | null;
  [k: string]: unknown;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UnsubscribeMessage".
 */
export interface UnsubscribeMessage {
  /**
   * 요청 상관 id(선택).
   */
  id?: string | null;
  type: "unsubscribe";
  payload: UnsubscribePayload;
}
/**
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UnsubscribePayload".
 */
export interface UnsubscribePayload {
  topic: string;
}
/**
 * `PATCH /conversations/{id}` 요청. 생략한 필드는 그대로 둔다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UpdateConversationRequest".
 */
export interface UpdateConversationRequest {
  title?: string | null;
  archived?: boolean | null;
  /**
   * 팀 구성 전환. 새 팀 구성에 없는 노드의 세션은 버린다.
   */
  graph_id?: string | null;
}
/**
 * `GET /usage` 응답: 창 스냅샷 + 토큰 집계.
 *
 * 부분 조회: `GET /usage?parts=windows,tokens`(쉼표 목록).
 * 알려진 부분 이름은 `USAGE_REPORT_PARTS`(`windows` → `windows`, `tokens` → `rollups`)이고,
 * `parts`를 생략하면 전부다. 요청하지 않은 부분은 **null**(= 요청 안 함)이다.
 * 빈 목록은 "요청했지만 값 없음"이며 둘을 구분한다. 모르는 부분 이름은 무시한다(전방 호환).
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UsageReport".
 */
export interface UsageReport {
  /**
   * 창 스냅샷(부분 windows). null = 요청하지 않음.
   */
  windows?: UsageWindowSnapshot[] | null;
  /**
   * 플랫폼 실행분 토큰 집계(부분 tokens). null = 요청하지 않음.
   */
  rollups?: TokenRollupRow[] | null;
  generated_at: number;
}
/**
 * 사용량 창 하나의 관측값.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UsageWindowSnapshot".
 */
export interface UsageWindowSnapshot {
  /**
   * 사용량 출처 id.
   */
  source: string;
  /**
   * 창 id(출처가 정함, 고정 목록 아님).
   */
  window: string;
  /**
   * 사용률(0~1, 넘을 수 있음).
   */
  used_ratio?: number | null;
  used_tokens?: number | null;
  /**
   * 출처가 주는 상태 문자열.
   */
  status?: string | null;
  /**
   * 초기화 시각(Unix epoch 초).
   */
  resets_at?: number | null;
  /**
   * 관측 시각(Unix epoch 초).
   */
  observed_at: number;
  /**
   * 출처 원문(비밀 제거 후).
   */
  raw?: unknown;
}
/**
 * 사용량 화면 설정입니다. 사용량 출처와 사용량 창의 표시 이름을 정합니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UsageSettings".
 */
export interface UsageSettings {
  /**
   * 사용량 창 이름을 화면에 보일 이름으로 바꿉니다(창 id → 이름).
   */
  window_labels?: {
    [k: string]: string;
  };
  /**
   * 사용량을 읽어 올 곳과 각 설정입니다. 비우면 자동으로 켜지는 출처를 씁니다.
   */
  sources?: UsageSourceSetting[];
  /**
   * 창 카드에 크게 보일 출처 순서입니다. 비우면 가장 최근 공식 값을 씁니다.
   */
  primary_source_order?: string[];
  /**
   * 값을 받은 뒤 이 시간이 지나면 오래된 값으로 표시합니다. 비우면 판정하지 않습니다.
   */
  stale_after_seconds?: number | null;
  [k: string]: unknown;
}
/**
 * 사용량 출처 하나의 사용 여부·설정.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UsageSourceSetting".
 */
export interface UsageSourceSetting {
  /**
   * 사용량을 읽어 올 곳입니다(예: 실행 기록, 상태 줄 파일).
   */
  id: string;
  /**
   * 이 출처에서 사용량을 읽을지 정합니다.
   */
  enabled?: boolean;
  /**
   * 출처마다 정한 추가 설정입니다(예: 읽을 파일 경로).
   */
  config?: {
    [k: string]: unknown;
  };
  [k: string]: unknown;
}
/**
 * 출처 연결 안내 조각 하나(복사해 붙이는 설정·명령, 0.8.0).
 *
 * `text`의 자리표시자(예: `{output_path}`·`{agent_console_cmd}`)는 서버가 절대 경로로 채워 준다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UsageSetupSnippet".
 */
export interface UsageSetupSnippet {
  id: string;
  /**
   * 조각 제목(예: 상태 줄 설정).
   */
  title: string;
  /**
   * 어느 셸·환경용인지(예: bash, powershell). 빈 값 = 공통.
   */
  shell?: string;
  /**
   * 코드 강조 언어(예: json, bash). 빈 값 = 일반 글.
   */
  language?: string;
  /**
   * 복사할 본문.
   */
  text: string;
}
/**
 * 사용량 출처 디스크립터.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UsageSourceDescriptor".
 */
export interface UsageSourceDescriptor {
  id: string;
  title: string;
  description?: string;
  config_schema?: {
    [k: string]: unknown;
  };
  trust: UsageTrust;
  /**
   * 출처 설정 방법 안내(마크다운). 화면에 그대로 보인다.
   */
  setup_help?: string | null;
  /**
   * 자세한 문서 링크(http(s) URL).
   */
  docs_url?: string | null;
  /**
   * 설정에 출처 목록이 없으면 켠 것으로 본다.
   */
  auto_enable?: boolean;
  /**
   * 값을 받으려면 사용자가 연결 설정을 해야 한다(setup_snippets).
   */
  needs_setup?: boolean;
  /**
   * 시험용 출처. 자동으로 켜지 않는다.
   */
  test_only?: boolean;
  /**
   * 연결 안내 조각(복사용).
   */
  setup_snippets?: UsageSetupSnippet[];
  /**
   * 이 출처가 내는 창과 표시 이름. 비우면 모름.
   */
  windows?: UsageWindowInfo[];
}
/**
 * 출처가 내는 사용량 창 하나의 표시 정보(0.8.0).
 *
 * 사용자 설정 `usage.window_labels`가 우선한다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UsageWindowInfo".
 */
export interface UsageWindowInfo {
  /**
   * 창 id(`UsageWindowSnapshot.window`).
   */
  id: string;
  /**
   * 창 이름(예: 5시간 창).
   */
  title: string;
  /**
   * 좁은 자리용 짧은 이름(예: 5h).
   */
  short_title?: string | null;
}
/**
 * `GET /usage/sources` 항목: 출처 디스크립터와 현재 상태.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "UsageSourceInfo".
 */
export interface UsageSourceInfo {
  descriptor: UsageSourceDescriptor;
  enabled?: boolean;
  config?: {
    [k: string]: unknown;
  };
  last_observed_at?: number | null;
  /**
   * 출처에서 마지막으로 값을 받은 시각(Unix epoch 초, 0.8.0). null = 받은 적 없음.
   */
  last_received_at?: number | null;
  error?: ErrorInfo | null;
}
/**
 * `version_conflict`(HTTP 412) 오류의 `error.details`. 서버의 현재 버전 요약.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "VersionConflictDetails".
 */
export interface VersionConflictDetails {
  current_version_hash: string;
  saved_at?: number | null;
  node_count?: number | null;
  edge_count?: number | null;
}
/**
 * `GET/PUT /graphs/{id}`, `POST /graphs` 응답. `version_hash`는 ETag와 같은 값.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "VersionedGraph".
 */
export interface VersionedGraph {
  graph: Graph;
  version_hash: string;
  saved_at?: number | null;
}
/**
 * 이 워크스페이스의 공통 설정과 사용자 설정입니다.
 *
 * This interface was referenced by `AgentConsoleContracts`'s JSON-Schema
 * via the `definition` "WorkspaceSettings".
 */
export interface WorkspaceSettings {
  /**
   * 파일 형식 번호입니다. 직접 바꾸지 않습니다.
   */
  schema_version?: number;
  agent_defaults?: AgentDefaults;
  chat?: ChatSettings;
  editor?: EditorSettings;
  delegation?: DelegationSettings;
  flow?: FlowSettings;
  interaction?: InteractionSettings;
  usage?: UsageSettings;
  ui?: UiPreferences;
  /**
   * 설정 항목마다 공통·팀·에이전트 설정을 합치는 방법을 바꿉니다(예: /limits → intersect).
   */
  settings_merge?: {
    [k: string]: string;
  };
  secrets?: SecretRuleSettings;
  logs?: LogSettings;
  /**
   * 새 정의를 공용으로 둘지 프로젝트 전용으로 둘지의 기본값입니다.
   */
  projects?: ProjectPreferences | null;
  /**
   * @deprecated
   * 더 이상 쓰지 않습니다. 에이전트 공통 설정의 실행 백엔드를 씁니다(읽기만 함).
   */
  default_backend?: string | null;
  /**
   * 다른 도구가 읽는 자유 속성입니다. 보통은 비워 둡니다.
   */
  attributes?: {
    [k: string]: unknown;
  };
  [k: string]: unknown;
}

// ---- 상수 (schema x-constants)

export const CONTRACTS_VERSION = "0.8.0" as const;

export const CONTRACT_VERSIONS = {
  "common": "1.3.0",
  "resources": "1.1.0",
  "logs": "1.0.0",
  "definitions": "1.3.0",
  "runs": "1.3.0",
  "usage": "1.1.0",
  "projects": "1.0.0",
  "chat": "1.1.0",
  "exports": "1.0.0",
  "imports": "1.1.0",
  "modules": "1.2.0"
} as const;

export const USAGE_REPORT_PARTS = [
  "windows",
  "tokens"
] as const;

export const KNOWN_RUN_EVENT_TYPES = [
  "run.created",
  "run.started",
  "run.paused",
  "run.resumed",
  "run.waiting",
  "run.completed",
  "run.failed",
  "run.cancelled",
  "run.interrupted",
  "node.queued",
  "node.started",
  "node.waiting",
  "node.resumed",
  "node.completed",
  "node.failed",
  "node.skipped",
  "node.cancelled",
  "edge.traversed",
  "agent.session_started",
  "agent.text_delta",
  "agent.message",
  "agent.tool_call",
  "agent.tool_result",
  "agent.subagent_started",
  "agent.subagent_stopped",
  "agent.usage",
  "log.warning",
  "run.reply",
  "usage.rate_limit",
  "interaction.requested",
  "interaction.answered",
  "interaction.closed",
  "edge.skipped",
  "loop.iteration",
  "loop.exhausted",
  "run.child_started",
  "run.child_finished"
] as const;

export const RUN_ORIGINS = [
  "chat",
  "web",
  "api",
  "task",
  "resume"
] as const;

export const LOG_EVENT_ORDERS = [
  "asc",
  "desc"
] as const;

export const LOG_PROJECT_UNGROUPED = "~ungrouped" as const;

export const ERROR_CODES = {
  "BAD_REQUEST": "bad_request",
  "VALIDATION_FAILED": "validation_failed",
  "UNAUTHORIZED": "unauthorized",
  "FORBIDDEN": "forbidden",
  "NOT_FOUND": "not_found",
  "ALREADY_EXISTS": "already_exists",
  "VERSION_CONFLICT": "version_conflict",
  "VERSION_REQUIRED": "version_required",
  "PAYLOAD_TOO_LARGE": "payload_too_large",
  "INTERNAL": "internal",
  "CONVERSATION_BUSY": "conversation_busy",
  "INTERACTION_CLOSED": "interaction_closed",
  "RUN_NOT_RESUMABLE": "run_not_resumable",
  "FEATURE_UNAVAILABLE": "feature_unavailable",
  "NOT_READY": "not_ready",
  "BACKEND_UNRESOLVED": "backend.unresolved",
  "BACKEND_PROBE_UNSUPPORTED": "backend.probe_unsupported"
} as const;

export const HTTP_STATUS_BY_ERROR_CODE = {
  "bad_request": 400,
  "validation_failed": 422,
  "unauthorized": 401,
  "forbidden": 403,
  "not_found": 404,
  "already_exists": 409,
  "version_conflict": 412,
  "version_required": 428,
  "payload_too_large": 413,
  "internal": 500,
  "conversation_busy": 409,
  "interaction_closed": 409,
  "run_not_resumable": 409,
  "feature_unavailable": 409,
  "not_ready": 503,
  "backend.unresolved": 422,
  "backend.probe_unsupported": 409
} as const;

export const KNOWN_ISSUE_CODES = {
  "LIMITS_NOT_ENFORCED": "limits.not_enforced",
  "RESOURCE_SLOT_UNSUPPORTED": "resource.slot_unsupported",
  "RESOURCE_SLOT_SESSION_SHARED": "resource.slot_session_shared",
  "SECRET_PLAIN_FOUND": "secret.plain_found",
  "LOGS_SOURCE_FAILED": "logs.source_failed",
  "LOGS_REDACTION_UNAVAILABLE": "logs.redaction_unavailable",
  "LOGS_STORAGE_MEMORY": "logs.storage_memory",
  "LOGS_UNKNOWN_CLASSIFIER": "logs.unknown_classifier",
  "FLOW_MAX_ITERATIONS_INVALID": "flow.max_iterations_invalid",
  "FLOW_MAX_NODE_RUNS_EXCEEDED": "flow.max_node_runs_exceeded",
  "CONDITION_UNKNOWN_OPERATOR": "condition.unknown_operator",
  "CONDITION_INVALID_VALUE": "condition.invalid_value",
  "TEAM_MIXED_STRATEGIES": "team.mixed_strategies",
  "TEAM_RECURSIVE": "team.recursive",
  "TEAM_NESTING_EXCEEDED": "team.nesting_exceeded",
  "TEAM_TEAM_NOT_FOUND": "team.team_not_found",
  "TEAM_CHILD_NO_ENTRY": "team.child_no_entry",
  "DELEGATION_DEPTH_EXCEEDED": "delegation.depth_exceeded",
  "BACKEND_UNRESOLVED": "backend.unresolved",
  "PROJECT_SHARED_USES_PROJECT": "project.shared_uses_project",
  "PROJECT_CROSS_PROJECT": "project.cross_project",
  "PROJECT_UNKNOWN": "project.unknown",
  "PROJECT_REFERENCES_UNAVAILABLE": "project.references_unavailable",
  "PROJECT_DEFINITIONS_UNAVAILABLE": "project.definitions_unavailable"
} as const;

export const KNOWN_SUGGESTION_IDS = {
  "PROJECT_MOVE_TO_SHARED": "project.move_to_shared"
} as const;

export const WS_CLOSE_UNAUTHORIZED = 4401 as const;

export const WS_CLOSE_FORBIDDEN = 4403 as const;

export const WS_AUTH_CLOSE_CODES = [
  4401,
  4403
] as const;

export const X_UI = "x-ui" as const;

export const X_UI_TIERS = [
  "basic",
  "advanced"
] as const;

export const USER_TEXT_RULES = {
  "version": 1,
  "description": "사용자에게 보이는 문구에 넣지 않는 패턴(설계 문서 번호·내부 노드 id). Python·TS 린트 테스트가 이 파일 하나를 읽는다. 패턴은 Python re와 JavaScript RegExp가 같게 읽는 문법만 쓴다.",
  "scopes": {
    "description": "계약 모델·필드 설명과 플러그인 디스크립터 문자열(설명·제목·config 스키마 설명)",
    "messages": "서버가 만드는 사용자 문구(검증 이슈·실행 실패 요약·문제 응답·해결 버튼)와 웹 메시지 표"
  },
  "patterns": [
    {
      "id": "design-ref",
      "pattern": "design §",
      "scopes": [
        "description",
        "messages"
      ],
      "reason": "설계 문서 인용은 개발자용이다. 사용자 문구에는 무엇을 하는지만 적는다."
    },
    {
      "id": "section-number",
      "pattern": "§\\d",
      "scopes": [
        "description",
        "messages"
      ],
      "reason": "문서 절 번호는 사용자에게 뜻이 없다."
    },
    {
      "id": "requirement-id",
      "pattern": "R\\d+\\.\\d",
      "scopes": [
        "description",
        "messages"
      ],
      "reason": "요구사항 번호는 사용자에게 뜻이 없다."
    },
    {
      "id": "node-id",
      "pattern": "'n\\d+'",
      "scopes": [
        "messages"
      ],
      "reason": "내부 노드 id 대신 노드 이름(label)으로 부른다. id는 details에만 둔다."
    }
  ]
} as const;
