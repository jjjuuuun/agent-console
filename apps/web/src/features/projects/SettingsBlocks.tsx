import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { Link } from "react-router";
import { Banner, Button, Disclosure, Icon, Menu, Popover, Tag, type MenuItemDef } from "@agent-console/ui";
import { useState } from "react";
import { scopeMessages } from "./scopeMessages";

const t = scopeMessages.settings;

/** 좁은 화면(컨테이너 640px 미만)에서 행 동작을 접는 `⋯` 메뉴. 넓은 화면에서는 CSS가 숨긴다. */
function RowMenu({ label, items }: { label: string; items: readonly MenuItemDef[] }) {
  const [open, setOpen] = useState(false);
  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      panelRole="menu"
      panelLabel={label}
      align="end"
      className="prj-row-menu"
      renderTrigger={(trigger) => (
        <button type="button" {...trigger} className="ac-btn ac-icon-btn" data-variant="ghost" data-size="sm" aria-label={label} title={label}>
          <Icon name="more" size={16} />
        </button>
      )}
    >
      <Menu items={items} onClose={() => setOpen(false)} />
    </Popover>
  );
}

export interface ProjectRow {
  id: string;
  name: string;
  folder: string;
  /** 홈 주소 */
  href: string;
  /** 상태 글자(정상이면 undefined 대신 plain=true) */
  statusLabel: string;
  statusTone: string;
  plain: boolean;
}

export interface ProjectsTableProps {
  rows: readonly ProjectRow[];
  onRepath: (id: string) => void;
  onUnregister: (id: string) => void;
}

