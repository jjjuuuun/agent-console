import { useId } from "react";
import type { SortState } from "./format";
import { resolveMessages } from "./messages";

export interface MemorySortMenuProps {
  /** 고를 수 있는 서버 정렬 값(`MEMORY_ENTRY_SORTS`). 라벨은 `sort.<값>` 문구, 없으면 원문. */
  sorts: readonly string[];
  /** 지금 정렬. null = 서버 기본 순서. */
  value: SortState | null;
  onChange: (next: SortState | null) => void;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/** 도구줄 [정렬] 메뉴 본문: 정렬 기준 라디오 + 방향 라디오. 열 머리에 없는 기준(만든 때)도 여기서 고른다. */
export function MemorySortMenu({ sorts, value, onChange, messages: custom, className }: MemorySortMenuProps) {
  const m = resolveMessages(custom);
  const uid = useId();
  const order = value?.order ?? "desc";
  return (
    <div className={`ac-mem-root ac-mem-sortmenu${className ? ` ${className}` : ""}`}>
      <div role="radiogroup" aria-label={m["sort.label"]} className="ac-mem-sortgroup">
        {sorts.map((s) => (
          <label key={s} className="ac-mem-switch">
            <input type="radio" name={`${uid}-sort`} checked={value?.key === s} onChange={() => onChange({ key: s, order })} />
            <span>{m[`sort.${s}`] ?? s}</span>
          </label>
        ))}
      </div>
      <div role="radiogroup" aria-label={m["sort.order"]} className="ac-mem-sortgroup">
        {(["asc", "desc"] as const).map((o) => (
          <label key={o} className="ac-mem-switch">
            <input type="radio" name={`${uid}-order`} checked={order === o} disabled={value === null} onChange={() => value && onChange({ key: value.key, order: o })} />
            <span>{m[`sort.${o}`]}</span>
          </label>
        ))}
      </div>
    </div>
  );
}
