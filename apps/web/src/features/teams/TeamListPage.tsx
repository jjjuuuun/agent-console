import { useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import type { GraphSummary } from "@agent-console/contracts";
import { Button, EmptyState, Icon, PageHeader, StatusChip } from "@agent-console/ui";
import { useApi } from "../../app/ApiContext";
import { ErrorBlock } from "../../app/ErrorBlock";
import { describeError } from "../../app/errors";
import { messages as m } from "../../app/messages";
import { useApiQuery } from "../../app/queries";
import { formatDateTime, formatDuration, formatRelative } from "../../lib/format";
import { useNow } from "../../app/useNow";
import { Skeleton, useEdgeTypes } from "../settings";
import { ActionMenu, type ActionMenuHandle, useGraphList, useInvalidateLists, useNodeTypes, DeleteDialog, DEFINITION_KINDS, definitionKey, libraryMessages as lm, routePath, ROUTE_ROLES, useListShortcuts } from "../library";
import { useRegisterCommands } from "../../shell/commands";
import { StartGuide } from "../start";
import { useScopedList } from "../projects";
import { ExportDialog, exportMessages } from "../exports";
import { DuplicateTeamDialog, NewTeamDialog, RenameTeamDialog, useStartChat } from "./TeamDialogs";
import { teamMessages as t } from "./messages";
import { summarizeEntries } from "./teamsLogic";
import { LINK_PART_IDS, useLinkPart } from "../../modules";
import { blocksRun, ValidationChip } from "./ValidationChip";
import "./teams.css";

const scopeOfGraph = (g: GraphSummary) => g.project;
const idOfGraph = (g: GraphSummary) => g.id;
const nameOfGraph = (g: GraphSummary) => g.name;

type SortKey = "name" | "modified";
type Dialog = { kind: "new" } | { kind: "rename" | "duplicate" | "export" | "delete"; graph: GraphSummary } | null;

/** 행의 "최근 사용" 칸: 이 팀 구성의 가장 최근 실행(행이 보일 때 지연 조회, 실패해도 행은 유지). */
function LastRunCell({ graphId }: { graphId: string }) {
  const q = useApiQuery(["list", "graph-last-run", graphId], (rest) => rest.listRuns({ graph_id: graphId, limit: 1 }), { retry: false });
  const run = q.data?.[0];
  if (run === undefined) return <span className="app-muted">{t.list.noRun}</span>;
  const ms = run.ended_at != null && run.started_at != null ? (run.ended_at - run.started_at) * 1000 : undefined;
  return (
    <Link to={`${routePath(ROUTE_ROLES.runs)}/${encodeURIComponent(run.id)}`} className="team-lastrun" onClick={(e) => e.stopPropagation()}>
      <StatusChip status={run.status} kind="run" label={m.runStatus[run.status] ?? run.status} />
      {ms === undefined ? null : <span className="app-muted">{formatDuration(ms)}</span>}
    </Link>
  );
}

function DeleteTeam({ graph, onClose, onDone }: { graph: GraphSummary; onClose: () => void; onDone: () => void }) {
  const { rest } = useApi();
  const queryClient = useQueryClient();
  const invalidate = useInvalidateLists();
  const convs = useApiQuery(["list", "conversations", { graph_id: graph.id }], (r) => r.listConversations({ graph_id: graph.id }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const n = convs.data?.length ?? 0;
  return (
    <DeleteDialog
      open
      name={graph.name}
      {...(n > 0 ? { note: t.delete.conversations(n) } : {})}
      busy={busy}
      error={error}
      onCancel={onClose}
      onConfirm={() => {
        setBusy(true);
        rest
          .deleteGraph(graph.id)
          .then(async () => {
            queryClient.removeQueries({ queryKey: definitionKey(DEFINITION_KINDS.graph, graph.id) });
            await invalidate();
            onDone();
          })
          .catch((e: unknown) => setError(describeError(e, t.delete.failed).message))
          .finally(() => setBusy(false));
      }}
    />
  );
}

/** 팀 구성 목록(`/teams`): 만들기·복제·이름 바꾸기·삭제·버전 목록·이 팀으로 대화 시작. 표는 `role=grid`이고 방향키로 움직인다. */
export function TeamListPage({ basePath }: { basePath: string }) {
  const navigate = useNavigate();
  // 검증 요약은 팀 검증 연동이 켜져 있을 때만 있다. 꺼졌으면 칩이 없고 모든 팀 구성을 같은 모양으로 보인다.
  const validationPart = useLinkPart(LINK_PART_IDS.teamsValidationColumn);
  const graphs = useGraphList();
  const nodeTypes = useNodeTypes();
  const edgeTypes = useEdgeTypes();
  const now = useNow(true, 30_000);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({ key: "modified", dir: "desc" });
  // 편집기 팔레트의 [팀 구성 만들기]가 `?new=1`로 들어오면 새 팀 구성 다이얼로그를 바로 연다
  const [params] = useSearchParams();
  const [dialog, setDialog] = useState<Dialog>(() => (params.get("new") === "1" ? { kind: "new" } : null));
  const [activeId, setActiveId] = useState<string | undefined>(undefined);
  const searchRef = useRef<HTMLInputElement>(null);
  const menus = useRef(new Map<string, ActionMenuHandle>());
  const scoped = useScopedList(graphs.data, { scopeOf: scopeOfGraph, kind: DEFINITION_KINDS.graph, idOf: idOfGraph, nameOf: nameOfGraph });
  const chat = useStartChat((id) => void navigate(`${routePath(ROUTE_ROLES.conversations)}/${encodeURIComponent(id)}`));

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = (scoped.items ?? []).filter((g) => q === "" || `${g.name} ${g.description ?? ""} ${g.id}`.toLowerCase().includes(q));
    const sign = sort.dir === "asc" ? 1 : -1;
    return [...list].sort((a, b) => (sort.key === "name" ? a.name.localeCompare(b.name, "ko") : (a.saved_at ?? 0) - (b.saved_at ?? 0)) * sign);
  }, [scoped.items, query, sort]);

  const open = (id: string) => void navigate(`${basePath}/${encodeURIComponent(id)}`);
  // 선택 모드에서는 행을 열지 않고 선택을 토글한다
  const openRow = (id: string) => {
    if (!scoped.intercept(id)) open(id);
  };
  const hasEntry = (g: GraphSummary) => (g.entry_labels ?? []).length > 0 && !(validationPart.visible && blocksRun(g.validation));
  const startChat = (g: GraphSummary) => {
    if (hasEntry(g)) void chat.start(g.id);
  };
  const active = (graphs.data ?? []).find((g) => g.id === activeId);

  useRegisterCommands([{ id: "teams.new", titleKey: "palette.actions.libTeamNew", run: () => setDialog({ kind: "new" }) }]);
  useListShortcuts({
    scope: "teams",
    onNew: () => setDialog({ kind: "new" }),
    onSearch: () => searchRef.current?.focus(),
    ...(active === undefined ? {} : { onRename: () => setDialog({ kind: "rename", graph: active }), onDelete: () => setDialog({ kind: "delete", graph: active }), onStartChat: () => startChat(active) }),
  });

  const onRowKey = (e: KeyboardEvent<HTMLTableRowElement>, g: GraphSummary, index: number) => {
    // Enter는 행 안의 글자 칸에서도 열린다. 링크·버튼·입력은 자기 동작을 따른다.
    const interactive = e.target instanceof HTMLElement && e.target !== e.currentTarget && e.target.closest("a, button, input, select, textarea, [role=menuitem]") !== null;
    if (interactive || (e.target !== e.currentTarget && e.key !== "Enter")) return;
    const rowEls = e.currentTarget.parentElement?.querySelectorAll<HTMLElement>("tr[data-row-id]");
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      rowEls?.[index + (e.key === "ArrowDown" ? 1 : -1)]?.focus();
    } else if (e.key === "Enter" && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      openRow(g.id);
    } else if (e.key === "F10" && e.shiftKey) {
      e.preventDefault();
      menus.current.get(g.id)?.open();
    }
  };

  const toggleSort = (key: SortKey) => setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: key === "name" ? "asc" : "desc" }));
  const ariaSort = (key: SortKey) => (sort.key === key ? (sort.dir === "asc" ? "ascending" : "descending") : "none");
  const list = graphs.data ?? [];

  let body;
  if (graphs.isLoading) {
    body = <Skeleton rows={6} />;
  } else if (graphs.isError) {
    body = <ErrorBlock title={t.list.loadFailed} message={graphs.error.message} retryLabel={lm.retry} onRetry={() => void graphs.refetch()} />;
  } else if (list.length === 0) {
    body = (
      <EmptyState
        icon={<Icon name="teams" size={24} />}
        title={t.list.empty}
        description={t.list.emptyBody}
        action={<Button variant="primary" size="lg" onClick={() => setDialog({ kind: "new" })}>{t.list.new}</Button>}
        secondaryAction={<StartGuide actionOverrides={{ create: () => setDialog({ kind: "new" }) }} />}
      />
    );
  } else if (rows.length === 0) {
    body = (
      <EmptyState title={t.list.noMatch(query)} action={<Button onClick={() => setQuery("")}>{t.list.clearSearch}</Button>} />
    );
  } else {
    body = (
      <div className="lib-table-wrap">
        <table className="lib-grid" role="grid" aria-label={t.list.tableLabel}>
          <thead>
            <tr>
              <th scope="col" aria-sort={ariaSort("name")}>
                <button type="button" onClick={() => toggleSort("name")} aria-label={t.list.sortBy(t.list.colName)}>
                  {t.list.colName} {sort.key === "name" ? (sort.dir === "asc" ? "▲" : "▼") : ""}
                </button>
              </th>
              <th scope="col">{t.list.colDescription}</th>
              <th scope="col">{t.list.colNodes}</th>
              <th scope="col">{t.list.colEntry}</th>
              <th scope="col" aria-sort={ariaSort("modified")}>
                <button type="button" onClick={() => toggleSort("modified")} aria-label={t.list.sortBy(t.list.colModified)}>
                  {t.list.colModified} {sort.key === "modified" ? (sort.dir === "asc" ? "▲" : "▼") : ""}
                </button>
              </th>
              <th scope="col">{t.list.colLastRun}</th>
              <th scope="col" aria-label={t.list.rowMenu} />
            </tr>
          </thead>
          <tbody>
            {rows.map((g, i) => {
              const entry = summarizeEntries(g.entry_labels, t.list.entryMore);
              return (
                <tr
                  key={g.id}
                  role="row"
                  data-row-id={g.id}
                  data-active={activeId === g.id ? "true" : undefined}
                  aria-selected={activeId === g.id}
                  tabIndex={i === 0 && activeId === undefined ? 0 : activeId === g.id ? 0 : -1}
                  onFocus={(e) => e.target === e.currentTarget && setActiveId(g.id)}
                  onKeyDown={(e) => onRowKey(e, g, i)}
                  onDoubleClick={() => openRow(g.id)}
                >
                  <td className="lib-cell-clip team-name">
                    <div className="team-name-line">
                      <Link to={`${basePath}/${encodeURIComponent(g.id)}`} className="ac-ellipsis team-name-link" title={g.name} onClick={(e) => { if (scoped.intercept(g.id)) e.preventDefault(); }}>{g.name}</Link>
                      {scoped.rowExtra(g)}
                      <Link to={`${basePath}/${encodeURIComponent(g.id)}`} className="team-vchip-link" onClick={(e) => e.stopPropagation()}>{validationPart.visible ? <ValidationChip summary={g.validation} /> : null}</Link>
                    </div>
                  </td>
                  <td className="lib-cell-clip app-muted" title={g.description}>{g.description ?? ""}</td>
                  <td className="ac-num">{g.node_count}</td>
                  <td className="lib-cell-clip">
                    {entry === undefined ? (
                      <span className="app-sev" data-severity="warning">▲ {t.list.noEntry}</span>
                    ) : (
                      <span title={(g.entry_labels ?? []).join(", ")}>{entry}</span>
                    )}
                  </td>
                  <td title={formatDateTime(g.saved_at)}>{formatRelative(g.saved_at, now)}</td>
                  <td><LastRunCell graphId={g.id} /></td>
                  <td className="lib-cell-actions">
                    <ActionMenu
                      ref={(h) => {
                        if (h) menus.current.set(g.id, h);
                        return () => {
                          menus.current.delete(g.id);
                        };
                      }}
                      label={`${g.name} ${t.list.rowMenu}`}
                      items={[
                        { id: "open", label: t.list.open, onSelect: () => open(g.id) },
                        { id: "chat", label: t.list.startChat, disabled: !hasEntry(g), ...(hasEntry(g) ? {} : { title: t.list.startChatNoEntry }), onSelect: () => startChat(g) },
                        { id: "rename", label: t.list.rename, onSelect: () => setDialog({ kind: "rename", graph: g }) },
                        { id: "duplicate", label: t.list.duplicate, onSelect: () => setDialog({ kind: "duplicate", graph: g }) },
                        { id: "export", label: exportMessages.menu, onSelect: () => setDialog({ kind: "export", graph: g }) },
                        { id: "versions", label: t.list.versions, onSelect: () => void navigate(`${basePath}/${encodeURIComponent(g.id)}?tab=versions`) },
                        { id: "delete", label: t.list.delete, danger: true, onSelect: () => setDialog({ kind: "delete", graph: g }) },
                      ]}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="app-muted lib-field-note team-total">{t.list.total(rows.length)}</p>
      </div>
    );
  }

  return (
    <div className="app-screen-frame" data-screen="teams">
      <PageHeader
        title={m.nav.teams}
        actions={
          <>
            <input ref={searchRef} type="search" className="ac-input team-search" aria-label={t.list.search} placeholder={t.list.searchPlaceholder} value={query} onChange={(e) => setQuery(e.target.value)} />
            <Button variant="primary" onClick={() => setDialog({ kind: "new" })} title="N">+ {t.list.new}</Button>
          </>
        }
      />
      <div className="app-screen-body">
        {scoped.bar}
        {chat.error ? <p className="app-sev" data-severity="error" role="alert">{chat.error}</p> : null}
        {body}
      </div>
      {dialog?.kind === "new" ? (
        <NewTeamDialog graphs={list} nodeTypes={nodeTypes.data ?? []} edgeTypes={edgeTypes.data ?? []} onClose={() => setDialog(null)} onCreated={(id) => { setDialog(null); open(id); }} />
      ) : null}
      {scoped.dialog}
      {dialog?.kind === "rename" ? <RenameTeamDialog graph={dialog.graph} onClose={() => setDialog(null)} onDone={() => setDialog(null)} /> : null}
      {dialog?.kind === "duplicate" ? (
        <DuplicateTeamDialog sourceId={dialog.graph.id} sourceName={dialog.graph.name} existingIds={new Set(list.map((g) => g.id))} onClose={() => setDialog(null)} onCreated={(id) => { setDialog(null); open(id); }} />
      ) : null}
      {dialog?.kind === "export" && DEFINITION_KINDS.graph !== undefined ? <ExportDialog initialItems={[{ kind: DEFINITION_KINDS.graph, id: dialog.graph.id }]} onClose={() => setDialog(null)} /> : null}
      {dialog?.kind === "delete" ? <DeleteTeam graph={dialog.graph} onClose={() => setDialog(null)} onDone={() => setDialog(null)} /> : null}
    </div>
  );
}
