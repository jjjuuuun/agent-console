import { useMemo, useReducer, type ReactNode, type Ref } from "react";
import { LogFilterBar, createLocalStorageSavedFilters, type FilterFieldSpec, type LogFilterValue, type SavedFilter, type SavedFilterStore } from "@agent-console/log-view";
import type { LogSourceInfo } from "@agent-console/contracts";
import { useStorage } from "../../app/StorageContext";
import { CUSTOM_RANGE_SEP, FILTER_FIELDS, LOGS_LIMITS, LOGS_STORAGE, RANGE_OPTIONS, SEARCH_FIELD, UNGROUPED_PROJECT_VALUE } from "./logsConfig";
import { customRangeValue, parseRange } from "./logsLib";
import { logsMessages as t } from "./messages";

/** 필터 필드 정의(데이터 `logsData.json`) → 필터 막대용 `FilterFieldSpec`. 선택지는 막대의 `renderSelectOptions`가 채운다. */
export function buildFilterFields(): FilterFieldSpec[] {
  return FILTER_FIELDS.map((f) => ({ name: f.name, label: t.filters.labels[f.name] ?? f.name, input: f.input }));
}

/** 즐겨찾는 필터 저장소(`ac.logs.savedFilters`, localStorage = 개인 화면 선택이며 서버 저장이 아니다). */
export function useSavedFilterStore(): SavedFilterStore {
  const storage = useStorage();
  return useMemo(
    () =>
      createLocalStorageSavedFilters(LOGS_STORAGE.savedFilters, {
        getItem: (k) => storage.get(k),
        setItem: (k, v) => storage.set(k, v),
      }),
    [storage],
  );
}

export interface FilterOptionsData {
  sources: readonly LogSourceInfo[] | undefined;
  /** 분류 체계 순서 + 데이터에 나온 범주 id */
  categoryIds: readonly string[];
  categoryName(id: string): string;
  /** 설정 `logs.projects.groups`의 그룹 */
  projectGroups: readonly { id: string; label?: string | null | undefined }[];
}

export interface LogFiltersProps {
  value: LogFilterValue;
  onChange(next: LogFilterValue): void;
  options: FilterOptionsData;
  /** 필드 이름 → 불러온 항목의 고유값(제안) */
  suggestions?: Readonly<Record<string, readonly string[]>> | undefined;
  /** 서버 422(`details.path`) → 필드 이름별 메시지 */
  fieldErrors?: Readonly<Record<string, string>> | undefined;
  inputRef?: Ref<HTMLInputElement> | undefined;
  compact?: boolean | undefined;
  /** 즐겨찾는 필터에 같이 저장할 화면 상태 */
  savedExtra?: (() => Record<string, unknown>) | undefined;
  onApplySavedExtra?: ((extra: Record<string, unknown> | undefined) => void) | undefined;
  trailing?: ReactNode;
  /** 검색어 입력을 숨길 때 false */
  search?: boolean;
}

/**
 * 로그 필터 막대(앱 층): `LogFilterBar`에 필드 정의·선택지·제안·즐겨찾기·서버 오류를 연결한다.
 * 필터 이름은 `logsData.json`의 목록에서만 온다. 서버가 모르는 이름을 URL로 받으면 막대가 "알 수 없는 필터" 칩으로 보인다.
 */
