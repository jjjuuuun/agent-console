import { LINK_PART_IDS as P, type LinkPartDef } from "../modules";

/**
 * 연동 부분 등록 데이터(`docs/design/screen-modules.md` 4.2). 화면 컴포넌트는 부분 id만 알고,
 * 어떤 모듈·역할이 필요한지는 여기서만 정한다. 사용자가 다르게 원하면 이 배열만 고친다.
 *
 * `requires`는 서버 `ModuleInfo.web_roles`의 역할 이름이다. 연동 모듈(3R.13~16)이 선언한 연동 역할을 쓴다
 * (예: 흐름 탭은 `runs:trace`). 아직 역할이 없는 곳은 각 줄 옆에 적었다.
 *
 * - `hide`: 보너스 정보라서 없으면 자리도 없다. 숨긴 부분은 API를 부르지 않는다.
 * - `disable`: 사용자가 하려던 주 동작이라서 자리는 두고 이유를 보인다.
 */
export const DEFAULT_LINK_PARTS: readonly LinkPartDef[] = [
  // 채팅 (screen-chat.md 4.2 b, 5, 6, 7)
  { id: P.chatDelegationChip, requires: ["conversations:runs"], onMissing: "hide" },
  { id: P.chatInteractionCard, requires: ["conversations:runs"], onMissing: "hide" },
  { id: P.chatSend, requires: ["conversations:runs"], onMissing: "disable", noteKey: "sendUnavailable" },
  { id: P.chatResumeTurn, requires: ["conversations:runs"], onMissing: "hide" },
  // 실행 (screen-runs-usage.md 1.3, 2.4)
  { id: P.runsFlowTab, requires: ["runs:trace"], onMissing: "hide" },
  { id: P.runsHandoffView, requires: ["runs:trace"], onMissing: "hide" },
  // 사용량 (screen-runs-usage.md 3.4)
  { id: P.usageTokenRollup, requires: ["usage:tokens"], onMissing: "hide" },
  // 로그 (screen-logs.md 1.2). 부분 id·역할은 이 데이터에서만 정한다.
  { id: P.logsTraceFlow, requires: ["logs:trace"], onMissing: "hide" },
  { id: P.logsRunLink, requires: ["runs"], onMissing: "hide" },
  { id: P.logsRunsTab, requires: ["logs:runs"], onMissing: "hide" },
  // 세션 상세 흐름 패널의 [구조도] 세그먼트(screen-architecture.md 5). 없으면 세그먼트도 질의도 없다.
  { id: P.logsArchitectureFlow, requires: ["logs:architecture"], onMissing: "hide" },
  // 실행 상세 검사 패널의 [구조도] 탭(screen-architecture.md 6.1). 로그 구조도와 로그-실행 연동이 모두 있어야 한다.
  { id: P.runsArchitectureTab, requires: ["logs:architecture", "logs:runs"], onMissing: "hide" },
  { id: P.logsUsageLink, requires: ["usage"], onMissing: "hide" },
  // 팀 구성·에이전트 (screens-v3.md 2.1, 2.5)
  { id: P.teamsValidationColumn, requires: ["definitions:graph", "runs:team-rules"], onMissing: "hide" },
  // 정의-팀 연동 역할(`definitions:teams`): 에이전트 사용처 패널과 저장 전 초안 미리보기(유효 설정·계획·묶음).
  // 없으면 부분이 숨고 사용처·초안 요청도 나가지 않는다(초안은 묻지 않고 저장본을 읽는다).
  { id: P.agentsUsagesPanel, requires: ["definitions:teams"], onMissing: "hide" },
  { id: P.teamsDraftPreview, requires: ["definitions:teams"], onMissing: "hide" },
  // 조건 편집 위젯의 연산자 목록(screen-delegation.md 1.2). 없으면 연산자를 자유 입력으로 받고 목록을 부르지 않는다.
  { id: P.teamsConditionOperators, requires: ["runs"], onMissing: "hide" },
  // 위임 흐름 탭의 자식 실행 묶음(탭 자체가 `runs:trace`에 달려 있어 별도 처리 없음)
  { id: P.runsTraceChildGroups, requires: ["runs:trace"], onMissing: "hide" },
  // 내보내기의 "의존 항목 자동 포함"(screens-v3.md 3)은 아직 화면에 없다. 생기면 `exports.dependencies`를 여기에 등록한다.
];
