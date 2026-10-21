/**
 * 연결 패널의 "모양·경로" 섹션(graph-edges §2.5). 데이터와 콜백을 props로만 받는 표현 컴포넌트다.
 * 모양 목록은 `shapes`(레지스트리), 어떤 입력을 보일지는 모양의 `supports*` 속성만 본다.
 * 값이 상속 중이면 입력은 placeholder + "상속" 배지로 보이고, 사용자가 건드린 키만 `layout`에 남는다.
 */
import { useId, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import type { EdgeLayout } from "@agent-console/contracts";
import { DEFAULT_BEND, DEFAULT_EDGE_RADIUS, MAX_EDGE_RADIUS, MAX_WAYPOINTS } from "../logic/edgePath";
import {
  RESET_LABEL_PATCH,
  RESET_PATH_PATCH,
  applyEdgeLayoutPatch,
  changedLayoutKeys,
  insertWaypoint,
  moveWaypoint,
  removeWaypoint,
  reorderWaypoint,
} from "../logic/edgeLayoutOps";
import type { EdgeLayoutPatch } from "../logic/edgeLayoutOps";
import type { Point } from "../logic/ops";
import { defaultMessages, format } from "../messages";
import type { GraphEditorMessages } from "../messages";
import type { EdgeShapeDescriptor } from "../shapes/types";

export interface EdgeLayoutPanelProps {
  /** 엣지의 `layout`(없으면 모두 상속) */
  layout: EdgeLayout | null | undefined;
  /** 모양 레지스트리 목록(표시 순서) */
  shapes: readonly EdgeShapeDescriptor[];
  /** 엣지 층을 뺀 상속 결과 모양("상속 (현재: …)" 표시) */
  inheritedShape: EdgeShapeDescriptor;
  /** [+ 추가]가 만들 경유점의 기본 위치(보통 두 노드 사이). 생략하면 마지막 경유점 옆 */
  newWaypoint?: Point;
  readOnly?: boolean;
  messages?: GraphEditorMessages;
  /** 정리된 새 `layout`(전부 기본이면 `null` = `layout` 키 삭제). 값 변경 1회 = 호출 1회 */
  onChange: (next: EdgeLayout | null) => void;
  className?: string;
}

interface NumberFieldProps {
  label: string;
  value: number | undefined;
  placeholder: number;
  min?: number;
  max?: number;
  step: number;
  /** Shift+↑↓로 움직일 크기(생략 = step) */
  bigStep?: number;
  inherited: boolean;
  inheritedBadge: string;
  disabled?: boolean;
  /** `undefined`는 값을 지움(상속으로 돌아감) */
  onCommit: (v: number | undefined) => void;
}

/** blur/Enter에서 한 번만 확정하는 숫자 입력. 빈 칸 확정 = 상속으로 되돌림. */
function NumberField(p: NumberFieldProps): ReactNode {
  const { value } = p;
  const [text, setText] = useState(value === undefined ? "" : String(value));
  // 바깥 값이 바뀌면(다른 곳에서 고침·초기화) 입력 문자열을 그 값으로 맞춘다(렌더 중 파생 상태 갱신)
  const [seen, setSeen] = useState(value);
  if (seen !== value) {
    setSeen(value);
    setText(value === undefined ? "" : String(value));
  }
  const commit = (): void => {
    const trimmed = text.trim();
    if (trimmed === "") {
      if (value !== undefined) p.onCommit(undefined);
      return;
    }
    const n = Number(trimmed);
    if (!Number.isFinite(n)) {
      setText(value === undefined ? "" : String(value));
      return;
    }
    const clamped = Math.min(p.max ?? Number.POSITIVE_INFINITY, Math.max(p.min ?? Number.NEGATIVE_INFINITY, n));
    setText(String(clamped));
    if (clamped !== value) p.onCommit(clamped);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === "Enter") {
      e.preventDefault();
      commit();
    } else if (e.shiftKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
      e.preventDefault();
      const base = Number(text) || (value ?? p.placeholder);
      const next = base + (e.key === "ArrowUp" ? 1 : -1) * (p.bigStep ?? p.step);
      setText(String(Math.min(p.max ?? Number.POSITIVE_INFINITY, Math.max(p.min ?? Number.NEGATIVE_INFINITY, next))));
    }
  };
  return (
    <span className="ac-ge-lp-field">
      <input
        type="number"
        className="ac-ge-lp-input"
        aria-label={p.label}
        value={text}
        placeholder={String(p.placeholder)}
        {...(p.min !== undefined ? { min: p.min } : {})}
        {...(p.max !== undefined ? { max: p.max } : {})}
        step={p.step}
        disabled={p.disabled === true}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={onKeyDown}
      />
      {p.inherited && <span className="ac-ge-lp-badge">{p.inheritedBadge}</span>}
    </span>
  );
}