export function LogFilters({ value, onChange, options, suggestions, fieldErrors, inputRef, compact, savedExtra, onApplySavedExtra, trailing, search = true }: LogFiltersProps) {
  const fields = useMemo(() => buildFilterFields(), []);
  const store = useSavedFilterStore();
  const [, refresh] = useReducer((n: number) => n + 1, 0);
  const saved = store.list();
  const selectOptions = (name: string) => {
    const def = FILTER_FIELDS.find((f) => f.name === name);
    if (def?.optionsFrom === "sources") return (options.sources ?? []).map((s) => ({ value: s.descriptor.id, label: s.descriptor.title }));
    if (def?.optionsFrom === "categories") return options.categoryIds.map((id) => ({ value: id, label: options.categoryName(id) }));
    if (def?.optionsFrom === "projects")
      return [...options.projectGroups.map((g) => ({ value: g.id, label: g.label?.trim() ? g.label : g.id })), { value: UNGROUPED_PROJECT_VALUE, label: t.filters.ungrouped }];
    return undefined;
  };
  return (
    <LogFilterBar
      fields={fields}
      value={value}
      onChange={onChange}
      {...(search ? { searchField: SEARCH_FIELD } : {})}
      searchMaxLength={LOGS_LIMITS.searchMaxLength}
      renderSelectOptions={selectOptions}
      {...(suggestions === undefined ? {} : { suggestions })}
      {...(fieldErrors === undefined ? {} : { fieldErrors })}
      {...(inputRef === undefined ? {} : { inputRef })}
      {...(compact === undefined ? {} : { compact })}
      savedFilters={saved}
      onSaveFilter={(name) => {
        const extra = savedExtra?.();
        store.save({ name, value, ...(extra === undefined ? {} : { extra }) });
        refresh();
      }}
      onApplySaved={(f: SavedFilter) => {
        onChange(f.value);
        onApplySavedExtra?.(f.extra);
      }}
      onDeleteSaved={(name) => {
        store.remove(name);
        refresh();
      }}
      trailing={trailing}
    />
  );
}

export interface RangeControlProps {
  /** URL `range` 값(없으면 기본) */
  value: string | undefined;
  fallbackId: string;
  onChange(next: string): void;
  /** 대시보드 도구 줄처럼 "위젯 설정대로" 항목이 필요하면 그 문구 */
  settingsOption?: string | undefined;
  label?: string;
}

/** 기간 선택(선택지 + 사용자 지정). 값은 URL `range`이고 서버에는 `since`/`until`로 바뀌어 간다. */
export function RangeControl({ value, fallbackId, onChange, settingsOption, label = t.filters.range }: RangeControlProps) {
  const parsed = parseRange(value === undefined && settingsOption !== undefined ? undefined : value, fallbackId);
  const custom = parsed.kind === "custom";
  const current = value === undefined && settingsOption !== undefined ? "" : custom ? "custom" : parsed.id;
  const [since, until] = custom ? [parsed.since ?? "", parsed.until ?? ""] : ["", ""];
  const toLocal = (iso: string) => {
    if (iso === "") return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const p = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
  };
  const fromLocal = (v: string) => (v === "" ? "" : new Date(v).toISOString());
  return (
    <span className="logs-range">
      <label className="logs-range-label">
        <span>{label}</span>
        <select
          value={current}
          onChange={(e) => {
            const v = e.target.value;
            if (v === "custom") onChange(customRangeValue(new Date(Date.now() - 86_400_000).toISOString(), ""));
            else onChange(v);
          }}
        >
          {settingsOption === undefined ? null : <option value="">{settingsOption}</option>}
          {RANGE_OPTIONS.filter((p) => settingsOption === undefined || p.seconds !== null).map((p) => (
            <option key={p.id} value={p.id}>{t.filters.rangeNames[p.id] ?? p.id}</option>
          ))}
          <option value="custom">{t.filters.rangeNames["custom"]}</option>
        </select>
      </label>
      {custom ? (
        <>
          <label className="logs-range-label">
            <span>{t.dashboards.customSince}</span>
            <input type="datetime-local" value={toLocal(since)} onChange={(e) => onChange(customRangeValue(fromLocal(e.target.value), until))} />
          </label>
          <label className="logs-range-label">
            <span>{t.dashboards.customUntil}</span>
            <input type="datetime-local" value={toLocal(until)} onChange={(e) => onChange(customRangeValue(since, fromLocal(e.target.value)))} />
          </label>
        </>
      ) : null}
    </span>
  );
}

export { CUSTOM_RANGE_SEP };
