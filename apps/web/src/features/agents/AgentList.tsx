import { LINK_PART_IDS, useLinkPart } from "../../modules";
import { useMemo, useRef, useState, type ReactNode } from "react";
import { useQueries } from "@tanstack/react-query";
import type { Agent } from "@agent-console/contracts";
import { NONE_KEY, folderOf } from "@agent-console/list-arrange";
import { Button, EmptyState, ListPane } from "@agent-console/ui";
import { ErrorBlock } from "../../app/ErrorBlock";
import { useApi } from "../../app/ApiContext";
import { Skeleton } from "../settings";
import { useListShortcuts, useListView, routeIconNode, ROUTE_ROLES, libraryMessages, ListEditDialogs } from "../library";
import { filterAgents } from "./agentLogic";
import { agentGroupDefs, agentSortDefs, attributeKeys } from "./arrange";
import { useAgentEdits } from "./useAgentEdits";
import { agentMessages as t } from "./messages";

export interface AgentListProps {
  agents: readonly Agent[] | undefined;
  loading: boolean;
  error: Error | null;
  onRetry: () => void;
  selectedId: string | undefined;
  onSelect: (id: string) => void;
  onNew: () => void;
  onRename: (id: string) => void;
  onDelete: (id: string) => void;
  /** 목록 머리에 끼울 줄(프로젝트 범위 필터 등, 없으면 생략) */
  scopeBar?: ReactNode;
  /** 이름 줄 끝에 붙일 요소(범위 태그·선택 표시 등) */
  rowExtra?: (agent: Agent) => ReactNode;
}

type UsedFilter = "all" | "used" | "unused";

/** 보기·접힘 기억 키(`ac.list.view.<listId>`) */
const LIST_ID = "agents";
/** 행을 묶음 머리로 끌 때 쓰는 dataTransfer 형식 */
const DRAG_TYPE = "application/x-agent-console-item";

/** 에이전트별 사용 팀 수(`GET /agents/{id}/usages`)를 행마다 조회한다. 목록 키(`list`) 아래라 쓰기 뒤 같이 갱신된다. */
export function useAgentUsageCounts(agents: readonly Agent[], enabled = true): (id: string) => number | undefined {
  const { rest } = useApi();
  const results = useQueries({
    queries: agents.map((a) => ({ queryKey: ["list", "agent-usages", a.id], queryFn: () => rest.listAgentUsages(a.id), staleTime: 30_000, enabled })),
  });
  const counts = new Map(agents.map((a, i) => [a.id, results[i]?.data?.length] as const));
  return (id) => counts.get(id);
}

