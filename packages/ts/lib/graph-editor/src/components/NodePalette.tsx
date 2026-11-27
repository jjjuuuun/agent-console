import { useMemo, useState } from "react";
import type { NodeTypeDescriptor } from "@agent-console/contracts";
import type { GraphEditorMessages } from "../messages";
import { defaultMessages } from "../messages";
import { categoryColorVar } from "../logic/color";
import { resolveHints } from "../logic/hints";
import { isHiddenType, latestVersions } from "../logic/team";

export const PALETTE_DRAG_MIME = "application/x-agent-console-node-type";
/** 정의에서 만드는 노드를 끌 때 정의 {id,name}를 JSON으로 싣는 보조 MIME */
export const PALETTE_DEFINITION_MIME = "application/x-agent-console-definition";

export interface NodePaletteProps {
  nodeTypes: readonly NodeTypeDescriptor[];
  onAdd: (typeId: string) => void;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  messages?: GraphEditorMessages;
  /** 그룹·항목 정렬과 검색의 대소문자 비교에 쓰는 로캘(BCP 47, 보통 화면 언어). 기본 `DEFAULT_PALETTE_LOCALE`("en") */
  locale?: string;
  /** 그룹 이름 표시용 변환(보통 서버 원문 category를 화면 언어로). 그룹 묶음·색은 원래 category 기준이라 언어를 바꿔도 같다. 기본: 그대로 */
  categoryLabel?: (category: string) => string;
}

/** 팔레트 정렬·검색 로캘의 기본값(환경 로캘에 기대지 않는다). */
export const DEFAULT_PALETTE_LOCALE = "en";

export interface PaletteGroup {
  /** 그룹 키: 원래 category 문자열(없으면 `uncategorized` 문구) */
  category: string;
  /** 화면에 보일 이름(`categoryLabel`을 거친 값, 정렬 기준) */
  label: string;
  /** 분류색을 고르는 키: 원래 category, 없으면 빈 문자열(중립색) */
  colorKey: string;
  items: NodeTypeDescriptor[];
}

/**
 * 팔레트 그룹 계산(순수 함수): 그룹 = category 문자열 그대로(키·색), 보이는 이름은 `categoryLabel`을 거친 `label`, `locale`로 label 정렬, 그룹 안은 title 정렬.
 * 빈 category는 `uncategorized` 이름의 그룹. 검색은 title·id·description·category·label 부분 일치.
 */
export function groupNodeTypes(types: readonly NodeTypeDescriptor[], query: string, uncategorized: string, locale: string = DEFAULT_PALETTE_LOCALE, categoryLabel?: (category: string) => string): PaletteGroup[] {
  const q = query.trim().toLocaleLowerCase(locale);
  const groups = new Map<string, { colorKey: string; label: string; items: NodeTypeDescriptor[] }>();
  for (const t of latestVersions(types)) {
    if (isHiddenType(t)) continue;
    const raw = (t.category ?? "").trim() === "" ? "" : (t.category as string);
    const cat = raw === "" ? uncategorized : raw;
    const label = raw === "" ? uncategorized : (categoryLabel?.(raw) ?? raw);
    if (q !== "") {
      const hay = [t.title, t.id, t.description ?? "", t.category ?? "", label].join("\n").toLocaleLowerCase(locale);
      if (!hay.includes(q)) continue;
    }
    const group = groups.get(cat) ?? { colorKey: raw, label, items: [] };
    group.items.push(t);
    groups.set(cat, group);
  }
  return [...groups.entries()]
    .sort(([, a], [, b]) => a.label.localeCompare(b.label, locale))
    .map(([category, g]) => ({ category, label: g.label, colorKey: g.colorKey, items: g.items.sort((a, b) => a.title.localeCompare(b.title, locale)) }));
}

