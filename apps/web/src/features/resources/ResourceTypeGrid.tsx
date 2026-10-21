import { useState } from "react";
import type { ResourceTypeDescriptor } from "@agent-console/contracts";
import { DescriptorIcon } from "../library";
import { resourceMessages as t } from "./messages";

export interface ResourceTypeGridProps {
  types: readonly ResourceTypeDescriptor[];
  onPick: (typeId: string) => void;
}

/** 리소스 종류 고르기 카드 격자(종류·설명·아이콘은 전부 디스크립터). 종류가 많으면 검색한다. */
export function ResourceTypeGrid({ types, onPick }: ResourceTypeGridProps) {
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const shown = types.filter((x) => q === "" || `${x.title} ${x.description ?? ""}`.toLowerCase().includes(q));
  return (
    <div className="lib-form">
      {types.length > 8 ? <input type="search" className="ac-input" aria-label={t.create.typeSearch} placeholder={t.create.typeSearch} value={query} onChange={(e) => setQuery(e.target.value)} /> : null}
      {types.length === 0 ? <p className="app-muted">{t.create.typeEmpty}</p> : null}
      <div className="res-card-grid" role="radiogroup" aria-label={t.create.typeStep}>
        {shown.map((x) => (
          <button key={x.id} type="button" role="radio" aria-checked={false} className="res-card" title={x.description ? `${x.title}: ${x.description}` : x.title} onClick={() => onPick(x.id)}>
            <span className="res-card-title">
              <DescriptorIcon hint={x.ui_hints?.icon} title={x.title} size={20} />
              <span className="ac-ellipsis">{x.title}</span>
            </span>
            {x.description ? <span className="app-muted lib-field-note ac-clamp-3">{x.description}</span> : null}
          </button>
        ))}
      </div>
    </div>
  );
}
