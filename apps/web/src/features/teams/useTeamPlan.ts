import type { Graph, TeamPlanSummary } from "@agent-console/contracts";
import { useDraftPreview, type DraftPreviewResult } from "./useDraftPreview";

/**
 * 팀 구성 계획 요약(입구·답변 자리·상호작용 허용). 저장 전 변경이 있으면 초안(`POST /graphs/plan`), 아니면 저장본(`GET /graphs/{id}/plan`).
 * 답변 자리의 라벨·순서·마지막 답변·스트림 같은 값은 연결 설정을 직접 읽지 않고 이 요약에서만 읽는다.
 */
export function useTeamPlan(graphId: string, graph: Graph | undefined, dirty: boolean): DraftPreviewResult<TeamPlanSummary> {
  return useDraftPreview<TeamPlanSummary, Graph>({
    keyBase: ["graph-plan", graphId],
    draftInput: dirty ? graph : undefined,
    savedEnabled: graph !== undefined,
    loadSaved: (rest) => rest.getGraphPlan(graphId),
    loadDraft: (rest, g) => rest.planDraftGraph({ graph: g }),
  });
}
