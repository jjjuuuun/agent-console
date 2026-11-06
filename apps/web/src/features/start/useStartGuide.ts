import { useMemo } from "react";
import type { StepGuideStep } from "@agent-console/ui";
import { useApi } from "../../app/ApiContext";
import { useApiQuery, queryKeys } from "../../app/queries";
import { useQuery } from "@tanstack/react-query";
import { buildProjectStartSteps, projectHomePath, useProjects } from "../projects";
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

  // 프로젝트 기능이 켜져 있으면 시작하기는 폴더 추가로 시작하는 4단계다(데이터: projects/projectStartSteps)
  const p = useProjects();
  const { rest, space } = useApi();
  const current = p.current;
  const projectTeams = useQuery({
    queryKey: ["list", "start", "project-teams", current],
    queryFn: () => space(current).listGraphs(),
    enabled: p.enabled && current !== null,
    retry: false,
    meta: { silentBackgroundError: true },
  });
  const projectChats = useQuery({
    queryKey: ["list", "start", "project-chats", current],
    queryFn: () => rest.listConversations({ project: current as string }),
    enabled: p.enabled && current !== null,
    retry: false,
    meta: { silentBackgroundError: true },
  });
  const projectSteps = useMemo(() => {
    if (!p.enabled) return null;
    const active = p.views.filter((v) => v.project.archived !== true).length;
    const graphRole = ROUTE_ROLES.graph;
    return buildProjectStartSteps({
      counts: {
        projects: p.loaded ? active : undefined,
        libraryTeams: graphs.data?.length,
        projectTeams: current === null ? 0 : projectTeams.data?.length,
        projectConversations: current === null ? 0 : projectChats.data?.length,
      },
      actions: {
        folder: { onAction: () => p.requestAddFolder() },
        ...(isOn(graphRole) ? { library: { to: routePath(graphRole) } } : {}),
        import: current === null ? {} : { to: projectHomePath(current) },
        ...(isOn(ROUTE_ROLES.conversations) ? { chat: { to: routePath(ROUTE_ROLES.conversations) } } : {}),
      },
    });
  }, [p, graphs.data, projectTeams.data, projectChats.data, current, isOn]);

  const steps = useMemo(
    () =>
      projectSteps ??
      buildStartSteps({
        counts: {
          usableTeams: graphs.data === undefined ? undefined : graphs.data.filter((g) => g.entry_labels == null || g.entry_labels.length > 0).length,
          conversations: conversations.data?.length,
          runs: runs.data?.length,
        },
        pathOf: routePath,
        isOn,
      }),
    [projectSteps, graphs.data, conversations.data, runs.data, isOn],
  );

  return {
    ready: graphs.data !== undefined && conversations.data !== undefined && (!p.enabled || p.loaded),
    steps,
    allDone: steps.length > 0 && steps.every((s) => s.done),
  };
}
