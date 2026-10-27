/**
 * 연동 부분 id(화면 코드가 부르는 이름). 필요한 모듈·역할은 이 파일이 아니라 등록 데이터(`links/linkParts.ts`)가 정한다.
 * 기능 폴더는 `links/`를 import하지 않으므로 id 상수만 이 공용 층에 둔다.
 */
export const LINK_PART_IDS = {
  chatDelegationChip: "chat.delegation-chip",
  chatInteractionCard: "chat.interaction-card",
  chatSend: "chat.send",
  chatResumeTurn: "chat.resume-turn",
  runsFlowTab: "runs.flow-tab",
  runsHandoffView: "runs.handoff-view",
  usageTokenRollup: "usage.token-rollup",
  logsTraceFlow: "logs.trace-flow",
  logsRunLink: "logs.run-link",
  logsRunsTab: "logs.runs-tab",
  logsArchitectureFlow: "logs.architecture-flow",
  logsUsageLink: "logs.usage-link",
  teamsValidationColumn: "teams.validation-column",
  agentsUsagesPanel: "agents.usages-panel",
  teamsDraftPreview: "teams.draft-preview",
  teamsConditionOperators: "teams.condition-operators",
  runsTraceChildGroups: "runs.trace-child-groups",
} as const;
