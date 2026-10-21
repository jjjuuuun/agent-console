import { useState, type KeyboardEvent, type ReactNode } from "react";
import type { ConversationSummary } from "@agent-console/contracts";
import { Button, ListPane, StatusIcon } from "@agent-console/ui";
import { messages as appMessages } from "../../app/messages";
import { formatRelative } from "../../lib/format";
import { ActionMenu, type ActionMenuItem } from "./ActionMenu";
import { chatMessages } from "./chatMessages";

const t = chatMessages.list;

export interface ConversationListProps {
  /** 정렬·검색·보관 필터가 끝난 목록 */
  conversations: readonly ConversationSummary[];
  /** 필터 전 전체 수(빈 상태 문구 구분용) */
  totalCount: number;
  selectedId?: string;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  query: string;
  onQueryChange: (query: string) => void;
  includeArchived: boolean;
  onIncludeArchivedChange: (value: boolean) => void;
  /** 팀 구성 이름. 모르면(삭제됨 또는 로딩 중) undefined */
  teamName: (graphId: string) => string | undefined;
  /** 현재 시각(ms) — 상대 시간 표시용. 호출자가 주입한다 */
  nowMs: number;
  onSelect: (id: string) => void;
  onNew: () => void;
  onRename: (c: ConversationSummary) => void;
  onToggleArchive: (c: ConversationSummary) => void;
  onDelete: (c: ConversationSummary) => void;
  onOpenTeam: (c: ConversationSummary) => void;
  /** 목록 위쪽 추가 슬롯 */
  header?: ReactNode;
}

function statusOf(c: ConversationSummary): { status: string; label: string } | null {
  if ((c.pending_interactions ?? 0) > 0) return { status: "waiting", label: t.status["waiting"] ?? "waiting" };
  const s = c.last_status;
  if (s === "running" || s === "failed" || s === "interrupted" || s === "queued" || s === "waiting") return { status: s, label: t.status[s] ?? s };
  return null;
}

/**
 * 대화 목록 패널(표현 전용). 상태 아이콘·응답 대기 칩·행 메뉴·검색·보관 필터.
 * 키: `↑↓ Enter`(ListPane), `N` 새 대화, `F2` 이름 바꾸기, `Delete` 삭제, `Shift+F10` 행 메뉴, `/` 검색.
 */
