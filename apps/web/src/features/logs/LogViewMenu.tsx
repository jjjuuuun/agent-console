import { useMemo } from "react";
import { TIME_MODES, defaultLogViewMessages, type TimeMode } from "@agent-console/log-view";
import { ActionMenu, type ActionMenuEntry } from "./ActionMenu";
import { logsMessages as t } from "./messages";

export interface LogViewMenuProps {
  /** 응답 묶기(세션 상세) */
  groupResponses?: { checked: boolean; onChange(next: boolean): void } | undefined;
  /** 숨긴 범주 포함. 숨긴 범주가 없으면 넘기지 않는다(항목이 없다) */
  includeHidden?: { checked: boolean; onChange(next: boolean): void } | undefined;
  /** 정렬(검색 이벤트 보기) */
  sort?: { order: "asc" | "desc"; onChange(next: "asc" | "desc"): void } | undefined;
  /** 시각 표시 방식 */
  time?: { mode: TimeMode; onChange(next: TimeMode): void } | undefined;
  /** 열 구성(최소 한 열은 남긴다) */
  columns?: { all: readonly string[]; selected: readonly string[]; labelOf(id: string): string; onChange(next: string[]): void } | undefined;
  /** "분류 체계 편집…" — 설정 › 로그 분류로 이동 */
  onEditTaxonomy?: (() => void) | undefined;
  open?: boolean | undefined;
  onOpenChange?: ((open: boolean) => void) | undefined;
}

/** [보기 ▾] 메뉴 항목 만들기(순수 함수): 응답 묶기 · 숨긴 범주 포함 · 정렬 · 시각 표시 · 열 구성 · 분류 체계 편집…. 넘기지 않은 부분은 없다. */
export function viewMenuEntries(p: LogViewMenuProps): ActionMenuEntry[] {
  const out: ActionMenuEntry[] = [];
  if (p.groupResponses) out.push({ kind: "check", id: "group", label: t.view.groupResponses, checked: p.groupResponses.checked, onChange: p.groupResponses.onChange });
  if (p.includeHidden) out.push({ kind: "check", id: "hidden", label: t.view.includeHidden, checked: p.includeHidden.checked, onChange: p.includeHidden.onChange });
  const sort = p.sort;
  if (sort) {
    out.push({ kind: "heading", id: "sort", label: t.view.sort });
    out.push({ kind: "radio", id: "sort-desc", label: t.search.orderDescName, checked: sort.order === "desc", onSelect: () => sort.onChange("desc") });
    out.push({ kind: "radio", id: "sort-asc", label: t.search.orderAscName, checked: sort.order === "asc", onSelect: () => sort.onChange("asc") });
  }
  const time = p.time;
  if (time) {
    out.push({ kind: "heading", id: "time", label: t.view.timeMode });
    for (const mode of TIME_MODES) out.push({ kind: "radio", id: `time-${mode}`, label: defaultLogViewMessages.timeMode[mode], checked: time.mode === mode, onSelect: () => time.onChange(mode) });
  }
  const cols = p.columns;
  if (cols) {
    out.push({ kind: "heading", id: "cols", label: t.view.columns });
    for (const id of cols.all) {
      const on = cols.selected.includes(id);
      out.push({ kind: "check", id: `col-${id}`, label: cols.labelOf(id), checked: on, disabled: on && cols.selected.length === 1, onChange: (next) => cols.onChange(next ? [...cols.selected, id] : cols.selected.filter((x) => x !== id)) });
    }
  }
  if (p.onEditTaxonomy) {
    if (out.length > 0) out.push({ kind: "separator", id: "sep-tax" });
    out.push({ kind: "item", id: "taxonomy", label: t.view.taxonomyLink, onSelect: p.onEditTaxonomy });
  }
  return out;
}

/**
 * [보기 ▾]: 한 번 정해 두면 잘 안 바꾸는 표시 설정을 한 메뉴에 모은다(5.7R.32). 항목 이름이 곧 상태다(체크 ✓·라디오 ●).
 * 상태·콜백은 전부 props이고 저장은 호출자(`useColumnChoice`·`useLogTimeMode` 등)가 한다.
 */
export function LogViewMenu(p: LogViewMenuProps) {
  const entries = useMemo(() => viewMenuEntries(p), [p]);
  return <ActionMenu label={t.view.button} trigger={<>{t.view.button} ▾</>} entries={entries} {...(p.open === undefined ? {} : { open: p.open })} {...(p.onOpenChange === undefined ? {} : { onOpenChange: p.onOpenChange })} />;
}