/** 등록된 프로젝트 표(screen-projects §8.1): 이름(홈 링크)·폴더·상태·동작. `↑↓`로 행의 링크 사이를 옮긴다. 표현 전용. */
export function ProjectsTable({ rows, onRepath, onUnregister }: ProjectsTableProps) {
  const body = useRef<HTMLTableSectionElement>(null);
  const onKey = (e: KeyboardEvent<HTMLTableSectionElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const links = Array.from(body.current?.querySelectorAll<HTMLElement>("a[data-prj-row]") ?? []);
    const i = links.indexOf(document.activeElement as HTMLElement);
    if (i < 0) return;
    e.preventDefault();
    links[Math.min(links.length - 1, Math.max(0, i + (e.key === "ArrowDown" ? 1 : -1)))]?.focus();
  };
  return (
    <table className="prj-table" aria-label={t.listLabel}>
      <thead>
        <tr>
          <th scope="col" className="prj-col-name">{t.colName}</th>
          <th scope="col">{t.colPath}</th>
          <th scope="col" className="prj-col-status">{t.colStatus}</th>
          <th scope="col" className="prj-col-actions">{t.colActions}</th>
        </tr>
      </thead>
      <tbody ref={body} onKeyDown={onKey}>
        {rows.map((r) => (
          <tr key={r.id}>
            <td className="prj-col-name"><Link data-prj-row="" className="ac-ellipsis" to={r.href} title={r.name}>{r.name}</Link></td>
            <td><span className="prj-mono ac-ellipsis" title={r.folder}>{r.folder}</span></td>
            <td className="prj-col-status">
              {r.plain ? <span className="app-muted">{t.ok}</span> : <Tag data-tone={r.statusTone}>{r.statusLabel}</Tag>}
            </td>
            <td className="prj-col-actions">
              <span className="prj-row-actions prj-wide-only">
                <Button size="sm" variant="ghost" onClick={() => onRepath(r.id)} aria-label={`${t.repath}: ${r.name}`}>{t.repath}</Button>
                <Button size="sm" variant="ghost" onClick={() => onUnregister(r.id)} aria-label={`${t.unregister}: ${r.name}`}>{t.unregister}</Button>
              </span>
              <span className="prj-narrow-only">
                <RowMenu label={t.more(r.name)} items={[{ id: "repath", label: t.repath, onSelect: () => onRepath(r.id) }, { id: "unregister", label: t.unregister, onSelect: () => onUnregister(r.id) }]} />
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export interface ArchivedRow {
  id: string;
  name: string;
  folder: string;
  archivedAt: string | null;
  /** 앱에 저장된 기록 요약 문구(없으면 줄 없음) */
  stored: string | null;
  blocked?: string | undefined;
}

/** 등록 해제된 프로젝트(기본 접힘, 0개면 그리지 않는다). */
export function ArchivedProjects({ rows, busyId, onReregister, onView }: { rows: readonly ArchivedRow[]; busyId?: string | null | undefined; onReregister: (id: string) => void; onView: (id: string) => void }) {
  if (rows.length === 0) return null;
  return (
    <Disclosure summary={t.archived(rows.length)}>
      <table className="prj-table" aria-label={t.archived(rows.length)}>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td className="prj-col-name"><span className="ac-ellipsis" title={r.name}>{r.name}</span></td>
              <td>
                <span className="prj-mono ac-ellipsis" title={r.folder}>{r.folder}</span>
                {r.archivedAt === null ? null : <span className="app-muted prj-note"> {t.archivedAt(r.archivedAt)}</span>}
                {r.stored === null ? null : <span className="app-muted prj-note"> {r.stored}</span>}
                {r.blocked === undefined ? null : <span className="app-muted prj-note"> {r.blocked}</span>}
              </td>
              <td className="prj-col-actions">
                <span className="prj-row-actions">
                  <Button size="sm" variant="ghost" loading={busyId === r.id} aria-disabled={r.blocked !== undefined} title={r.blocked} onClick={() => r.blocked === undefined && onReregister(r.id)}>{t.reregister}</Button>
                  <Button size="sm" variant="ghost" onClick={() => onView(r.id)}>{t.viewHistory}</Button>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Disclosure>
  );
}

export interface LegacyRow {
  key: string;
  feature: string;
  count: number;
}

/** 프로젝트에 속하지 않은 이전 기록(screen-projects §8.3). 개수가 있는 행만 받는다. 행이 없으면 그리지 않는다. */
export function LegacyRecordsBlock({ rows, hiddenCount, onAssign, onKeep, onShowHidden }: { rows: readonly LegacyRow[]; hiddenCount: number; onAssign: (key: string) => void; onKeep: (key: string) => void; onShowHidden: () => void }) {
  if (rows.length === 0 && hiddenCount === 0) return null;
  return (
    <section className="prj-card" aria-labelledby="prj-legacy-title">
      <div className="prj-card-head">
        <h3 id="prj-legacy-title">{t.legacyTitle}</h3>
        {hiddenCount > 0 ? <Button size="sm" variant="ghost" onClick={onShowHidden}>{t.legacyShowHidden}</Button> : null}
      </div>
      {rows.length > 0 ? <p className="app-muted">{t.legacyDesc}</p> : null}
      {rows.length === 0 ? null : (
        <table className="prj-table" aria-labelledby="prj-legacy-title">
          <thead><tr><th scope="col">{t.colFeature}</th><th scope="col">{t.colCount}</th><th scope="col" className="prj-col-actions">{t.colActions}</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key}>
                <td>{r.feature}</td>
                <td>{t.legacyCount(r.count)}</td>
                <td className="prj-col-actions">
                  <span className="prj-row-actions">
                    <Button size="sm" variant="primary" onClick={() => onAssign(r.key)} aria-label={`${r.feature} ${t.legacyAssign}`}>{t.legacyAssign}</Button>
                    <Button size="sm" variant="ghost" onClick={() => onKeep(r.key)} aria-label={`${r.feature} ${t.legacyKeep}`}>{t.legacyKeep}</Button>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export interface CleanupRow {
  id: string;
  name: string;
  href: string;
  count: number;
  blocked?: string | undefined;
}

/** 옛 프로젝트 전용 구성 옮기기(screen-projects §8.4). 옮길 구성이 없으면 그리지 않는다. */
export function LegacyConfigBlock({ rows, orphans, onMove }: { rows: readonly CleanupRow[]; orphans: number; onMove: (id: string) => void }) {
  const total = rows.reduce((n, r) => n + r.count, 0) + orphans;
  if (total === 0) return null;
  return (
    <section className="prj-card" aria-labelledby="prj-cleanup-title">
      <h3 id="prj-cleanup-title">{t.cleanupTitle}</h3>
      <p className="app-muted">{t.cleanupDesc(total)}</p>
      {rows.length === 0 ? null : (
        <table className="prj-table" aria-labelledby="prj-cleanup-title">
          <thead><tr><th scope="col">{t.cleanupColProject}</th><th scope="col">{t.cleanupColCount}</th><th scope="col" className="prj-col-actions">{t.colActions}</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td><Link className="ac-ellipsis" to={r.href}>{r.name}</Link></td>
                <td>{r.count}</td>
                <td className="prj-col-actions">
                  <Button size="sm" aria-disabled={r.blocked !== undefined} title={r.blocked} onClick={() => r.blocked === undefined && onMove(r.id)} aria-label={`${r.name} ${t.cleanupMove}`}>{t.cleanupMove}</Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {orphans > 0 ? (
        <p className="prj-note">{t.cleanupOrphans(orphans)} <span className="app-muted">{t.cleanupOrphansHelp}</span></p>
      ) : null}
    </section>
  );
}

export interface RecordsRow {
  /** null = 프로젝트 없음 */
  id: string | null;
  name: string;
  href: string | null;
  chats: number;
  runs: number;
  blocked?: string | undefined;
}

/** 앱에 남은 기록(screen-projects §8.6). 모두 0이면 그리지 않는다. 프로젝트 없음 행은 `[프로젝트에 넣기…]`가 아니라 `onAssignNone`을 부른다. */
export function AppRecordsBlock({ rows, onMove, onAssignNone, children }: { rows: readonly RecordsRow[]; onMove: (id: string) => void; onAssignNone: () => void; children?: ReactNode }) {
  const shown = rows.filter((r) => r.chats + r.runs > 0);
  if (shown.length === 0) return null;
  return (
    <section className="prj-card" aria-labelledby="prj-records-title">
      <h3 id="prj-records-title">{t.recordsTitle}</h3>
      <p className="app-muted">{t.recordsDesc}</p>
      <table className="prj-table" aria-labelledby="prj-records-title">
        <thead><tr><th scope="col">{t.recordsColProject}</th><th scope="col">{t.recordsColChats}</th><th scope="col">{t.recordsColRuns}</th><th scope="col" className="prj-col-actions">{t.colActions}</th></tr></thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.id ?? "~none"}>
              <td>{r.href === null ? <span>{r.name}</span> : <Link className="ac-ellipsis" to={r.href}>{r.name}</Link>}</td>
              <td>{r.chats}</td>
              <td>{r.runs}</td>
              <td className="prj-col-actions">
                {r.id === null ? (
                  <Button size="sm" onClick={onAssignNone}>{t.legacyAssign}</Button>
                ) : (
                  <Button size="sm" aria-disabled={r.blocked !== undefined} title={r.blocked} onClick={() => r.blocked === undefined && onMove(r.id as string)} aria-label={`${r.name} ${t.recordsMove}`}>{t.recordsMove}</Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {children}
    </section>
  );
}

/** 섹션 맨 위 오류 배너. */
export function SectionError({ onRetry }: { onRetry: () => void }) {
  return <Banner tone="danger" actions={<Button size="sm" onClick={onRetry}>{t.retry}</Button>}>{t.loadFailed}</Banner>;
}
