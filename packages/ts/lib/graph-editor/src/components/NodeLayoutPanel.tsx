/**
 * 노드 패널의 [배치] 탭(graph-edges §3.4). 데이터와 콜백을 props로만 받는 표현 컴포넌트다.
 * 방향 목록은 `directions`(방향 어휘 표), 포트 행은 노드의 최종 포트 목록에서 만들어 넘긴 `ports`만 본다.
 * 사용자가 바꾼 키만 `layout`에 남고(상속 = 생략), 모든 값이 비면 `null`(= `layout` 키 삭제)을 돌려준다.
 */
import { useId } from "react";
import type { ReactNode } from "react";
import type { NodeLayout } from "@agent-console/contracts";
import { AUTO_DIRECTION, AUTO_SIDE, SIDES, SIDE_GLYPH } from "../logic/layout";
import type { DirectionSides } from "../logic/layout";
import { applyNodeLayoutPatch, orphanPortKeys, withPortSide } from "../logic/nodeLayoutOps";
import { defaultMessages, format } from "../messages";
import type { GraphEditorMessages } from "../messages";

/** 포트 표의 한 행. `key`는 `node.layout.ports`의 키(`in:<포트>`·`out:<포트>`). */
export interface NodeLayoutPortRow {
  key: string;
  io: "in" | "out";
  id: string;
  label: string;
  /** 이 포트의 면을 상속으로 둘 때 결정되는 면(괄호에 보인다) */
  inheritedSide: string;
}

export interface NodeLayoutPanelProps {
  /** 노드의 `layout`(없으면 모두 상속) */
  layout: NodeLayout | null | undefined;
  /** 방향 어휘 표(버튼 목록과 글리프의 출처) */
  directions: DirectionSides;
  /** 노드 층을 뺀 상속 결과: 방향 id와 어느 층에서 왔는지 */
  inheritedDirection: { id: string; source: string };
  ports: readonly NodeLayoutPortRow[];
  readOnly?: boolean;
  messages?: GraphEditorMessages;
  /** 정리된 새 `layout`(전부 기본이면 `null` = `layout` 키 삭제). 값 변경 1회 = 호출 1회 */
  onChange: (next: NodeLayout | null) => void;
  /** 있으면 [이 방향을 그래프 기본으로] 버튼을 보인다(인자 = 지금 결정된 방향 id) */
  onMakeGraphDefault?: (directionId: string) => void;
  className?: string;
}

const dirTitle = (m: GraphEditorMessages, id: string): string => m.directionLabels[id] ?? id;

