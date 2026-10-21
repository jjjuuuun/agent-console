import { useMemo, useRef, useState } from "react";
import type { ResourceSummary, ResourceTypeDescriptor } from "@agent-console/contracts";
import { Button, Dialog } from "@agent-console/ui";
import { DescriptorIcon } from "./DescriptorIcon";
import { libraryMessages as t } from "./messages";

export interface ResourcePickerProps {
  open: boolean;
  resources: readonly ResourceSummary[];
  types: readonly ResourceTypeDescriptor[];
  /** 이미 붙어 있어 고르지 않아도 되는 리소스 id */
  exclude?: ReadonlySet<string>;
  onPick: (resource: ResourceSummary) => void;
  /** 있으면 하단에 [새 리소스 만들기 →] */
  onCreateNew?: () => void;
  onClose: () => void;
}

/** 리소스 고르기 다이얼로그(검색 + 종류 필터 칩). 종류 목록·아이콘·이름은 모두 디스크립터 데이터. */
export function ResourcePicker({ open, resources, types, exclude, onPick, onCreateNew, onClose }: ResourcePickerProps) {
  const [query, setQuery] = useState("");
  const [typeId, setTypeId] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const typeById = useMemo(() => new Map(types.map((x) => [x.id, x])), [types]);
  const present = useMemo(() => [...new Set(resources.map((r) => r.type))], [resources]);
  const q = query.trim().toLowerCase();
  const rows = resources.filter(
    (r) => !(exclude?.has(r.id) ?? false) && (typeId === null || r.type === typeId) && (q === "" || `${r.name} ${r.description ?? ""} ${r.id}`.toLowerCase().includes(q)),
  );
  return (
    <Dialog
      open={open}
      title={t.picker.title}
      onClose={onClose}
      initialFocus={searchRef}
      actions={
        <>
          {onCreateNew ? (
            <Button variant="ghost" onClick={onCreateNew}>
              {t.picker.createNew}
            </Button>
          ) : null}
          <Button onClick={onClose}>{t.close}</Button>
        </>
      }
    >
      <div className="lib-form">
        <input ref={searchRef} type="search" className="ac-input" aria-label={t.picker.search} placeholder={t.picker.search} value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="lib-chips" role="group" aria-label={t.picker.allTypes}>
          <button type="button" className="lib-chip" aria-pressed={typeId === null} onClick={() => setTypeId(null)}>
            {t.picker.allTypes}
          </button>
          {present.map((id) => (
            <button key={id} type="button" className="lib-chip" aria-pressed={typeId === id} onClick={() => setTypeId(typeId === id ? null : id)}>
              {typeById.get(id)?.title ?? id}
            </button>
          ))}
        </div>
        {rows.length === 0 ? (
          <p className="app-muted">{resources.length === 0 ? t.picker.empty : t.picker.noMatch}</p>
        ) : (
          <ul className="lib-pick-list">
            {rows.map((r) => {
              const type = typeById.get(r.type);
              return (
                <li key={r.id}>
                  <button type="button" className="lib-pick-item" aria-label={t.picker.pick(r.name)} onClick={() => onPick(r)}>
                    <DescriptorIcon hint={type?.ui_hints?.icon} title={type?.title ?? r.type} size={18} />
                    <span className="lib-pick-main">
                      <span className="ac-ellipsis">{r.name}</span>
                      <span className="app-muted ac-ellipsis lib-pick-sub">{[type?.title ?? r.type, r.description].filter(Boolean).join(" · ")}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Dialog>
  );
}
