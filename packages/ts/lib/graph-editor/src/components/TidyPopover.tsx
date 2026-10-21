/**
 * [정리 ▾] 팝오버(graph-edges §4.1). 데이터와 콜백을 props로만 받는 표현 컴포넌트다.
 * 엔진 목록·옵션은 `LayoutEngineDescriptor` 선언에서, 방향은 방향 어휘 표에서, 모양은 모양 목록에서, 연결 종류는 `edgeKinds`에서 그린다.
 * 계산은 `compute`가 한다(편집기가 엔진을 돌려 결과를 돌려줌). 팝오버는 진행·취소·시간 제한·실패·재시도와
 * "미리보기 / 적용 1회" 호출만 책임진다. 적용 전에는 어떤 그래프 변경도 만들지 않는다.
 */
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { coerceOptionValues } from "../layout/types";
import type { LayoutEngineDescriptor, OptionDecl, OptionValues } from "../layout/types";
import { SIDE_GLYPH } from "../logic/layout";
import { fitShift, intersectRects } from "../logic/popoverFit";
import type { FitRect } from "../logic/popoverFit";
import type { DirectionSides } from "../logic/layout";
import { defaultMessages, format } from "../messages";
import type { GraphEditorMessages } from "../messages";
import type { EdgeShapeDescriptor } from "../shapes/types";

/** 팝오버가 편집하는 값 전체. 기억할 값(엔진 옵션 등)과 적용 때 그래프에 쓰는 값(방향·모양)이 섞여 있다. */
export interface TidyValues {
  engineId: string;
  /** 엔진 id → 옵션 값 */
  optionsByEngine: Readonly<Record<string, OptionValues>>;
  /** 방향 id */
  direction: string;
  scope: "all" | "selected";
  /** 그래프 기본 모양 id. 빈 문자열 = 상속(지움) */
  edgeShape: string;
  /** 종류 id → 모양 id(빈 문자열 = 상속) */
  shapeByKind: Readonly<Record<string, string>>;
  resetRoutes: boolean;
  alignNodes: boolean;
  /** 종류 id → 배치에 쓸지(빠진 키 = 씀) */
  kinds: Readonly<Record<string, boolean>>;
}

export interface TidyEdgeKind {
  id: string;
  title: string;
}

export interface TidyPopoverProps<R> {
  engines: readonly LayoutEngineDescriptor[];
  directions: DirectionSides;
  shapes: readonly EdgeShapeDescriptor[];
  edgeKinds: readonly TidyEdgeKind[];
  initial: TidyValues;
  nodeCount: number;
  selectedCount: number;
  /** 초기화 대상 연결선 수(0이면 [모든 연결선 경로 초기화]가 안내만 한다) */
  pathCount: number;
  /** 계산. `signal`이 중단되면(취소·시간 초과) 멈추고 거부한다 */
  compute: (values: TidyValues, signal: AbortSignal) => Promise<R>;
  /** 미리보기 결과를 보여 준다(`null` = 해제) */
  onPreview: (result: R | null) => void;
  /** [적용]: 결과를 반영한다. 한 번 호출 */
  onApply: (result: R, values: TidyValues) => void;
  /** [모든 연결선 경로 초기화]를 확인한 뒤 호출 */
  onResetAllRoutes: () => void;
  onClose: () => void;
  /** 값이 바뀔 때(마지막 값 기억용) */
  onValuesChange?: (values: TidyValues) => void;
  /** 계산 중 여부가 바뀔 때(캔버스 진행 바용) */
  onRunningChange?: (running: boolean) => void;
  /** 한 번의 계산 제한 시간(ms). 기본 10000 */
  timeoutMs?: number;
  messages?: GraphEditorMessages;
  className?: string;
}

export const TIDY_TIMEOUT_MS = 10_000;

type Action = "preview" | "apply";

const isAbort = (e: unknown): boolean => e instanceof Error && e.name === "AbortError";
const textOf = (e: unknown): string => (e instanceof Error && e.message !== "" ? e.message : String(e));

