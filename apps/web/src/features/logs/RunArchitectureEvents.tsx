import { useLogTimeMode } from "./useLogTimeMode";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { Button } from "@agent-console/ui";
import { CategoryChips, LogEventTable, eventColumns, orderCategories, type LogTaxonomyView } from "@agent-console/log-view";
import type { LogEvent } from "@agent-console/contracts";
import { LogDetailPanel } from "./LogDetailPanel";
import { useDetailLink } from "./useDetailLink";
import { RUN_TAB_COLUMNS, RUN_TABLE_CHROME, RUN_TABLE_MIN_BODY, LOGS_LIMITS } from "./logsConfig";
import { categoryItems, originOf } from "./logsLib";
import { logsMessages as t } from "./messages";
import { slotFor } from "./slots";
import { useElementHeight } from "./useElementHeight";

/** 표 위 필터 막대의 값(탭과 [크게 보기] 대화상자가 같은 값을 쓴다). */
export interface RunEventFilters {
  q: string;
  errorsOnly: boolean;
  follow: boolean;
  categories: readonly string[];
}

export const NO_RUN_EVENT_FILTERS: RunEventFilters = { q: "", errorsOnly: false, follow: true, categories: [] };

export interface RunArchitectureEventsProps {
  events: readonly LogEvent[];
  filters: RunEventFilters;
  onFilters(next: RunEventFilters): void;
  taxonomy: LogTaxonomyView;
  isError(e: Pick<LogEvent, "category" | "tags">): boolean;
  loading: boolean;
  hasMore: boolean;
  loadingMore: boolean;
  onNearEnd(): void;
  running: boolean;
  selectedUid: string | null;
  onSelect(uid: string | null): void;
  /** 건너뛰기 링크가 부르는 "표에 포커스" 함수를 등록한다 */
  registerFocus?(focus: (() => void) | null): void;
  /** 표 위 안내 문구(필터로 걸러진 건수 등) */
  note?: string | undefined;
  searchId: string;
}

