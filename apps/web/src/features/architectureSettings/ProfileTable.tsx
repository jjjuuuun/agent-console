import { useMemo, useState } from "react";
import type { GroupByDef, SortDef } from "@agent-console/list-arrange";
import { byNumber, byText } from "@agent-console/list-arrange";
import { Badge, Button, GroupHeader, Tooltip } from "@agent-console/ui";
import { useListView } from "../library";
import { ORIGIN, archSettingsMessages as t } from "./messages";
import type { ProfileRow } from "./profileLogic";

export type RowAction = "view" | "edit" | "clone" | "disable" | "enable" | "remove" | "revert";

export interface ProfileTableProps {
  rows: readonly ProfileRow[];
  disabledRows: readonly ProfileRow[];
  /** 편집기가 열려 있는 행 id */
  openId: string | null;
  onAction: (action: RowAction, row: ProfileRow) => void;
  disabled?: boolean;
}

/** 출처 값을 사람이 읽는 이름으로. 모르는 값은 원문. */
export function originLabel(row: Pick<ProfileRow, "origin" | "overrides">): string {
  if (row.origin === ORIGIN.user) return row.overrides === undefined ? t.origin.user : t.origin.userOverride;
  if (row.origin === ORIGIN.default) return t.origin.default;
  if (row.origin.startsWith(ORIGIN.pluginPrefix)) return t.origin.plugin(row.origin.slice(ORIGIN.pluginPrefix.length));
  return row.origin;
}

/** 행 상태 -> 행 동작 목록(명세 7.3). */
export function actionsOf(row: ProfileRow): RowAction[] {
  if (row.disabled) return ["enable"];
  if (row.origin !== ORIGIN.user) return ["view", "clone", "disable"];
  return row.overrides === undefined ? ["edit", "clone", "remove"] : ["edit", "revert"];
}

const groupDefs: GroupByDef<ProfileRow>[] = [{ id: "origin", titleKey: "group.origin", read: (r) => [originLabel(r)] }];
const sortDefs: SortDef<ProfileRow>[] = [
  { id: "title", titleKey: "sort.title", compare: byText<ProfileRow>((r) => r.title) },
  { id: "issues", titleKey: "sort.issues", compare: (a, b) => byNumber<ProfileRow>((r) => r.issues ?? 0, true)(a, b) || byText<ProfileRow>((r) => r.title)(a, b), available: (items) => items.some((r) => (r.issues ?? 0) > 0) },
];

function Row({ row, open, onAction, disabled }: { row: ProfileRow; open: boolean; onAction: ProfileTableProps["onAction"]; disabled: boolean | undefined }) {
  const acts = actionsOf(row);
  return (
    <li className="arch-settings-row" data-row-id={row.id} data-open={open ? "true" : undefined}>
      <span className="arch-settings-row-main">
        {row.dirty ? <span className="arch-settings-dot" role="img" aria-label={t.list.unsaved} title={t.list.unsaved} /> : null}
        <span className="arch-settings-row-title ac-ellipsis" title={row.title}>{row.title}</span>
        <span className="arch-settings-row-id ac-ellipsis" title={row.id}>{row.id}</span>
        <Badge className="arch-settings-origin">{originLabel(row)}</Badge>
      </span>
      <span className="arch-settings-row-meta">
        {row.issues === null ? (
          <Tooltip content={row.dirty ? t.list.unknownCounts : t.list.notInList} placement="top" align="start">
            <span className="app-muted" tabIndex={0} role="img" aria-label={row.dirty ? t.list.unknownCounts : t.list.notInList}>—</span>
          </Tooltip>
        ) : row.issues > 0 ? (
          <span className="arch-settings-issues-count"><span className="app-sev" data-severity="warning" aria-hidden="true">⚠</span> {t.list.issues(row.issues)}</span>
        ) : (
          <span className="app-muted">{t.list.noIssues}</span>
        )}
        {row.cells === null || row.edges === null ? null : <span className="app-muted">{t.list.counts(row.cells, row.edges)}</span>}
      </span>
      <span className="arch-settings-row-actions" role="group" aria-label={t.list.actionsFor(row.title)}>
        {acts.map((a) => (
          <Button key={a} size="sm" variant={a === "remove" ? "danger" : "secondary"} disabled={disabled === true} onClick={() => onAction(a, row)}>
            {t.list[a]}
          </Button>
        ))}
      </span>
    </li>
  );
}

/**
 * 프로필 목록(표현 전용): 묶기·정렬은 `useListView`(라이브러리 공용 보기 메뉴)를 쓴다. 기본은 묶지 않음.
 * 끈 프로필은 목록 아래 접힌 줄에 모인다.
 */
export function ProfileTable({ rows, disabledRows, openId, onAction, disabled }: ProfileTableProps) {
  const [showDisabled, setShowDisabled] = useState(false);
  const items = useMemo(() => [...rows], [rows]);
  const view = useListView<ProfileRow>({
    listId: "architecture-profiles",
    items,
    groupDefs,
    sortDefs,
    defaultView: { groupBy: "none", sort: "title" },
    messages: t.arrange,
    searching: false,
    idOf: (r) => r.id,
    showMenu: rows.length > 1,
  });
  const body = view.paneGroups === undefined ? view.arranged.sorted : null;
  return (
    <div className="arch-settings-table">
      {view.menu}
      {body !== null ? (
        <ul className="arch-settings-rows" aria-label={t.list.label}>
          {body.map((r) => <Row key={r.id} row={r} open={openId === r.id} onAction={onAction} disabled={disabled} />)}
        </ul>
      ) : (
        <div className="arch-settings-groups">
          {view.paneGroups?.map((g) => (
            <div key={g.key} className="arch-settings-group">
              <GroupHeader label={g.label} count={g.count} depth={g.depth} collapsed={g.collapsed} onToggle={() => view.arranged.toggle(g.key, !g.collapsed)} />
              {g.collapsed ? null : (
                <ul className="arch-settings-rows" aria-label={g.label}>
                  {g.items.map((r) => <Row key={r.id} row={r} open={openId === r.id} onAction={onAction} disabled={disabled} />)}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
      {disabledRows.length === 0 ? null : (
        <div className="arch-settings-disabled">
          <Button size="sm" variant="ghost" aria-expanded={showDisabled} onClick={() => setShowDisabled(!showDisabled)}>
            {t.list.disabledTitle(disabledRows.length)} {showDisabled ? "▴" : "▾"}
          </Button>
          {showDisabled ? (
            <ul className="arch-settings-rows" aria-label={t.list.disabledTitle(disabledRows.length)}>
              {disabledRows.map((r) => <Row key={r.id} row={r} open={false} onAction={onAction} disabled={disabled} />)}
            </ul>
          ) : null}
        </div>
      )}
    </div>
  );
}
