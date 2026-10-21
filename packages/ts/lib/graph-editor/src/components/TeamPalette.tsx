import { useMemo, useState } from "react";
import type { NodeTypeDescriptor } from "@agent-console/contracts";
import type { GraphEditorMessages } from "../messages";
import { defaultMessages, format } from "../messages";
import { categoryColorVar } from "../logic/color";
import { firstGlyph, resolveHints, safeIconText } from "../logic/hints";
import { isHiddenType, latestVersions } from "../logic/team";
import type { DefinitionItem, PaletteAddSpec } from "../types";
import { PALETTE_DEFINITION_MIME, PALETTE_DRAG_MIME, PaletteItem, groupNodeTypes } from "./NodePalette";

export interface TeamPaletteProps {
  nodeTypes: readonly NodeTypeDescriptor[];
  /** 키 = 노드 타입 `binds.kind` */
  definitionLists?: Readonly<Record<string, readonly DefinitionItem[]>>;
  /** 정의 종류 → 구역 표시 이름(없으면 항목 `groupLabel` → kind 문자열) */
  definitionKindTitles?: Readonly<Record<string, string>>;
  onAdd: (spec: PaletteAddSpec) => void;
  /** 정의가 없는 구역의 [만들기] */
  onCreateDefinition?: (kind: string) => void;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  messages?: GraphEditorMessages;
}

export interface DefinitionSubgroup {
  type: NodeTypeDescriptor;
  items: DefinitionItem[];
}

export interface DefinitionSection {
  kind: string;
  title: string;
  /** 필터 전에 정의가 하나도 없었는가(빈 안내용) */
  empty: boolean;
  subgroups: DefinitionSubgroup[];
}

const matches = (q: string, ...fields: (string | null | undefined)[]): boolean =>
  q === "" || fields.join("\n").toLocaleLowerCase().includes(q);

/**
 * 팔레트 구역 계산(순수 함수).
 * - 정의 구역: `binds`가 있는 노드 타입 × `definitionLists[binds.kind]` (숨김 타입 제외). 같은 kind의 타입은 한 구역의 소그룹.
 * - 기본 노드: `binds`가 없는 타입(숨김 제외), category 그룹.
 * 검색은 이름·설명·category 부분 일치.
 */
export function buildTeamPalette(
  nodeTypes: readonly NodeTypeDescriptor[],
  definitionLists: Readonly<Record<string, readonly DefinitionItem[]>>,
  kindTitles: Readonly<Record<string, string>>,
  query: string,
  uncategorized: string,
): { sections: DefinitionSection[]; base: ReturnType<typeof groupNodeTypes> } {
  const q = query.trim().toLocaleLowerCase();
  const visible = latestVersions(nodeTypes).filter((t) => !isHiddenType(t));
  const bound = visible.filter((t) => t.binds !== null && t.binds !== undefined);
  const base = groupNodeTypes(
    visible.filter((t) => t.binds === null || t.binds === undefined),
    query,
    uncategorized,
  );
  const kinds = [...new Set(bound.map((t) => (t.binds as { kind: string }).kind))];
  const sections: DefinitionSection[] = kinds.map((kind) => {
    const list = definitionLists[kind] ?? [];
    const title = kindTitles[kind] ?? list.find((it) => it.groupLabel !== undefined)?.groupLabel ?? kind;
    const subgroups = bound
      .filter((t) => (t.binds as { kind: string }).kind === kind)
      .map((type) => ({
        type,
        items: list.filter((it) => matches(q, it.name, it.description, it.meta, type.title, type.category)),
      }))
      .filter((g) => g.items.length > 0);
    return { kind, title, empty: list.length === 0, subgroups };
  });
  return { sections: sections.sort((a, b) => a.title.localeCompare(b.title, "ko")), base };
}

/**
 * 팀 구성 팔레트: "정의에서 만드는 노드"(binds × 정의 목록) 구역들 + "기본 노드"(binds 없음) 구역.
 * 구역 제목·항목은 전부 데이터에서 온다. 노드 타입 id 분기 없음.
 */