const WAYPOINT_STEP = 8;
const WAYPOINT_BIG_STEP = 32;

export function EdgeLayoutPanel(props: EdgeLayoutPanelProps): ReactNode {
  const { layout, shapes, inheritedShape, readOnly = false, onChange } = props;
  const m = props.messages ?? defaultMessages;
  const uid = useId();
  const [open, setOpen] = useState(true);
  const wps: readonly Point[] = layout?.waypoints ?? [];
  const known = layout?.shape ? shapes.find((s) => s.id === layout.shape) : undefined;
  const unknownId = layout?.shape && known === undefined ? layout.shape : undefined;
  const effective = known ?? inheritedShape;
  const patch = (p: EdgeLayoutPatch): void => onChange(applyEdgeLayoutPatch(layout, p));
  const setWaypoints = (next: Point[]): void => patch({ waypoints: next });
  const changed = changedLayoutKeys(layout);
  const changedItems = [...new Set(changed.map((k) => format(m.edgeLayoutChangedLabels[k] ?? k, { n: wps.length })))];
  const atLimit = wps.length >= MAX_WAYPOINTS;

  const addWaypoint = (): void => {
    if (atLimit) return;
    const last = wps[wps.length - 1];
    const at = props.newWaypoint ?? (last !== undefined ? { x: last.x + WAYPOINT_BIG_STEP, y: last.y + WAYPOINT_BIG_STEP } : { x: 0, y: 0 });
    const next = insertWaypoint(wps, wps.length, at);
    if (next !== null) setWaypoints(next);
  };

  return (
    <section className={["ac-ge-lp", props.className].filter(Boolean).join(" ")} aria-labelledby={`${uid}-h`}>
      <h3 className="ac-ge-lp-head" id={`${uid}-h`}>
        <button type="button" className="ac-ge-lp-toggle" aria-expanded={open} aria-controls={`${uid}-body`} onClick={() => setOpen(!open)}>
          <span aria-hidden="true">{open ? "▾" : "▸"}</span> {m.edgeLayoutTitle}
        </button>
      </h3>
      {open && (
        <div className="ac-ge-lp-body" id={`${uid}-body`}>
          <div className="ac-ge-lp-row">
            <label htmlFor={`${uid}-shape`}>{m.edgeLayoutShape}</label>
            <span className="ac-ge-lp-field">
              <select
                id={`${uid}-shape`}
                className="ac-ge-lp-input"
                value={layout?.shape ?? ""}
                disabled={readOnly}
                aria-invalid={unknownId !== undefined ? true : undefined}
                onChange={(e) => patch({ shape: e.target.value === "" ? null : e.target.value })}
              >
                <option value="">{format(m.shapeInherited, { title: inheritedShape.title })}</option>
                {shapes.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title}
                  </option>
                ))}
                {unknownId !== undefined && <option value={unknownId}>{format(m.unknownShape, { id: unknownId })}</option>}
              </select>
              <svg className="ac-ge-lp-preview" width="24" height="10" viewBox="0 0 24 10" aria-hidden="true" focusable="false">
                <path d={effective.preview} fill="none" stroke="currentColor" strokeWidth="1.5" />
              </svg>
            </span>
          </div>

          {effective.supportsRadius && (
            <div className="ac-ge-lp-row">
              <span>{m.edgeLayoutRadius}</span>
              <NumberField
                label={m.edgeLayoutRadius}
                value={layout?.radius ?? undefined}
                placeholder={DEFAULT_EDGE_RADIUS}
                min={0}
                max={MAX_EDGE_RADIUS}
                step={1}
                inherited={layout?.radius === undefined || layout.radius === null}
                inheritedBadge={m.edgeLayoutInheritedBadge}
                disabled={readOnly}
                onCommit={(v) => patch({ radius: v ?? null })}
              />
            </div>
          )}

          {effective.supportsBend && wps.length === 0 && (
            <div className="ac-ge-lp-row">
              <span>{m.edgeLayoutBend}</span>
              <NumberField
                label={m.edgeLayoutBend}
                value={typeof layout?.bend === "number" ? Math.round(layout.bend * 100) : undefined}
                placeholder={Math.round(DEFAULT_BEND * 100)}
                min={0}
                max={100}
                step={5}
                inherited={typeof layout?.bend !== "number"}
                inheritedBadge={m.edgeLayoutInheritedBadge}
                disabled={readOnly}
                onCommit={(v) => patch({ bend: v === undefined ? null : v / 100 })}
              />
            </div>
          )}

          {effective.supportsWaypoints ? (
            <div className="ac-ge-lp-wps">
              <div className="ac-ge-lp-row">
                <span id={`${uid}-wps`}>{format(m.edgeLayoutWaypoints, { n: wps.length, max: MAX_WAYPOINTS })}</span>
                <button
                  type="button"
                  className="ac-ge-btn"
                  disabled={readOnly || atLimit}
                  title={atLimit ? format(m.waypointLimit, { max: MAX_WAYPOINTS }) : undefined}
                  onClick={addWaypoint}
                >
                  {m.edgeLayoutAddWaypoint}
                </button>
              </div>
              <ol className="ac-ge-lp-list" aria-labelledby={`${uid}-wps`}>
                {wps.map((w, i) => (
                  <li key={i} className="ac-ge-lp-wp" data-testid={`waypoint-row-${i + 1}`}>
                    <span className="ac-ge-lp-wp-index">{i + 1}</span>
                    <NumberField
                      label={`${format(m.edgeLayoutWaypointRow, { i: i + 1 })} x`}
                      value={w.x}
                      placeholder={0}
                      step={WAYPOINT_STEP}
                      bigStep={WAYPOINT_BIG_STEP}
                      inherited={false}
                      inheritedBadge=""
                      disabled={readOnly}
                      onCommit={(v) => setWaypoints(moveWaypoint(wps, i, { x: v ?? w.x, y: w.y }))}
                    />
                    <NumberField
                      label={`${format(m.edgeLayoutWaypointRow, { i: i + 1 })} y`}
                      value={w.y}
                      placeholder={0}
                      step={WAYPOINT_STEP}
                      bigStep={WAYPOINT_BIG_STEP}
                      inherited={false}
                      inheritedBadge=""
                      disabled={readOnly}
                      onCommit={(v) => setWaypoints(moveWaypoint(wps, i, { x: w.x, y: v ?? w.y }))}
                    />
                    <button type="button" className="ac-ge-btn" disabled={readOnly || i === 0} aria-label={format(m.edgeLayoutMoveUp, { i: i + 1 })} onClick={() => setWaypoints(reorderWaypoint(wps, i, i - 1))}>
                      {m.edgeLayoutMoveUpText}
                    </button>
                    <button type="button" className="ac-ge-btn" disabled={readOnly || i === wps.length - 1} aria-label={format(m.edgeLayoutMoveDown, { i: i + 1 })} onClick={() => setWaypoints(reorderWaypoint(wps, i, i + 1))}>
                      {m.edgeLayoutMoveDownText}
                    </button>
                    <button type="button" className="ac-ge-btn" disabled={readOnly} aria-label={format(m.edgeLayoutRemove, { i: i + 1 })} onClick={() => setWaypoints(removeWaypoint(wps, i))}>
                      {m.edgeLayoutRemoveText}
                    </button>
                  </li>
                ))}
              </ol>
            </div>
          ) : (
            wps.length > 0 && <p className="ac-ge-lp-note">{format(m.edgeLayoutWaypointsIgnored, { n: wps.length })}</p>
          )}

          <div className="ac-ge-lp-row">
            <span>{m.edgeLayoutLabelPos}</span>
            <NumberField
              label={m.edgeLayoutLabelPos}
              value={typeof layout?.label_t === "number" ? Math.round(layout.label_t * 100) : undefined}
              placeholder={50}
              min={10}
              max={90}
              step={5}
              inherited={typeof layout?.label_t !== "number"}
              inheritedBadge={m.edgeLayoutInheritedBadge}
              disabled={readOnly}
              onCommit={(v) => patch({ label_t: v === undefined ? null : v / 100 })}
            />
            <button type="button" className="ac-ge-btn" disabled={readOnly} onClick={() => patch(RESET_LABEL_PATCH)}>
              {m.edgeLayoutResetLabel}
            </button>
          </div>

          <div className="ac-ge-lp-row">
            <button type="button" className="ac-ge-btn" disabled={readOnly} onClick={() => patch(RESET_PATH_PATCH)}>
              {m.edgeLayoutResetPath}
            </button>
            <button type="button" className="ac-ge-btn" disabled={readOnly} onClick={() => onChange(null)}>
              {m.edgeLayoutResetAll}
            </button>
          </div>
          {changedItems.length > 0 && <p className="ac-ge-lp-note">{format(m.edgeLayoutChanged, { items: changedItems.join(", ") })}</p>}
        </div>
      )}
    </section>
  );
}
