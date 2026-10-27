import { useMemo } from "react";
import type { StepGuideStep } from "@agent-console/ui";
import { useApiQuery, queryKeys } from "../../app/queries";
import { ROUTE_ROLES, routePath, useGraphList, useRoutesOn } from "../library";
import { buildStartSteps } from "./startSteps";

export interface StartGuide {
  /** 데이터를 모두 받았는가(받기 전에는 카드를 그리지 않는다) */
  ready: boolean;
  steps: StepGuideStep[];
  /** 모든 단계 완료 */
  allDone: boolean;
}

/** 첫 단계 안내의 데이터(세 곳 공용). 표현은 ui의 `StepGuide`가 맡는다. */
export function useStartGuide(): StartGuide {
  const isOn = useRoutesOn();
  const runsOn = isOn(ROUTE_ROLES.runs);
  const graphs = useGraphList();
  const conversations = useApiQuery(queryKeys.list("conversations"), (r) => r.listConversations());
  const runs = useApiQuery(queryKeys.list("runs", { limit: 1 }), (r) => r.listRuns({ limit: 1 }), { enabled: runsOn });

  const steps = useMemo(
    () =>
      buildStartSteps({
        counts: {
          usableTeams: graphs.data === undefined ? undefined : graphs.data.filter((g) => g.entry_labels == null || g.entry_labels.length > 0).length,
          conversations: conversations.data?.length,
          runs: runs.data?.length,
        },
        pathOf: routePath,
        isOn,
      }),
    [graphs.data, conversations.data, runs.data, isOn],
  );

  return {
    ready: graphs.data !== undefined && conversations.data !== undefined,
    steps,
    allDone: steps.length > 0 && steps.every((s) => s.done),
  };
}