export function ConversationList(props: ConversationListProps) {
  const { conversations, selectedId, query } = props;
  const [menuFor, setMenuFor] = useState<string | null>(null);

  const byId = (id: string | undefined) => conversations.find((c) => c.id === id);
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    const typing = target.matches("input, textarea, select, [contenteditable]");
    const row = byId(target.closest<HTMLElement>("[data-row-id]")?.dataset["rowId"]);
    if (e.key === "/" && !typing) {
      e.preventDefault();
      e.currentTarget.querySelector<HTMLElement>(".ac-listpane-search")?.focus();
    } else if (e.key === "F10" && e.shiftKey && row) {
      e.preventDefault();
      setMenuFor(row.id);
    } else if (typing || e.ctrlKey || e.metaKey || e.altKey) {
      return;
    } else if ((e.key === "n" || e.key === "N") && !e.shiftKey) {
      e.preventDefault();
      props.onNew();
    } else if (e.key === "F2" && row) {
      e.preventDefault();
      props.onRename(row);
    } else if (e.key === "Delete" && row) {
      e.preventDefault();
      props.onDelete(row);
    }
  };

  const menuItems = (c: ConversationSummary): ActionMenuItem[] => [
    { id: "rename", label: chatMessages.menu.rename, onSelect: () => props.onRename(c) },
    { id: "archive", label: c.archived ? chatMessages.menu.unarchive : chatMessages.menu.archive, onSelect: () => props.onToggleArchive(c) },
    { id: "open-team", label: chatMessages.menu.openTeam, onSelect: () => props.onOpenTeam(c), disabled: props.teamName(c.graph_id) === undefined },
    { id: "delete", label: chatMessages.menu.delete, onSelect: () => props.onDelete(c), danger: true },
  ];

  const empty = (
    <div className="chat-list-empty">
      {query.trim() !== "" ? (
        <>
          <p>{t.noResults(query.trim())}</p>
          <Button size="sm" onClick={() => props.onQueryChange("")}>{t.clearSearch}</Button>
        </>
      ) : (
        // 새 대화 단추는 목록 머리의 것 하나뿐이다(중복 제거, 5.2R.21)
        <p>{t.empty}</p>
      )}
    </div>
  );

  return (
    <div className="chat-list" onKeyDown={onKeyDown}>
      <div className="chat-list-head">
        <Button variant="primary" onClick={props.onNew} title="N">{`+ ${t.new}`}</Button>
        <label className="app-check">
          <input type="checkbox" checked={props.includeArchived} onChange={(e) => props.onIncludeArchivedChange(e.target.checked)} />
          {t.includeArchived}
        </label>
        {props.header}
      </div>
      <ListPane
        items={conversations}
        selectedId={selectedId}
        onSelect={(id) => props.onSelect(id)}
        rowHeight={56}
        searchValue={query}
        onSearchChange={props.onQueryChange}
        messages={{ listLabel: t.label, searchLabel: t.searchLabel, searchPlaceholder: t.searchPlaceholder }}
        {...(props.loading ? { loading: <ListSkeleton /> } : {})}
        {...(props.error ? { error: <ListError message={props.error} onRetry={props.onRetry} /> } : {})}
        empty={empty}
        renderItem={(c) => {
          const status = statusOf(c);
          const title = c.title || t.untitled;
          const team = props.teamName(c.graph_id);
          const waiting = c.pending_interactions ?? 0;
          return (
            <div className="chat-row" data-archived={c.archived ? "true" : undefined} data-waiting={waiting > 0 ? "true" : undefined}>
              <div className="chat-row-main">
                <div className="chat-row-line">
                  <span className="chat-row-icon">
                    {status ? <StatusIcon status={status.status} kind={status.status === "waiting" ? "node" : "run"} size={14} label={status.label} /> : null}
                  </span>
                  <span className="chat-row-title ac-ellipsis" title={title}>{title}</span>
                  <span className="chat-row-time app-muted">{formatRelative(c.updated_at, props.nowMs)}</span>
                </div>
                <div className="chat-row-line chat-row-sub app-muted">
                  <span className="ac-ellipsis" title={team ?? t.deletedTeam} data-deleted-team={team === undefined ? "true" : undefined}>{team ?? t.deletedTeam}</span>
                  {waiting > 0 ? <span className="chat-chip" data-tone="waiting">⏸ {t.waitingChip(waiting)}</span> : null}
                  {(c.held ?? 0) > 0 ? <span className="chat-chip" data-tone="waiting">⏸ {t.heldChip(c.held ?? 0)}</span> : null}
                  {(c.queued ?? 0) - (c.held ?? 0) > 0 ? <span className="chat-chip">{t.queuedChip((c.queued ?? 0) - (c.held ?? 0))}</span> : null}
                  {c.archived ? <span className="chat-chip">{t.archivedChip}</span> : null}
                </div>
              </div>
              <ActionMenu label={t.rowMenu(title)} items={menuItems(c)} size="sm" open={menuFor === c.id} onOpenChange={(open) => setMenuFor(open ? c.id : null)} />
            </div>
          );
        }}
      />
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="app-skeleton" aria-hidden="true">
      {Array.from({ length: 6 }, (_, i) => <div key={i} className="app-skeleton-row" style={{ height: 40 }} />)}
    </div>
  );
}

function ListError({ message, onRetry }: { message: string; onRetry?: (() => void) | undefined }) {
  return (
    <div className="chat-list-empty">
      <p>{message}</p>
      {onRetry ? <Button size="sm" onClick={onRetry}>{appMessages.common.retry}</Button> : null}
    </div>
  );
}