/** 압축 이벤트 표 + 필터 막대 + 인라인 상세(화면 명세 §6.3). 데이터와 선택은 부모가 갖는다. */
export function RunArchitectureEvents(p: RunArchitectureEventsProps) {
  const { filters: f } = p;
  const wrapRef = useRef<HTMLDivElement>(null);
  const [chipsOpen, setChipsOpen] = useState(false);
  const height = useElementHeight(wrapRef, 200, 80);
  const time = useLogTimeMode();
  const columns = useMemo(() => eventColumns(RUN_TAB_COLUMNS, undefined, time.widths), [time.widths]);
  const { events, isError } = p;
  const filtered = f.q !== "" || f.errorsOnly || f.categories.length > 0;
  const needle = f.q.trim().toLowerCase();
  const rows = useMemo(
    () =>
      events.filter(
        (e) =>
          (!f.errorsOnly || isError(e)) &&
          (f.categories.length === 0 || f.categories.includes(e.category)) &&
          (needle === "" || `${e.title ?? ""} ${e.summary ?? ""}`.toLowerCase().includes(needle)),
      ),
    [events, isError, f.errorsOnly, f.categories, needle],
  );
  const chips = useMemo(() => orderCategories(categoryItems([...p.events], [...p.events]), p.taxonomy), [p.events, p.taxonomy]);
  const origin = useMemo(() => originOf([...p.events]), [p.events]);
  const selected = p.selectedUid === null ? undefined : p.events.find((e) => e.uid === p.selectedUid);
  const selectedUid = selected === undefined ? null : p.selectedUid;
  const { tableRef, panelRef, onActivate } = useDetailLink(selectedUid);
  const register = p.registerFocus;
  useEffect(() => {
    if (register === undefined) return;
    const focus = () => tableRef.current?.focus();
    register(focus);
    return () => register(null);
  }, [register, tableRef]);

  return (
    <div className="logs-runtab arch-run-events">
      <div className="logs-runtab-filters">
        <input
          id={p.searchId}
          type="search"
          className="logs-input"
          aria-label={t.runTab.archSearch}
          placeholder={t.runTab.archSearch}
          maxLength={LOGS_LIMITS.searchMaxLength}
          value={f.q}
          onChange={(e) => p.onFilters({ ...f, q: e.target.value })}
        />
        {chips.length === 0 ? null : (
          <Button size="sm" aria-expanded={chipsOpen} aria-controls={`${p.searchId}-chips`} onClick={() => setChipsOpen((o) => !o)}>
            {t.runTab.categories(f.categories.length)} {chipsOpen ? "▴" : "▾"}
          </Button>
        )}
        {chipsOpen ? <span id={`${p.searchId}-chips`} className="logs-runtab-chips"><CategoryChips items={chips} taxonomy={p.taxonomy} slotFor={slotFor} selected={[...f.categories]} onChange={(next) => p.onFilters({ ...f, categories: next })} maxInline={6} /></span> : null}
        <label className="app-check"><input type="checkbox" checked={f.errorsOnly} onChange={(e) => p.onFilters({ ...f, errorsOnly: e.target.checked })} />{t.runTab.errorsOnly}</label>
        {p.running ? <label className="app-check"><input type="checkbox" checked={f.follow} onChange={(e) => p.onFilters({ ...f, follow: e.target.checked })} />{t.runTab.follow}</label> : null}
      </div>
      {p.note === undefined ? null : <p className="arch-table-note" role="status">{p.note}</p>}
      <div ref={wrapRef} className="logs-tablewrap logs-runtab-table" style={{ flex: "1 1 0" }}>
        <LogEventTable
          ref={tableRef}
          onActivate={onActivate}
          rows={rows}
          columns={columns}
          density="compact"
          selectedUid={selectedUid}
          onSelect={p.onSelect}
          taxonomy={p.taxonomy}
          isError={p.isError}
          slotFor={slotFor}
          timeMode={time.mode}
          onTimeModeChange={time.setMode}
          originTime={origin}
          loading={p.loading}
          hasMore={p.hasMore}
          loadingMore={p.loadingMore}
          onNearEnd={p.onNearEnd}
          followLast={p.running ? f.follow : undefined}
          onFollowChange={(follow) => p.onFilters({ ...f, follow })}
          height={Math.max(RUN_TABLE_MIN_BODY, height - RUN_TABLE_CHROME)}
          ariaLabel={t.runTab.archTableLabel}
          emptyBelowHeader
          renderEmpty={() => (
            <div className="logs-runtab-empty">
              <p>{filtered ? t.runTab.emptyFilter : t.runTab.archEmpty}</p>
              {filtered ? <Button size="sm" onClick={() => p.onFilters(NO_RUN_EVENT_FILTERS)}>{t.clearFilters}</Button> : null}
            </div>
          )}
        />
      </div>
      {selectedUid !== null ? (
        <section className="logs-runtab-drawer" aria-label={t.runTab.drawerTitle}>
          <div className="logs-runtab-drawer-head">
            <strong>{t.runTab.drawerTitle}</strong>
            {selected?.session ? <Link className="logs-linkbtn" to={`/logs/sessions/${encodeURIComponent(selected.session)}#e=${encodeURIComponent(selectedUid)}`}>{t.runTab.seeInLogs}</Link> : null}
          </div>
          <LogDetailPanel
            ref={panelRef}
            uid={selectedUid}
            preview={selected}
            taxonomy={p.taxonomy}
            isError={p.isError}
            originTime={origin}
            laneLabelFor={() => undefined}
            tabs={["overview", "detail", "raw"]}
            drawer={false}
            onClose={() => {
              p.onSelect(null);
              requestAnimationFrame(() => tableRef.current?.focus());
            }}
            onOpenEvent={() => undefined}
          />
        </section>
      ) : null}
    </div>
  );
}