/** 저장돼 있던 값을 현재 선언에 맞게 정리한다(모르는 엔진·방향·모양·범위 밖 숫자는 기본으로). */
export function normalizeTidyValues(raw: Partial<TidyValues> | null | undefined, base: TidyValues, engines: readonly LayoutEngineDescriptor[]): TidyValues {
  const r = raw ?? {};
  const engineId = engines.some((e) => e.id === r.engineId) ? (r.engineId as string) : (engines.find((e) => e.id === base.engineId)?.id ?? engines[0]?.id ?? base.engineId);
  const optionsByEngine: Record<string, OptionValues> = {};
  for (const e of engines) optionsByEngine[e.id] = coerceOptionValues(e.options, r.optionsByEngine?.[e.id] ?? base.optionsByEngine[e.id]);
  const bool = (v: unknown, d: boolean): boolean => (typeof v === "boolean" ? v : d);
  return {
    ...base,
    engineId,
    optionsByEngine,
    scope: r.scope === "selected" || r.scope === "all" ? r.scope : base.scope,
    resetRoutes: bool(r.resetRoutes, base.resetRoutes),
    alignNodes: bool(r.alignNodes, base.alignNodes),
    kinds: Object.fromEntries(Object.entries(r.kinds ?? base.kinds).filter(([, v]) => typeof v === "boolean")) as Record<string, boolean>,
  };
}