/** 에이전트 목록 패널: 검색·사용 여부 필터·정렬(이름순)·키보드 이동. 데이터와 콜백은 props. */
export function AgentList({ agents, loading, error, onRetry, selectedId, onSelect, onNew, onRename, onDelete, scopeBar, rowExtra }: AgentListProps) {
  const [query, setQuery] = useState("");
  const [used, setUsed] = useState<UsedFilter>("all");
  const root = useRef<HTMLDivElement>(null);
  const all = useMemo(() => agents ?? [], [agents]);
  const [moving, setMoving] = useState<Agent | undefined>(undefined);
  const [labeling, setLabeling] = useState<Agent | undefined>(undefined);
  const edits = useAgentEdits();
  // 사용처(어느 팀 구성이 쓰는지)는 정의-팀 연동이 켜져 있을 때만 있다. 꺼졌으면 사용 여부 필터·배지가 없다.
  const usagePart = useLinkPart(LINK_PART_IDS.agentsUsagesPanel);
  const usage = useAgentUsageCounts(all, usagePart.visible);
  const filtered = filterAgents(all, query, usagePart.visible ? used : "all", usage);
  // 묶는 기준·정렬은 데이터다. 속성 키는 보기 상태가 쥔다.
  const sortDefs = useMemo(() => agentSortDefs(usagePart.visible ? usage : undefined), [usagePart.visible, usage]);
  const view = useListView<Agent>({
    listId: LIST_ID,
    items: filtered,
    groupDefs: (attrKey) => agentGroupDefs({ attrKey, roleReason: t.arrange.roleDistinct }),
    sortDefs,
    defaultView: { groupBy: "folder", sort: "name" },
    messages: t.arrange,
    searching: query.trim() !== "",
    selectedId,
    idOf: (a) => a.id,
    showMenu: !(all.length === 0 || loading),
    attributeKeys: attributeKeys(all),
  });
  const { arranged } = view;
  const rows = arranged.sorted;
  const folderGrouping = arranged.groupDef?.id === "folder" && arranged.groups !== undefined;
  const targetId = (): string | undefined => document.activeElement?.closest<HTMLElement>("[data-row-id]")?.dataset["rowId"] ?? selectedId;
  const targetAgent = (): Agent | undefined => all.find((a) => a.id === targetId());

  useListShortcuts({
    scope: "agents",
    onNew,
    onSearch: () => root.current?.querySelector<HTMLInputElement>('input[type="search"]')?.focus(),
    onView: view.openMenu,
    onMove: () => setMoving(targetAgent()),
    onLabels: () => setLabeling(targetAgent()),
    ...(selectedId === undefined ? {} : { onRename: () => onRename(selectedId), onDelete: () => onDelete(selectedId) }),
  });

  const empty = (agents ?? []).length === 0 ? (
    <EmptyState
      icon={routeIconNode(ROUTE_ROLES.agent)}
      title={t.list.empty}
      description={t.list.emptyBody}
      action={<Button variant="primary" onClick={onNew}>{t.list.new}</Button>}
    />
  ) : (
    <p className="app-muted app-pad">{t.list.noMatch}</p>
  );

  return (
    <div ref={root} className="lib-split-list">
      {scopeBar}
      {usagePart.visible ? (
        <div className="lib-list-toolbar" role="group" aria-label={t.list.filterLabel}>
          {(["all", "used", "unused"] as const).map((f) => (
            <button key={f} type="button" className="lib-chip" aria-pressed={used === f} onClick={() => setUsed(f)}>
              {{ all: t.list.filterAll, used: t.list.filterUsed, unused: t.list.filterUnused }[f]}
            </button>
          ))}
        </div>
      ) : null}
      <ListPane<Agent>
        items={rows}
        {...(view.paneGroups === undefined ? {} : { groups: view.paneGroups, onToggleGroup: arranged.toggle })}
        {...(folderGrouping
          ? {
              onGroupDrop: (key: string, data: DataTransfer) => {
                const agent = all.find((a) => a.id === data.getData(DRAG_TYPE));
                const folder = key === NONE_KEY ? undefined : key;
                if (agent !== undefined && folderOf(agent.attributes) !== folder) void edits.moveToFolder(agent.id, agent.name, folder);
              },
            }
          : {})}
        belowTop={view.menu ?? undefined}
        selectedId={selectedId}
        onSelect={(id) => onSelect(id)}
        rowHeight={56}
        searchValue={query}
        onSearchChange={setQuery}
        toolbar={<Button variant="primary" size="sm" onClick={onNew} title="N">+ {t.list.new}</Button>}
        loading={loading ? <Skeleton rows={6} /> : undefined}
        error={error ? <ErrorBlock title={t.list.loadFailed} message={error.message} retryLabel={libraryMessages.retry} onRetry={onRetry} /> : undefined}
        empty={empty}
        messages={{ listLabel: t.list.label, searchLabel: t.list.search, searchPlaceholder: t.list.searchPlaceholder }}
        renderItem={(a) => {
          const n = usage(a.id);
          const summary = [a.backend, a.model].filter(Boolean).join(" · ");
          return (
            <span
              className="lib-row"
              {...(folderGrouping
                ? { draggable: true, onDragStart: (e: React.DragEvent) => { e.dataTransfer.setData(DRAG_TYPE, a.id); e.dataTransfer.effectAllowed = "move"; } }
                : {})}
            >
              <span className="lib-row-main">
                {rowExtra?.(a)}
                <span className="lib-row-name ac-ellipsis" title={a.name}>{a.name}</span>
              </span>
              <span className="lib-row-sub ac-ellipsis">{[a.role, summary, n === undefined ? "" : t.list.usageText(n)].filter(Boolean).join(" · ")}</span>
            </span>
          );
        }}
      />
      <ListEditDialogs<Agent> moving={moving} labeling={labeling} onCloseMove={() => setMoving(undefined)} onCloseLabels={() => setLabeling(undefined)} items={all} edits={edits} messages={t.arrange} />
    </div>
  );
}
