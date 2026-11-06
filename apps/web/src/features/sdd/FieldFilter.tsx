/**
 * 필드 값 거르기(screen-sdd §7.2): 2단계 메뉴(필드 키 → 값) + 고른 조건 칩. 키·값은 작업들에 실제 나온 것(서버 목록 응답)에서 모은다.
 * 조건은 `키=값` 문자열이고 제어형이다(주소에 담는 것은 호출자 몫).
 */
import { useState } from "react";
import { Button, Popover } from "@agent-console/ui";
import { fieldPair, splitFieldPair } from "./params";
import { sddMessages as m } from "./messages";

/** 값 목록 상한(많이 나온 순 위쪽, 나머지는 검색으로) */
const VALUE_LIMIT = 50;
/** 칩이 이 수를 넘으면 `+N`으로 접는다 */
const CHIP_LIMIT = 4;

export interface FieldOption {
  key: string;
  values: readonly { value: string; count: number }[];
}

export function FieldFilter({ options, selected, onChange }: { options: readonly FieldOption[]; selected: readonly string[]; onChange: (next: string[]) => void }) {
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const current = options.find((o) => o.key === key);
  const needle = search.trim().toLowerCase();
  const values = (current?.values ?? []).filter((v) => needle === "" || v.value.toLowerCase().includes(needle)).slice(0, VALUE_LIMIT);
  const toggle = (k: string, v: string) => {
    const pair = fieldPair(k, v);
    onChange(selected.includes(pair) ? selected.filter((x) => x !== pair) : [...selected, pair]);
  };
  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setKey(null);
          setSearch("");
        }
      }}
      panelRole="dialog"
      panelLabel={m.tasks.field}
      renderTrigger={(trigger) => (
        <Button size="sm" {...trigger}>{selected.length === 0 ? m.tasks.field : `${m.tasks.field} ${selected.length}`} ▾</Button>
      )}
    >
      {current === undefined ? (
        options.length === 0 ? (
          <p className="app-muted" role="status">{m.tasks.fieldNone}</p>
        ) : (
          <ul className="sdd-multi" aria-label={m.tasks.field}>
            {options.map((o) => (
              <li key={o.key}>
                <button type="button" className="app-link-btn sdd-mono" onClick={() => { setKey(o.key); setSearch(""); }}>
                  {o.key} ›
                </button>
              </li>
            ))}
          </ul>
        )
      ) : (
        <div className="sdd-field-values">
          <button type="button" className="app-link-btn" onClick={() => setKey(null)}>{m.tasks.fieldBack}</button>
          <input type="search" className="ac-input" aria-label={m.tasks.fieldSearch} placeholder={m.tasks.fieldSearch} value={search} onChange={(e) => setSearch(e.target.value)} />
          {values.length === 0 ? <p className="app-muted" role="status">{m.tasks.fieldValueNone}</p> : null}
          <ul className="sdd-multi" aria-label={m.tasks.fieldValues(current.key)}>
            {values.map((v) => (
              <li key={v.value}>
                <label className="ac-choice">
                  <input type="checkbox" checked={selected.includes(fieldPair(current.key, v.value))} onChange={() => toggle(current.key, v.value)} />
                  <span className="ac-ellipsis">{v.value}</span>
                  <span className="app-muted">{v.count}</span>
                </label>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Popover>
  );
}

/** 고른 필드 조건 칩 줄(`{키}: {값} ×`, 넘치면 `+N`). 조건이 없으면 그리지 않는다. */
export function FieldChips({ selected, onChange }: { selected: readonly string[]; onChange: (next: string[]) => void }) {
  const [all, setAll] = useState(false);
  if (selected.length === 0) return null;
  const shown = all ? selected : selected.slice(0, CHIP_LIMIT);
  const hidden = selected.length - shown.length;
  return (
    <div className="sdd-field-chips" role="group" aria-label={m.tasks.fieldChips} data-testid="sdd-field-chips">
      {shown.map((pair) => {
        const { key, value } = splitFieldPair(pair);
        return (
          <button key={pair} type="button" className="sdd-field-chip" aria-label={m.tasks.fieldChipRemove(key, value)} onClick={() => onChange(selected.filter((x) => x !== pair))}>
            <span className="sdd-mono">{key}</span>: {value} <span aria-hidden="true">×</span>
          </button>
        );
      })}
      {hidden > 0 ? <button type="button" className="app-link-btn" onClick={() => setAll(true)}>{m.tasks.fieldChipMore(hidden)}</button> : null}
    </div>
  );
}
