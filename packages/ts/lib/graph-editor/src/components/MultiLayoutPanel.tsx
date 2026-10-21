/**
 * 다중 선택 패널의 배치 섹션(graph-edges §1.4·§2.4·§3.4). 데이터와 콜백을 props로만 받는 표현 컴포넌트다.
 * - 연결선만 여러 개 선택: [모양 ▾]·[경로 초기화](확인 단계). 모양 목록은 `shapes`(레지스트리)에서 온다.
 * - 노드만 여러 개 선택: [방향] 버튼. 방향 목록은 `directions`(방향 어휘 표)에서 온다.
 * 선택한 항목의 값이 서로 다르면 "여러 값"으로 보이고, 고르면 선택 전부에 같은 값을 쓴다(상속 = 키 삭제).
 */
import { useId, useState } from "react";
import type { ReactNode } from "react";
import { AUTO_DIRECTION, SIDE_GLYPH } from "../logic/layout";
import type { DirectionSides } from "../logic/layout";
import { defaultMessages, format } from "../messages";
import type { GraphEditorMessages } from "../messages";
import type { EdgeShapeDescriptor } from "../shapes/types";

export interface MultiLayoutEdgesProps {
  /** 선택한 연결선 수 */
  count: number;
  shapes: readonly EdgeShapeDescriptor[];
  /** 선택한 연결선의 `layout.shape`가 모두 같으면 그 값(상속이면 `""`), 다르면 `null` */
  shape: string | null;
  /** 경로 초기화로 실제 지워질 연결선 수(0이면 안내만 한다) */
  resettable: number;
  /** 모양을 정한다(`null` = 상속, 키 삭제). 선택 전부에 쓴다 */
  onShape: (shapeId: string | null) => void;
  /** 확인 뒤 호출: 선택한 연결선의 경유점·꺾임·라벨 위치를 지운다(모양 유지) */
  onResetPaths: () => void;
}

export interface MultiLayoutNodesProps {
  count: number;
  directions: DirectionSides;
  /** 선택한 노드의 `layout.direction`이 모두 같으면 그 값(상속이면 `""`), 다르면 `null` */
  direction: string | null;
  /** 방향을 정한다(`null` = 상속, 키 삭제) */
  onDirection: (directionId: string | null) => void;
}

export interface MultiLayoutPanelProps {
  edges?: MultiLayoutEdgesProps;
  nodes?: MultiLayoutNodesProps;
  readOnly?: boolean;
  messages?: GraphEditorMessages;
  className?: string;
}

const MIXED = "\u0000mixed";

export function MultiLayoutPanel(props: MultiLayoutPanelProps): ReactNode {
  const { edges, nodes, readOnly = false } = props;
  const m = props.messages ?? defaultMessages;
  const uid = useId();
  const [confirm, setConfirm] = useState(false);
  const [note, setNote] = useState("");
  if (edges === undefined && nodes === undefined) return null;
  const dirTitle = (id: string): string => m.directionLabels[id] ?? id;

  return (
    <section className={["ac-ge-lp", props.className].filter(Boolean).join(" ")} aria-labelledby={`${uid}-h`}>
      <h3 className="ac-ge-lp-head" id={`${uid}-h`}>
        {format(m.selectedCount, { count: edges?.count ?? nodes?.count ?? 0 })}
      </h3>
      <div className="ac-ge-lp-body">
        {edges !== undefined && (
          <>
            <div className="ac-ge-lp-row">
              <label htmlFor={`${uid}-shape`}>{m.edgeLayoutShape}</label>
              <span className="ac-ge-lp-field">
                <select
                  id={`${uid}-shape`}
                  className="ac-ge-lp-input"
                  value={edges.shape === null ? MIXED : edges.shape}
                  disabled={readOnly}
                  onChange={(e) => {
                    if (e.target.value === MIXED) return;
                    edges.onShape(e.target.value === "" ? null : e.target.value);
                  }}
                >
                  {edges.shape === null && (
                    <option value={MIXED} disabled>
                      {m.multiLayoutMixed}
                    </option>
                  )}
                  <option value="">{m.nodeLayoutInherit}</option>
                  {edges.shapes.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.title}
                    </option>
                  ))}
                  {edges.shape !== null && edges.shape !== "" && !edges.shapes.some((s) => s.id === edges.shape) && (
                    <option value={edges.shape}>{format(m.unknownShape, { id: edges.shape })}</option>
                  )}
                </select>
              </span>
            </div>
            <div className="ac-ge-lp-row">
              {confirm ? (
                <div role="alertdialog" aria-label={m.edgeLayoutResetPath} className="ac-ge-tidy-confirm">
                  <span>{format(m.routeResetConfirm, { n: edges.resettable })}</span>
                  <button
                    type="button"
                    className="ac-ge-btn ac-ge-btn--danger"
                    autoFocus
                    onClick={() => {
                      setConfirm(false);
                      edges.onResetPaths();
                    }}
                  >
                    {m.routeResetConfirmYes}
                  </button>
                  <button type="button" className="ac-ge-btn" onClick={() => setConfirm(false)}>
                    {m.tidyCancel}
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  className="ac-ge-btn"
                  disabled={readOnly}
                  onClick={() => {
                    if (edges.resettable === 0) setNote(m.routeResetNothing);
                    else {
                      setNote("");
                      setConfirm(true);
                    }
                  }}
                >
                  {m.edgeLayoutResetPath}
                </button>
              )}
            </div>
          </>
        )}
        {nodes !== undefined && (
          <div className="ac-ge-lp-row" role="group" aria-label={m.nodeLayoutDirection}>
            <span>{m.nodeLayoutDirection}</span>
            <span className="ac-ge-lp-field ac-ge-dir-group">
              {Object.keys(nodes.directions).map((id) => {
                const out = nodes.directions[id]?.out;
                return (
                  <button key={id} type="button" className="ac-ge-btn" aria-pressed={nodes.direction === id} aria-label={dirTitle(id)} title={dirTitle(id)} disabled={readOnly} onClick={() => nodes.onDirection(id)}>
                    <span aria-hidden="true">{out === undefined ? id : SIDE_GLYPH[out]}</span>
                  </button>
                );
              })}
              <button type="button" className="ac-ge-btn" aria-pressed={nodes.direction === AUTO_DIRECTION} title={m.nodeLayoutAutoDirectionHint} disabled={readOnly} onClick={() => nodes.onDirection(AUTO_DIRECTION)}>
                {dirTitle(AUTO_DIRECTION)}
              </button>
              <button type="button" className="ac-ge-btn" aria-pressed={nodes.direction === ""} disabled={readOnly} onClick={() => nodes.onDirection(null)}>
                {m.nodeLayoutInherit}
              </button>
            </span>
            {nodes.direction === null && <span className="ac-ge-lp-note">{m.multiLayoutMixed}</span>}
          </div>
        )}
        <div className="ac-ge-sr-only" role="status" aria-live="polite">
          {note}
        </div>
        {note !== "" && <p className="ac-ge-lp-note">{note}</p>}
      </div>
    </section>
  );
}