/** 노드 타입 팔레트. 그룹·항목은 전부 nodeTypes에서 생성하며 이름 고정이 없다. */
export function NodePalette(props: NodePaletteProps) {
  const m = props.messages ?? defaultMessages;
  const [inner, setInner] = useState("");
  const query = props.searchValue ?? inner;
  const locale = props.locale ?? DEFAULT_PALETTE_LOCALE;
  const groups = useMemo(() => groupNodeTypes(props.nodeTypes, query, m.paletteUncategorized, locale, props.categoryLabel), [props.nodeTypes, query, m.paletteUncategorized, locale, props.categoryLabel]);

  let body;
  if (props.loading) body = <div className="ac-ge-palette-note" role="status">{m.paletteLoading}</div>;
  else if (props.error) {
    body = (
      <div className="ac-ge-palette-note" role="alert">
        <div>{m.paletteError}</div>
        {props.onRetry && (
          <button type="button" className="ac-ge-btn" onClick={props.onRetry}>
            {m.paletteRetry}
          </button>
        )}
      </div>
    );
  } else if (props.nodeTypes.length === 0) body = <div className="ac-ge-palette-note">{m.paletteEmpty}</div>;
  else if (groups.length === 0) body = <div className="ac-ge-palette-note">{m.paletteNoMatch}</div>;
  else
    body = groups.map((g) => (
      <section key={g.category} className="ac-ge-palette-group" aria-label={g.label}>
        <h3 className="ac-ge-palette-group-title ac-ellipsis" title={g.label}>
          <span className="ac-ge-dot" style={{ background: categoryColorVar(g.colorKey) }} aria-hidden="true" />
          {g.label} ({g.items.length})
        </h3>
        <ul className="ac-ge-palette-list">
          {g.items.map((t) => {
            return (
              <li key={t.id}>
                <PaletteItem
                  title={t.title}
                  description={t.description}
                  iconText={resolveHints(t.ui_hints, t.title).iconText}
                  color={resolveHints(t.ui_hints, t.title).color ?? categoryColorVar(t.category)}
                  onAdd={() => props.onAdd(t.id)}
                  dragData={{ [PALETTE_DRAG_MIME]: t.id }}
                />
              </li>
            );
          })}
        </ul>
      </section>
    ));

  return (
    <nav className="ac-ge-palette ac-text" aria-label={m.paletteTitle}>
      <input
        type="search"
        className="ac-ge-input"
        aria-label={m.paletteSearchLabel}
        placeholder={m.paletteSearch}
        value={query}
        onChange={(e) => (props.onSearchChange ? props.onSearchChange(e.target.value) : setInner(e.target.value))}
      />
      <div className="ac-ge-palette-body">{body}</div>
    </nav>
  );
}

export interface PaletteItemProps {
  title: string;
  description?: string | undefined;
  iconText: string;
  /** 아바타 배경(CSS 값) */
  color: string;
  /** 오른쪽 보조 텍스트(예: "3회 사용") */
  meta?: string | undefined;
  /** 부제 한 줄(예: "노드 5개 · 입구 있음"). 있으면 설명 대신 보인다 */
  subtitle?: string | undefined;
  /** 있으면 항목을 비활성(`aria-disabled`)으로 두고 추가·끌기를 무시한다. 툴팁에 이 문구를 쓴다 */
  disabledReason?: string | undefined;
  onAdd: () => void;
  /** 끌 때 `dataTransfer`에 싣는 MIME → 값 */
  dragData: Record<string, string>;
}

/** 팔레트 항목 한 개: 더블클릭·Enter로 추가, 끌어다 놓기. 노드 타입/정의 어느 쪽에도 쓴다. */
export function PaletteItem(props: PaletteItemProps) {
  const disabled = props.disabledReason !== undefined;
  const tip = [props.title, props.description, props.disabledReason].filter((x) => x !== undefined && x !== "").join("\n");
  return (
    <button
      type="button"
      className="ac-ge-palette-item"
      draggable={!disabled}
      aria-disabled={disabled ? "true" : undefined}
      title={tip}
      onDoubleClick={disabled ? undefined : props.onAdd}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          if (!disabled) props.onAdd();
        }
      }}
      onDragStart={(e) => {
        if (disabled) {
          e.preventDefault();
          return;
        }
        for (const [mime, value] of Object.entries(props.dragData)) e.dataTransfer.setData(mime, value);
        e.dataTransfer.effectAllowed = "copy";
      }}
    >
      <span className="ac-ge-avatar" style={{ background: props.color }} aria-hidden="true">
        {props.iconText}
      </span>
      <span className="ac-ge-palette-texts">
        <span className="ac-ge-palette-title ac-ellipsis">{props.title}</span>
        {props.subtitle ? <span className="ac-ge-palette-meta-line ac-ellipsis">{props.subtitle}</span> : props.description && <span className="ac-ge-palette-desc ac-clamp-2">{props.description}</span>}
        {disabled && <span className="ac-ge-palette-meta-line ac-ellipsis">{props.disabledReason}</span>}
      </span>
      {props.meta && <span className="ac-ge-palette-meta">{props.meta}</span>}
    </button>
  );
}
