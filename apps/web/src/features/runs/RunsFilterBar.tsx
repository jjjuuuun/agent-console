import { Button } from "@agent-console/ui";
import { runStatusLabels, runsMessages as t } from "./messages";
import { PERIOD_OPTIONS } from "./runsConfig";

export interface FilterOption {
  id: string;
  label: string;
}

export interface RunsFilters {
  graph: string;
  agent: string;
  conversation: string;
  /** 비어 있으면 전체 */
  statuses: readonly string[];
  period: string;
  query: string;
  /** 자식 실행(중첩 팀)도 목록에 보일지(URL `?children=1`, 기본 꺼짐) */
  children: boolean;
  /** 이 루트 실행 아래 자식만 본다(URL `?root=`). 비어 있으면 전체 */
  root: string;
}

export interface RunsFilterBarProps {
  value: RunsFilters;
  onChange(next: RunsFilters): void;
  graphs: readonly FilterOption[];
  agents: readonly FilterOption[];
  conversations: readonly FilterOption[];
  /** 고를 수 있는 상태 값(어휘 + 데이터에 나온 값) */
  statuses: readonly string[];
  waitingStatus: string;
  /** 검색칸 포커스를 외부에서 주기 위한 ref */
  searchRef?: React.Ref<HTMLInputElement>;
  firstRef?: React.Ref<HTMLSelectElement>;
}

function Select({ label, value, onChange, options, selectRef }: { label: string; value: string; onChange(v: string): void; options: readonly FilterOption[]; selectRef?: React.Ref<HTMLSelectElement> }) {
  return (
    <label className="runs-filter">
      <span className="app-muted">{label}</span>
      <select ref={selectRef} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t.list.filters.all}</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>{o.label}</option>
        ))}
      </select>
    </label>
  );
}

/** 실행 목록 필터 줄. 값과 변경은 모두 props(URL 쿼리와의 연결은 컨테이너가). */
export function RunsFilterBar({ value, onChange, statuses, waitingStatus, searchRef, firstRef, graphs, agents, conversations }: RunsFilterBarProps) {
  const set = (patch: Partial<RunsFilters>) => onChange({ ...value, ...patch });
  const toggleStatus = (s: string) => set({ statuses: value.statuses.includes(s) ? value.statuses.filter((x) => x !== s) : [...value.statuses, s] });
  const waitingOnly = value.statuses.length === 1 && value.statuses[0] === waitingStatus;
  return (
    <div className="runs-filters" role="search" aria-label={t.list.filters.label}>
      <Select label={t.list.filters.graph} value={value.graph} onChange={(v) => set({ graph: v })} options={graphs} selectRef={firstRef} />
      <Select label={t.list.filters.agent} value={value.agent} onChange={(v) => set({ agent: v })} options={agents} />
      <Select label={t.list.filters.conversation} value={value.conversation} onChange={(v) => set({ conversation: v })} options={conversations} />
      <label className="runs-filter">
        <span className="app-muted">{t.list.filters.period}</span>
        <select value={value.period} onChange={(e) => set({ period: e.target.value })}>
          {PERIOD_OPTIONS.map((p) => (
            <option key={p.id} value={p.id}>{t.list.periods[p.id] ?? p.id}</option>
          ))}
        </select>
      </label>
      <fieldset className="runs-filter runs-status-filter">
        <legend className="app-muted">{t.list.filters.status}</legend>
        {statuses.map((s) => (
          <label key={s} className="app-check">
            <input type="checkbox" checked={value.statuses.includes(s)} onChange={() => toggleStatus(s)} />
            {runStatusLabels[s] ?? s}
          </label>
        ))}
      </fieldset>
      <Button size="sm" variant={waitingOnly ? "primary" : "secondary"} aria-pressed={waitingOnly} onClick={() => set({ statuses: waitingOnly ? [] : [waitingStatus] })}>
        {t.list.filters.waitingOnly}
      </Button>
      <label className="app-check">
        <input type="checkbox" checked={value.children} onChange={(e) => set({ children: e.target.checked })} />
        {t.list.filters.children}
      </label>
      {value.root !== "" ? (
        <span className="runs-filter">
          <span className="app-muted">{t.list.filters.rootOnly(value.root.slice(0, 6))}</span>
          <button type="button" className="app-link-btn" onClick={() => set({ root: "" })}>{t.list.filters.rootClear}</button>
        </span>
      ) : null}
      <label className="runs-filter">
        <span className="app-muted">{t.list.filters.search}</span>
        <input ref={searchRef} type="search" value={value.query} placeholder={t.list.filters.searchPlaceholder} onChange={(e) => set({ query: e.target.value })} />
      </label>
    </div>
  );
}