export function TeamPalette(props: TeamPaletteProps) {
  const m = props.messages ?? defaultMessages;
  const [inner, setInner] = useState("");
  const query = props.searchValue ?? inner;
  const lists = props.definitionLists ?? {};
  const titles = props.definitionKindTitles ?? {};
  const { sections, base } = useMemo(
    () => buildTeamPalette(props.nodeTypes, lists, titles, query, m.paletteUncategorized),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [props.nodeTypes, props.definitionLists, props.definitionKindTitles, query, m.paletteUncategorized],
  );
  const hasAnyType = props.nodeTypes.some((t) => !isHiddenType(t));
  const visibleSections = sections.filter((s) => s.subgroups.length > 0 || (s.empty && query.trim() === ""));

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
  } else if (!hasAnyType) body = <div className="ac-ge-palette-note">{m.paletteEmpty}</div>;
  else if (visibleSections.length === 0 && base.length === 0) body = <div className="ac-ge-palette-note">{m.paletteNoMatch}</div>;
  else {
    body = (
      <>
        {visibleSections.map((s) => (
          <section key={s.kind} className="ac-ge-palette-section" aria-label={s.title} data-binds-kind={s.kind}>
            <h3 className="ac-ge-palette-section-title ac-ellipsis" title={s.title}>{s.title}</h3>
            {s.empty ? (
              <div className="ac-ge-palette-note">
                <div>{format(m.paletteNoDefinitions, { kind: s.title })}</div>
                {props.onCreateDefinition && (
                  <button type="button" className="ac-ge-btn" onClick={() => props.onCreateDefinition?.(s.kind)}>
                    {format(m.paletteCreateDefinition, { kind: s.title })}
                  </button>
                )}
              </div>
            ) : (
              s.subgroups.map((g) => {
                const hints = resolveHints(g.type.ui_hints, g.type.title);
                return (
                  <div key={g.type.id} className="ac-ge-palette-group">
                    {s.subgroups.length > 1 && (
                      <h4 className="ac-ge-palette-group-title ac-ellipsis" title={g.type.title}>
                        <span className="ac-ge-dot" style={{ background: hints.color ?? categoryColorVar(g.type.category) }} aria-hidden="true" />
                        {g.type.title}
                      </h4>
                    )}
                    <ul className="ac-ge-palette-list">
                      {g.items.map((it) => (
                        <li key={it.id}>
                          <PaletteItem
                            title={it.name}
                            description={it.description}
                            subtitle={it.meta}
                            disabledReason={it.disabledReason}
                            iconText={safeIconText(it.iconName) ?? firstGlyph(it.name)}
                            color={hints.color ?? categoryColorVar(g.type.category)}
                            meta={it.usageCount !== undefined && it.usageCount > 0 ? format(m.paletteUsage, { n: it.usageCount }) : undefined}
                            onAdd={() => props.onAdd({ typeId: g.type.id, definition: { id: it.id, name: it.name } })}
                            dragData={{
                              [PALETTE_DRAG_MIME]: g.type.id,
                              [PALETTE_DEFINITION_MIME]: JSON.stringify({ id: it.id, name: it.name }),
                            }}
                          />
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })
            )}
            {!s.empty && query.trim() === "" && s.subgroups.length > 0 && s.subgroups.every((g) => g.items.length > 0 && g.items.every((it) => it.disabledReason !== undefined)) && (
              <div className="ac-ge-palette-note">
                <div>{format(m.paletteOnlyDisabled, { kind: s.title })}</div>
                {props.onCreateDefinition && (
                  <button type="button" className="ac-ge-btn" onClick={() => props.onCreateDefinition?.(s.kind)}>
                    {format(m.paletteCreateDefinition, { kind: s.title })}
                  </button>
                )}
              </div>
            )}
          </section>
        ))}
        {base.length > 0 && (
          <section className="ac-ge-palette-section" aria-label={m.paletteBaseSection}>
            <h3 className="ac-ge-palette-section-title ac-ellipsis">{m.paletteBaseSection}</h3>
            {base.map((g) => (
              <section key={g.category} className="ac-ge-palette-group" aria-label={g.category}>
                <h4 className="ac-ge-palette-group-title ac-ellipsis" title={g.category}>
                  <span className="ac-ge-dot" style={{ background: categoryColorVar(g.category === m.paletteUncategorized ? "" : g.category) }} aria-hidden="true" />
                  {g.category} ({g.items.length})
                </h4>
                <ul className="ac-ge-palette-list">
                  {g.items.map((t) => {
                    const hints = resolveHints(t.ui_hints, t.title);
                    return (
                      <li key={t.id}>
                        <PaletteItem
                          title={t.title}
                          description={t.description}
                          iconText={hints.iconText}
                          color={hints.color ?? categoryColorVar(t.category)}
                          onAdd={() => props.onAdd({ typeId: t.id })}
                          dragData={{ [PALETTE_DRAG_MIME]: t.id }}
                        />
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
          </section>
        )}
      </>
    );
  }

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
