import { projectBody, useProjectId } from "../../app/projectScope";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import type { PresetSummary } from "@agent-console/contracts";
import type { QuickStartItem, StepGuideStep } from "@agent-console/ui";
import { useApi } from "../../app/ApiContext";
import { describeError } from "../../app/errors";
import { queryKeys, useApiQuery } from "../../app/queries";
import { LINK_PART_IDS, useLinkPart } from "../../modules";
import { ROUTE_ROLES, routePath, useAgentList, useGraphList, useRoutesOn } from "../library";
import { startMessages } from "./messages";
import { buildStartSteps } from "./startSteps";

/** 바로 시작 줄에 보일 프리셋 최대 개수 */
export const QUICK_START_MAX = 3;

/** `featured`가 있는 프리셋만 그 순서(작은 값 먼저, 같으면 목록 순서)로 최대 `max`개. */
export function pickFeatured(presets: readonly PresetSummary[], max = QUICK_START_MAX): PresetSummary[] {
  return presets
    .map((p, i) => ({ p, i }))
    .filter(({ p }) => typeof p.featured === "number")
    .sort((a, b) => (a.p.featured as number) - (b.p.featured as number) || a.i - b.i)
    .slice(0, max)
    .map(({ p }) => p);
}

function itemIds(preset: PresetSummary): string[] {
  return (preset.items ?? []).map((raw) => (typeof raw["id"] === "string" ? raw["id"] : "")).filter((id) => id !== "");
}

export interface StartGuide {
  /** 데이터를 모두 받았는가(받기 전에는 카드를 그리지 않는다) */
  ready: boolean;
  steps: StepGuideStep[];
  /** 모든 단계 완료 */
  allDone: boolean;
  quickItems: QuickStartItem[];
  /** 프리셋 [시작]. 충돌이 있으면 `conflictPreset`을 채워 적용 대화상자를 연다. */
  startQuick: (id: string) => void;
  /** 이름·id 충돌로 기존 적용 대화상자가 필요한 프리셋 */
  conflictPreset: PresetSummary | null;
  closeConflict: () => void;
  error: string | null;
  /** 적용은 됐지만 열 대화를 못 찾았을 때 안내할 경로 */
  fallbackPath: string | null;
  /** 충돌 판정용 기존 id */
  existingIds: ReadonlySet<string>;
}

/**
 * 첫 단계 안내의 데이터·동작(세 곳 공용). 표현은 ui의 `StepGuide`·`QuickStartRow`가 맡는다.
 * 프리셋 [시작] = `POST /presets/{id}/apply` -> 결과에서 `start_graph` 항목의 `target_id` -> `POST /conversations` -> 그 대화 화면.
 */
export function useStartGuide(): StartGuide {
  const { rest } = useApi();
  const projectId = useProjectId();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isOn = useRoutesOn();
  const presetsPart = useLinkPart(LINK_PART_IDS.chatStartPresets);
  const runsOn = isOn(ROUTE_ROLES.runs);
  const graphs = useGraphList();
  const agents = useAgentList();
  const conversations = useApiQuery(queryKeys.list("conversations"), (r) => r.listConversations());
  const runs = useApiQuery(queryKeys.list("runs", { limit: 1 }), (r) => r.listRuns({ limit: 1 }), { enabled: runsOn });
  const resources = useApiQuery(queryKeys.list("resources"), (r) => r.listResources());
  const presets = useApiQuery(queryKeys.list("presets"), (r) => r.listPresets(), { enabled: presetsPart.visible });

  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fallbackPath, setFallbackPath] = useState<string | null>(null);
  const [conflictPreset, setConflictPreset] = useState<PresetSummary | null>(null);

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
  const featured = useMemo(() => pickFeatured(presets.data ?? []), [presets.data]);
  const existingIds = useMemo(
    () => new Set<string>([...(agents.data ?? []).map((a) => a.id), ...(graphs.data ?? []).map((g) => g.id), ...(resources.data ?? []).map((r) => r.id)]),
    [agents.data, graphs.data, resources.data],
  );

  const startQuick = (id: string) => {
    const preset = featured.find((p) => p.id === id);
    if (preset === undefined || busyId !== null) return;
    setError(null);
    setFallbackPath(null);
    // 이름·id가 겹치거나 열 팀 구성을 모르면(여러 팀) 기존 적용 대화상자에서 고른다.
    if (preset.start_graph == null || itemIds(preset).some((x) => existingIds.has(x))) {
      setConflictPreset(preset);
      return;
    }
    setBusyId(id);
    void (async () => {
      try {
        const res = await rest.applyPreset(id, projectId === null ? {} : { project: projectId });
        void queryClient.invalidateQueries({ queryKey: ["list"] });
        const failed = (res.items ?? []).some((i) => i.action === "failed");
        const target = preset.start_graph == null ? undefined : (res.items ?? []).find((i) => i.kind === "graph" && i.id === preset.start_graph)?.target_id;
        if (failed || target == null || target === "") {
          setError(startMessages.quick.noStartTeam);
          setFallbackPath(routePath(ROUTE_ROLES.graph));
          return;
        }
        const conv = await rest.createConversation({ graph_id: target, ...projectBody(projectId) });
        void queryClient.invalidateQueries({ queryKey: ["list"] });
        void queryClient.invalidateQueries({ queryKey: ["chat"] });
        void navigate(`${routePath(ROUTE_ROLES.conversations)}/${encodeURIComponent(conv.id)}`);
      } catch (e) {
        setError(describeError(e, startMessages.quick.failed).message);
      } finally {
        setBusyId(null);
      }
    })();
  };

  const quickItems: QuickStartItem[] = featured.map((p) => ({
    id: p.id,
    title: p.name,
    ...(p.description ? { description: p.description } : {}),
    ...(p.badges && p.badges.length > 0 ? { badges: p.badges } : {}),
    busy: busyId === p.id,
  }));

  return {
    ready: graphs.data !== undefined && conversations.data !== undefined,
    steps,
    allDone: steps.length > 0 && steps.every((s) => s.done),
    quickItems,
    startQuick,
    conflictPreset,
    closeConflict: () => setConflictPreset(null),
    error,
    fallbackPath,
    existingIds,
  };
}
