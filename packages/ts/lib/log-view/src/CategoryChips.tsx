import { useMemo, useRef, useState, type KeyboardEvent } from "react";
import { fmt, mergeMessages, type DeepPartial, type LogViewMessages } from "./messages";
import { colorFor, orderCategories } from "./taxonomy";
import type { LogTaxonomyView, SlotFor } from "./types";

export interface CategoryChipItem {
  id: string;
  /** 현재 위치까지의 개수(재생 위치 반영). */
  count: number;
  /** 세션 전체 개수. 있으면 칩에 이 숫자를 보이고(재생 중 흔들리지 않음) 툴팁에 둘 다 적는다. */
  total?: number;
}

export interface CategoryChipsProps {
  items: readonly CategoryChipItem[];
  taxonomy: LogTaxonomyView;
  slotFor: SlotFor;
  selected: readonly string[];
  onChange: (next: string[]) => void;
  /** 이 개수를 넘으면 나머지는 [더 보기]에 둔다. */
  maxInline?: number;
  messages?: DeepPartial<LogViewMessages>;
  ariaLabel?: string;
}

/**
 * 범주 필터 칩 줄. 받은 항목에서만 만들고(범주 이름 하드코딩 없음), 순서는 분류 체계 순서 -> 개수 내림차순.
 * 다중 선택 토글(`aria-pressed`), `←→`로 칩 사이 이동, `Space`/`Enter` 토글. [전체]는 선택 비우기.
 */
export function CategoryChips(props: CategoryChipsProps) {
  const { items, taxonomy, slotFor, selected, onChange, maxInline = 12, ariaLabel } = props;
  const m = useMemo(() => mergeMessages(props.messages), [props.messages]);
  const [showAll, setShowAll] = useState(false);
  const ordered = useMemo(() => orderCategories(items, taxonomy), [items, taxonomy]);
  const visible = showAll ? ordered : ordered.slice(0, maxInline);
  const root = useRef<HTMLDivElement>(null);

  const toggle = (id: string) => onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const buttons = [...(root.current?.querySelectorAll<HTMLButtonElement>("button[data-chip]") ?? [])];
    const i = buttons.findIndex((b) => b === document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    buttons[(i + (e.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length]?.focus();
  };

  return (
    <div ref={root} className="ac-lv-catchips" role="group" aria-label={ariaLabel ?? m.categoryChips} onKeyDown={onKeyDown}>
      <button type="button" data-chip className="ac-lv-togglechip" aria-pressed={selected.length === 0} onClick={() => onChange([])}>
        {m.allCategories}
      </button>
      {visible.map((it) => {
        const entry = taxonomy.get(it.id);
        const shown = it.total ?? it.count;
        return (
          <button
            key={it.id}
            type="button"
            data-chip
            className="ac-lv-togglechip"
            aria-pressed={selected.includes(it.id)}
            title={it.total != null ? fmt(m.chipTitle, { total: it.total, current: it.count }) : entry.name}
            onClick={() => toggle(it.id)}
          >
            <span className="ac-lv-dot" style={{ background: colorFor(it.id, taxonomy, slotFor) }} aria-hidden="true" />
            <span className="ac-lv-ellipsis">{entry.name}</span>
            <span className="ac-lv-num">{shown}</span>
          </button>
        );
      })}
      {ordered.length > maxInline ? (
        <button type="button" className="ac-lv-linkbtn" aria-expanded={showAll} onClick={() => setShowAll(!showAll)}>
          {showAll ? m.collapseGroup : `${m.more} ▾`}
        </button>
      ) : null}
    </div>
  );
}