export function NodeLayoutPanel(props: NodeLayoutPanelProps): ReactNode {
  const { layout, directions, inheritedDirection, ports, readOnly = false, onChange } = props;
  const m = props.messages ?? defaultMessages;
  const uid = useId();
  const own = layout?.direction ?? null;
  const ownAuto = own === AUTO_DIRECTION;
  const ownKnown = own !== null && (ownAuto || Object.hasOwn(directions, own));
  const effective = ownKnown ? own : inheritedDirection.id;
  const liveKeys = new Set(ports.map((p) => p.key));
  const orphans = orphanPortKeys(layout, liveKeys);
  const outGlyph = (id: string): string => {
    const side = directions[id]?.out;
    return side === undefined ? "" : SIDE_GLYPH[side];
  };
  const select = (id: string | null): void => onChange(applyNodeLayoutPatch(layout, { direction: id }));
  const sideText = (side: string): string => m.sideLabels[side] ?? side;
  const hasChanges = layout !== null && layout !== undefined && Object.keys(layout).length > 0;

  return (
    <section className={["ac-ge-lp", props.className].filter(Boolean).join(" ")} aria-labelledby={`${uid}-h`}>
      <h3 className="ac-ge-lp-head" id={`${uid}-h`}>
        {m.layoutTabTitle}
      </h3>
      <div className="ac-ge-lp-body">
        <div className="ac-ge-lp-row" role="group" aria-label={m.nodeLayoutDirection}>
          <span>{m.nodeLayoutDirection}</span>
          <span className="ac-ge-lp-field ac-ge-dir-group">
            {Object.keys(directions).map((id) => (
              <button
                key={id}
                type="button"
                className="ac-ge-btn"
                aria-pressed={ownKnown && own === id}
                aria-label={dirTitle(m, id)}
                title={dirTitle(m, id)}
                disabled={readOnly}
                onClick={() => select(id)}
              >
                <span aria-hidden="true">{outGlyph(id)}</span>
              </button>
            ))}
            <button type="button" className="ac-ge-btn" aria-pressed={ownAuto} title={m.nodeLayoutAutoDirectionHint} disabled={readOnly} onClick={() => select(AUTO_DIRECTION)}>
              {dirTitle(m, AUTO_DIRECTION)}
            </button>
            <button
              type="button"
              className="ac-ge-btn"
              aria-pressed={!ownKnown}
              aria-label={format(m.nodeLayoutInheritAria, { title: dirTitle(m, inheritedDirection.id) })}
              title={format(m.nodeLayoutInheritAria, { title: dirTitle(m, inheritedDirection.id) })}
              disabled={readOnly}
              onClick={() => select(null)}
            >
              {m.nodeLayoutInherit}
            </button>
          </span>
        </div>
        {!ownKnown && (
          <p className="ac-ge-lp-note">
            {format(m.nodeLayoutInheritedNow, {
              source: m.directionSourceLabels[inheritedDirection.source] ?? inheritedDirection.source,
              direction: dirTitle(m, inheritedDirection.id),
            })}
          </p>
        )}
        {own !== null && !ownKnown && <p className="ac-ge-lp-note">{format(m.nodeLayoutUnknown, { value: own })}</p>}

        {ports.length > 0 && (
          <div className="ac-ge-lp-ports">
            <span id={`${uid}-ports`} className="ac-ge-lp-subhead">
              {m.nodeLayoutPorts}
            </span>
            <ul className="ac-ge-lp-list" aria-labelledby={`${uid}-ports`}>
              {ports.map((p) => {
                const value = layout?.ports?.[p.key] ?? "";
                const known = value === "" || (SIDES as readonly string[]).includes(value) || value === AUTO_SIDE;
                const ioText = p.io === "in" ? m.nodeLayoutIn : m.nodeLayoutOut;
                return (
                  <li key={p.key} className="ac-ge-lp-row" data-testid={`port-row-${p.key}`}>
                    <label htmlFor={`${uid}-${p.key}`}>
                      <span aria-hidden="true">{p.io === "in" ? "▸" : "◂"}</span> {ioText} {p.label}
                    </label>
                    <span className="ac-ge-lp-field">
                      <select
                        id={`${uid}-${p.key}`}
                        className="ac-ge-lp-input"
                        value={value}
                        disabled={readOnly}
                        aria-label={format(m.nodeLayoutPortSide, { io: ioText, label: p.label })}
                        aria-invalid={known ? undefined : true}
                        onChange={(e) => onChange(withPortSide(layout, p.key, e.target.value === "" ? null : e.target.value))}
                      >
                        <option value="">{format(m.nodeLayoutInheritOption, { side: sideText(p.inheritedSide) })}</option>
                        {SIDES.map((s) => (
                          <option key={s} value={s}>
                            {sideText(s)}
                          </option>
                        ))}
                        <option value={AUTO_SIDE}>{m.nodeLayoutAutoSide}</option>
                        {!known && <option value={value}>{format(m.nodeLayoutUnknown, { value })}</option>}
                      </select>
                      {value !== "" && (
                        <span className="ac-ge-lp-dot" role="img" aria-label={m.nodeLayoutChangedMark} title={m.nodeLayoutChangedMark}>
                          ●
                        </span>
                      )}
                    </span>
                  </li>
                );
              })}
              {orphans.map((key) => (
                <li key={key} className="ac-ge-lp-row" data-testid={`port-orphan-${key}`}>
                  <span>{format(m.nodeLayoutOrphan, { id: key })}</span>
                  <button type="button" className="ac-ge-btn" disabled={readOnly} onClick={() => onChange(withPortSide(layout, key, null))}>
                    {m.nodeLayoutRemoveOrphan}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="ac-ge-lp-row">
          {props.onMakeGraphDefault !== undefined && (
            <button type="button" className="ac-ge-btn" disabled={readOnly} onClick={() => props.onMakeGraphDefault?.(effective)}>
              {m.nodeLayoutMakeDefault}
            </button>
          )}
          <button type="button" className="ac-ge-btn" disabled={readOnly || !hasChanges} onClick={() => onChange(null)}>
            {m.nodeLayoutReset}
          </button>
        </div>
      </div>
    </section>
  );
}