function OptionControl({ decl, value, onChange, disabled }: { decl: OptionDecl; value: string | number | boolean; onChange: (v: string | number | boolean) => void; disabled: boolean }) {
  const id = useId();
  if (decl.type === "boolean") {
    return (
      <label className="ac-ge-tidy-row ac-ge-check">
        <input type="checkbox" checked={value === true} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
        <span>{decl.title}</span>
      </label>
    );
  }
  return (
    <div className="ac-ge-tidy-row">
      <label htmlFor={id} className="ac-ge-tidy-label">
        {decl.title}
      </label>
      {decl.type === "enum" ? (
        <select id={id} className="ac-ge-select" value={String(value)} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
          {(decl.choices ?? []).map((c) => (
            <option key={c.value} value={c.value}>
              {c.title}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          className="ac-ge-input ac-ge-tidy-number"
          type="number"
          value={typeof value === "number" ? value : ""}
          min={decl.min}
          max={decl.max}
          step={decl.step}
          disabled={disabled}
          onChange={(e) => {
            const n = e.target.valueAsNumber;
            if (Number.isFinite(n)) onChange(n);
          }}
        />
      )}
    </div>
  );
}

export function TidyPopover<R>(props: TidyPopoverProps<R>): ReactNode {
  const { engines, directions, shapes, edgeKinds, nodeCount, selectedCount, pathCount, compute, onPreview, onApply, onResetAllRoutes, onClose } = props;
  const m = props.messages ?? defaultMessages;
  const uid = useId();
  const [values, setValues] = useState<TidyValues>(props.initial);
  const [running, setRunning] = useState<Action | null>(null);
  const [error, setError] = useState<{ reason: string; action: Action } | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [status, setStatus] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const cache = useRef<{ key: string; result: R } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const timeoutMs = props.timeoutMs ?? TIDY_TIMEOUT_MS;
  const latest = useRef(props);
  useEffect(() => {
    latest.current = props;
  });

  // 팝오버가 잘리지 않게, 열 때 뷰포트·overflow 클리핑 조상·가장 가까운 캔버스 영역의 교집합 안으로 민다(UX A20)
  useLayoutEffect(() => {
    const el = rootRef.current;
    if (el === null) return;
    const rects: FitRect[] = [{ left: 0, top: 0, right: document.documentElement.clientWidth, bottom: document.documentElement.clientHeight }];
    for (let p = el.parentElement; p !== null && p !== document.body; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (cs.overflowX !== "visible" || cs.overflowY !== "visible") rects.push(p.getBoundingClientRect());
    }
    const canvas = el.closest(".ac-ge-canvas");
    if (canvas !== null) rects.push(canvas.getBoundingClientRect());
    const bounds = intersectRects(rects);
    if (bounds === null) return;
    const edge = 8;
    // 경계보다 키가 크면 줄여 안쪽 스크롤로 보이게 한다
    const room = bounds.bottom - bounds.top - 2 * edge;
    if (room > 0 && el.getBoundingClientRect().height > room) el.style.maxHeight = `${room}px`;
    const roomW = bounds.right - bounds.left - 2 * edge;
    if (roomW > 0 && el.getBoundingClientRect().width > roomW) el.style.maxWidth = `${roomW}px`;
    const { x, y } = fitShift(el.getBoundingClientRect(), bounds, edge);
    if (x !== 0 || y !== 0) el.style.translate = `${x}px ${y}px`;
  }, []);

  useEffect(() => {
    rootRef.current?.querySelector<HTMLElement>("input, select, button")?.focus();
    return () => abortRef.current?.abort();
  }, []);

  const engine = engines.find((e) => e.id === values.engineId) ?? engines[0];
  const needNodes = values.scope === "selected" ? selectedCount : nodeCount;
  const blocked = needNodes < 2 || engine === undefined;
  const dirIds = Object.keys(directions);
  // 엔진이 권장 모양을 선언했고 그 모양이 목록에 있을 때만 "연결선도 자동 경로로" 체크를 둔다
  const shapeOption = engine?.edgeShapeOption !== undefined && shapes.some((s) => s.id === engine.edgeShapeOption?.shapeId) ? engine.edgeShapeOption : undefined;

  const change = (patch: Partial<TidyValues>): void => {
    const next = { ...values, ...patch };
    setValues(next);
    props.onValuesChange?.(next);
    cache.current = null;
    if (previewing) {
      setPreviewing(false);
      onPreview(null);
    }
    if (error !== null) setError(null);
  };

  const run = async (action: Action): Promise<void> => {
    if (blocked || running !== null) return;
    const key = JSON.stringify(values);
    setError(null);
    if (cache.current?.key === key) {
      finish(action, cache.current.result);
      return;
    }
    const ctl = new AbortController();
    abortRef.current = ctl;
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      ctl.abort();
    }, timeoutMs);
    setRunning(action);
    latest.current.onRunningChange?.(true);
    try {
      const result = await compute(values, ctl.signal);
      if (ctl.signal.aborted) throw Object.assign(new Error("aborted"), { name: "AbortError" });
      cache.current = { key, result };
      finish(action, result);
    } catch (e) {
      if (isAbort(e) || ctl.signal.aborted) {
        if (timedOut) setError({ reason: format(m.tidyTimeout, { sec: Math.round(timeoutMs / 1000) }), action });
        else setStatus(m.tidyCancelled);
      } else setError({ reason: textOf(e), action });
    } finally {
      clearTimeout(timer);
      if (abortRef.current === ctl) abortRef.current = null;
      setRunning(null);
      latest.current.onRunningChange?.(false);
    }
  };

  const finish = (action: Action, result: R): void => {
    if (action === "preview") {
      setPreviewing(true);
      setStatus(m.tidyPreviewShown);
      onPreview(result);
    } else onApply(result, values);
  };

  const cancel = (): void => {
    if (abortRef.current !== null) abortRef.current.abort();
    else onClose();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      if (confirmReset) setConfirmReset(false);
      else cancel();
    } else if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.altKey && e.target instanceof HTMLElement && !["BUTTON", "TEXTAREA", "A"].includes(e.target.tagName)) {
      e.preventDefault();
      void run("apply");
    }
    if (e.key !== "Tab") e.stopPropagation(); // 캔버스 단축키(R·S·X·Delete 등)가 팝오버 안에서 동작하지 않게
  };

  const reasonId = `${uid}-reason`;
  const optionValues = engine === undefined ? {} : (values.optionsByEngine[engine.id] ?? {});

  return (
    <div ref={rootRef} className={["ac-ge-tidy", props.className].filter(Boolean).join(" ")} role="dialog" aria-label={m.tidyTitle} onKeyDown={onKeyDown}>
      <div className="ac-ge-tidy-head">
        <strong>{m.tidyTitle}</strong>
        <button type="button" className="ac-ge-btn" aria-label={m.tidyClose} onClick={onClose}>
          ×
        </button>
      </div>
      <fieldset className="ac-ge-tidy-group" disabled={running !== null}>
        <legend className="ac-ge-tidy-legend">{m.tidyDirection}</legend>
        <div className="ac-ge-tidy-dirs" role="radiogroup" aria-label={m.tidyDirection}>
          {dirIds.map((id) => {
            const out = directions[id]?.out;
            return (
              <button
                key={id}
                type="button"
                role="radio"
                aria-checked={values.direction === id}
                className="ac-ge-btn"
                title={m.directionLabels[id] ?? id}
                aria-label={m.directionLabels[id] ?? id}
                onClick={() => change({ direction: id })}
              >
                {out === undefined ? id : SIDE_GLYPH[out]}
              </button>
            );
          })}
        </div>
        <div className="ac-ge-tidy-row" role="radiogroup" aria-label={m.tidyScope}>
          <span className="ac-ge-tidy-label">{m.tidyScope}</span>
          <label className="ac-ge-check">
            <input type="radio" name={`${uid}-scope`} checked={values.scope === "all"} onChange={() => change({ scope: "all" })} />
            <span>{m.tidyScopeAll}</span>
          </label>
          <label className="ac-ge-check">
            <input type="radio" name={`${uid}-scope`} checked={values.scope === "selected"} disabled={selectedCount < 1} onChange={() => change({ scope: "selected" })} />
            <span>{format(m.tidyScopeSelected, { n: selectedCount })}</span>
          </label>
        </div>
        {engine !== undefined && (
          <>
            <div className="ac-ge-tidy-sep">{m.tidyEngineOptions}</div>
            {engines.length > 1 && (
              <div className="ac-ge-tidy-row">
                <label htmlFor={`${uid}-engine`} className="ac-ge-tidy-label">
                  {m.tidyEngine}
                </label>
                <select id={`${uid}-engine`} className="ac-ge-select" value={engine.id} onChange={(e) => change({ engineId: e.target.value })}>
                  {engines.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.title}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {engine.options.map((o) => (
              <OptionControl
                key={`${engine.id}:${o.key}`}
                decl={o}
                value={optionValues[o.key] ?? o.default}
                disabled={false}
                onChange={(v) => change({ optionsByEngine: { ...values.optionsByEngine, [engine.id]: { ...optionValues, [o.key]: v } } })}
              />
            ))}
          </>
        )}
        <div className="ac-ge-tidy-sep">{m.tidyEdges}</div>
        <div className="ac-ge-tidy-row">
          <label htmlFor={`${uid}-shape`} className="ac-ge-tidy-label">
            {m.tidyDefaultShape}
          </label>
          <select id={`${uid}-shape`} className="ac-ge-select" value={values.edgeShape} onChange={(e) => change({ edgeShape: e.target.value })}>
            <option value="">{m.tidyShapeInherit}</option>
            {shapes.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title}
              </option>
            ))}
          </select>
        </div>
        {shapeOption !== undefined && (
          <label className="ac-ge-tidy-row ac-ge-check">
            <input
              type="checkbox"
              checked={values.edgeShape === shapeOption.shapeId}
              onChange={(e) => change({ edgeShape: e.target.checked ? shapeOption.shapeId : "" })}
            />
            <span>{shapeOption.title ?? m.tidyAutoRoutes}</span>
          </label>
        )}
        {edgeKinds.length > 0 && (
          <div className="ac-ge-tidy-kinds" role="group" aria-label={m.tidyShapeByKind}>
            <span className="ac-ge-tidy-label">{m.tidyShapeByKind}</span>
            {edgeKinds.map((k) => (
              <div key={k.id} className="ac-ge-tidy-row">
                <label htmlFor={`${uid}-kind-${k.id}`} className="ac-ge-tidy-kind ac-ellipsis" title={k.title}>
                  {k.title}
                </label>
                <select
                  id={`${uid}-kind-${k.id}`}
                  className="ac-ge-select"
                  value={values.shapeByKind[k.id] ?? ""}
                  onChange={(e) => change({ shapeByKind: { ...values.shapeByKind, [k.id]: e.target.value } })}
                >
                  <option value="">{m.tidyShapeInherit}</option>
                  {shapes.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.title}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        )}
        <label className="ac-ge-tidy-row ac-ge-check">
          <input type="checkbox" checked={values.resetRoutes} onChange={(e) => change({ resetRoutes: e.target.checked })} />
          <span>{m.tidyResetRoutes}</span>
        </label>
        <label className="ac-ge-tidy-row ac-ge-check">
          <input type="checkbox" checked={values.alignNodes} onChange={(e) => change({ alignNodes: e.target.checked })} />
          <span>{m.tidyAlignNodes}</span>
        </label>
        {edgeKinds.length > 0 && (
          <div className="ac-ge-tidy-kinds" role="group" aria-label={m.tidyKinds}>
            <span className="ac-ge-tidy-label">{m.tidyKinds}</span>
            <div className="ac-ge-tidy-checks">
              {edgeKinds.map((k) => (
                <label key={k.id} className="ac-ge-check">
                  <input type="checkbox" checked={values.kinds[k.id] !== false} onChange={(e) => change({ kinds: { ...values.kinds, [k.id]: e.target.checked } })} />
                  <span>{k.title}</span>
                </label>
              ))}
            </div>
          </div>
        )}
      </fieldset>
      <div className="ac-ge-tidy-reset">
        {confirmReset ? (
          <div role="alertdialog" aria-label={m.tidyResetAllRoutes} className="ac-ge-tidy-confirm">
            <span>{format(m.routeResetConfirm, { n: pathCount })}</span>
            <button
              type="button"
              className="ac-ge-btn ac-ge-btn--danger"
              autoFocus
              onClick={() => {
                setConfirmReset(false);
                onResetAllRoutes();
              }}
            >
              {m.routeResetConfirmYes}
            </button>
            <button type="button" className="ac-ge-btn" onClick={() => setConfirmReset(false)}>
              {m.tidyCancel}
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="ac-ge-btn"
            disabled={running !== null}
            onClick={() => {
              if (pathCount === 0) setStatus(m.routeResetNothing);
              else setConfirmReset(true);
            }}
          >
            {m.tidyResetAllRoutes}
          </button>
        )}
      </div>
      {error !== null && (
        <div className="ac-ge-tidy-error" role="alert">
          <span>{format(m.tidyFailed, { reason: error.reason })}</span>
          <button type="button" className="ac-ge-btn" onClick={() => void run(error.action)}>
            {m.tidyRetry}
          </button>
        </div>
      )}
      {blocked && (
        <div id={reasonId} className="ac-ge-tidy-hint">
          {m.tidyNeedTwoNodes}
        </div>
      )}
      <div className="ac-ge-sr-only" role="status" aria-live="polite">
        {running !== null ? m.tidyRunning : status}
      </div>
      <div className="ac-ge-tidy-actions">
        <button
          type="button"
          className="ac-ge-btn"
          aria-pressed={previewing}
          disabled={blocked || (running !== null && running !== "preview")}
          aria-busy={running === "preview" || undefined}
          aria-describedby={blocked ? reasonId : undefined}
          onClick={() => {
            if (previewing) {
              setPreviewing(false);
              onPreview(null);
            } else void run("preview");
          }}
        >
          {previewing ? m.tidyPreviewOff : m.tidyPreview}
        </button>
        <span className="ac-ge-tidy-spacer" />
        <button type="button" className="ac-ge-btn" onClick={cancel}>
          {m.tidyCancel}
        </button>
        <button
          type="button"
          className="ac-ge-btn ac-ge-btn--primary"
          disabled={blocked || (running !== null && running !== "apply")}
          aria-busy={running === "apply" || undefined}
          aria-describedby={blocked ? reasonId : undefined}
          title={blocked ? m.tidyNeedTwoNodes : undefined}
          onClick={() => void run("apply")}
        >
          {running === "apply" ? m.tidyRunning : m.tidyApply}
        </button>
      </div>
    </div>
  );
}
