import { useId, useMemo, type ReactNode } from "react";
import type { LogDimensionInfo, LogMetricInfo, LogWidget } from "@agent-console/contracts/logs";
import { fmt, mergeMessages, type DeepPartial, type LogViewMessages } from "./messages";
import { MAX_WIDGET_H, MAX_WIDGET_W, MIN_WIDGET_H, MIN_WIDGET_W, widgetSize } from "./layout";
import { validateQuery, type JsonSchema, type WidgetDescriptor } from "./widgets/registry";

export interface WidgetEditorProps {
  value: LogWidget;
  onChange: (next: LogWidget) => void;
  /** 선택 가능한 위젯 종류(레지스트리 목록). */
  descriptors: readonly WidgetDescriptor[];
  /** 서버 목록(`GET /logs/schema`). 없으면(undefined) 자유 입력 콤보박스로 바뀐다. */
  dimensions?: readonly LogDimensionInfo[] | undefined;
  metrics?: readonly LogMetricInfo[] | undefined;
  /** 필터 편집(앱이 `LogFilterBar` 압축형을 주입). */
  filterBar?: ReactNode;
  /** 종류별 표시 옵션 폼(앱이 SchemaForm을 주입). 없으면 영역 숨김. */
  renderOptionsForm?: (schema: JsonSchema, value: Record<string, unknown>, onChange: (next: Record<string, unknown>) => void) => ReactNode;
  /** 미리보기 영역(앱이 집계를 호출해 `descriptor.render`로 그림). */
  preview?: ReactNode;
  /** 서버 검증 오류 등 외부에서 받은 메시지. */
  errors?: readonly string[];
  onApply: (widget: LogWidget) => void;
  onCancel: () => void;
  messages?: DeepPartial<LogViewMessages>;
}

/** 질의·종류 검증 결과 문구 목록. 비어 있으면 적용 가능. */
export function validateWidget(widget: LogWidget, descriptor: WidgetDescriptor | undefined, dimensions: readonly LogDimensionInfo[] | undefined, m: LogViewMessages): string[] {
  const out: string[] = [];
  if (!descriptor) out.push(m.editorKindRequired);
  if (!widget.query.metric.trim()) out.push(m.editorMetricRequired);
  if (descriptor) {
    const times = dimensions ? new Set(dimensions.filter((d) => d.kind === "time").map((d) => d.id)) : undefined;
    const r = validateQuery(descriptor.queryShape, widget.query.group_by ?? [], times);
    if (!r.ok) out.push(r.reason === "count" ? fmt(m.editorGroupByCount, { min: descriptor.queryShape.groupBy.min, max: descriptor.queryShape.groupBy.max }) : m.editorTimeFirst);
  }
  return out;
}

/**
 * 위젯 추가·편집 패널(제어 컴포넌트). 종류는 레지스트리 목록에서, 지표·차원은 서버 목록에서 고른다(없으면 자유 입력).
 * 종류를 바꿔도 맞지 않는 차원은 지우지 않고 오류로 표시한다(되돌릴 수 있게).
 */
export function WidgetEditor(props: WidgetEditorProps) {
  const { value, onChange, descriptors, dimensions, metrics, filterBar, renderOptionsForm, preview, errors = [], onApply, onCancel } = props;
  const m = useMemo(() => mergeMessages(props.messages), [props.messages]);
  const uid = useId();
  const descriptor = descriptors.find((d) => d.kind === value.kind);
  const groupBy = value.query.group_by ?? [];
  const problems = validateWidget(value, descriptor, dimensions, m);
  const size = widgetSize(value, descriptor?.defaultSize);
  const patchQuery = (q: Partial<LogWidget["query"]>) => onChange({ ...value, query: { ...value.query, ...q } });
  const setGroup = (next: string[]) => patchQuery({ group_by: next });
  const options = (value.options ?? {}) as Record<string, unknown>;
  const setOptions = (next: Record<string, unknown>) => onChange({ ...value, options: { ...next, ...(options["w"] !== undefined ? { w: options["w"] } : {}), ...(options["h"] !== undefined ? { h: options["h"] } : {}) } });
  const freeText = dimensions === undefined;
  const move = (i: number, d: -1 | 1) => {
    const j = i + d;
    if (j < 0 || j >= groupBy.length) return;
    const next = [...groupBy];
    [next[i], next[j]] = [next[j] as string, next[i] as string];
    setGroup(next);
  };
  const dimLabel = (id: string) => dimensions?.find((d) => d.id === id)?.title ?? id;
  const sizeInput = (key: "w" | "h", min: number, max: number, label: string) => (
    <label className="ac-lv-inline">
      {label}
      <input type="number" className="ac-lv-input" min={min} max={max} value={size[key]} onChange={(e) => onChange({ ...value, options: { ...(value.options ?? {}), w: size.w, h: size.h, [key]: Math.min(max, Math.max(min, Number(e.target.value) || min)) } })} />
    </label>
  );

  return (
    <form
      className="ac-lv-editor"
      aria-label={m.editorTitle}
      onSubmit={(e) => {
        e.preventDefault();
        if (problems.length === 0) onApply(value);
      }}
      onKeyDown={(e) => e.key === "Escape" && onCancel()}
    >
      <fieldset>
        <legend>{m.editorKind}</legend>
        <div className="ac-lv-kindlist" role="radiogroup" aria-label={m.editorKind}>
          {descriptors.map((d) => (
            <label key={d.kind} className="ac-lv-kindcard" data-checked={d.kind === value.kind || undefined}>
              <input type="radio" name={`${uid}-kind`} checked={d.kind === value.kind} onChange={() => onChange({ ...value, kind: d.kind })} />
              <strong>{d.title}</strong>
              {d.description ? <span className="ac-lv-muted">{d.description}</span> : null}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="ac-lv-field">
        {m.editorTitleField}
        <input className="ac-lv-input" value={value.title ?? ""} onChange={(e) => onChange({ ...value, title: e.target.value === "" ? null : e.target.value })} />
      </label>
      <label className="ac-lv-field">
        {m.editorMetric}
        {metrics ? (
          <select className="ac-lv-input" value={value.query.metric} onChange={(e) => patchQuery({ metric: e.target.value })}>
            <option value="" />
            {!metrics.some((x) => x.id === value.query.metric) && value.query.metric ? <option value={value.query.metric}>{value.query.metric}</option> : null}
            {metrics.map((x) => (
              <option key={x.id} value={x.id}>
                {x.title ?? x.id}
                {x.unit ? ` (${x.unit})` : ""}
              </option>
            ))}
          </select>
        ) : (
          <input className="ac-lv-input" value={value.query.metric} onChange={(e) => patchQuery({ metric: e.target.value })} aria-describedby={`${uid}-hint`} />
        )}
      </label>
      <fieldset>
        <legend>{m.editorGroupBy}</legend>
        <ol className="ac-lv-dimlist">
          {groupBy.map((g, i) => (
            <li key={`${g}-${i}`} onKeyDown={(e) => { if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) { e.preventDefault(); move(i, e.key === "ArrowUp" ? -1 : 1); } }}>
              <span className="ac-lv-chip" tabIndex={0}>{dimLabel(g)}</span>
              <button type="button" className="ac-lv-iconbtn" aria-label={fmt(m.editorRemoveDimension, { name: dimLabel(g) })} onClick={() => setGroup(groupBy.filter((_, j) => j !== i))}>
                ×
              </button>
            </li>
          ))}
        </ol>
        {freeText ? (
          <AddFreeDimension onAdd={(d) => setGroup([...groupBy, d])} m={m} listId={`${uid}-hint`} />
        ) : (
          <select className="ac-lv-input" aria-label={m.editorAddDimension} value="" onChange={(e) => e.target.value && setGroup([...groupBy, e.target.value])}>
            <option value="">{m.editorAddDimension}</option>
            {dimensions.map((d) => (
              <option key={d.id} value={d.id}>
                {d.title ?? d.id}
              </option>
            ))}
          </select>
        )}
        {freeText ? <p id={`${uid}-hint`} className="ac-lv-muted">{m.editorComboHint} · {m.editorTimeUnknown}</p> : null}
      </fieldset>
      {filterBar ? (
        <fieldset>
          <legend>{m.editorFilter}</legend>
          {filterBar}
        </fieldset>
      ) : null}
      {descriptor && renderOptionsForm ? (
        <fieldset>
          <legend>{m.editorOptions}</legend>
          {renderOptionsForm(descriptor.optionsSchema, options, setOptions)}
          <div className="ac-lv-row-actions">
            {sizeInput("w", MIN_WIDGET_W, MAX_WIDGET_W, m.editorWidth)}
            {sizeInput("h", MIN_WIDGET_H, MAX_WIDGET_H, m.editorHeight)}
          </div>
        </fieldset>
      ) : null}
      {preview ? (
        <section aria-label={m.editorPreview}>
          <h4>{m.editorPreview}</h4>
          {preview}
        </section>
      ) : null}
      {[...problems, ...errors].length > 0 ? (
        <ul className="ac-lv-problems" role="alert">
          {[...problems, ...errors].map((p, i) => (
            <li key={i}>{p}</li>
          ))}
        </ul>
      ) : null}
      <div className="ac-lv-row-actions">
        <button type="button" className="ac-lv-btn" onClick={onCancel}>
          {m.editorCancel}
        </button>
        <button type="submit" className="ac-lv-btn" data-primary disabled={problems.length > 0}>
          {m.editorApply}
        </button>
      </div>
    </form>
  );
}

function AddFreeDimension({ onAdd, m, listId }: { onAdd: (d: string) => void; m: LogViewMessages; listId: string }) {
  return (
    <form
      className="ac-lv-inline"
      onSubmit={(e) => {
        e.preventDefault();
        e.stopPropagation();
        const input = e.currentTarget.elements.namedItem("dim") as HTMLInputElement;
        if (input.value.trim()) {
          onAdd(input.value.trim());
          input.value = "";
        }
      }}
    >
      <input name="dim" className="ac-lv-input" aria-label={m.editorAddDimension} aria-describedby={listId} />
      <button type="submit" className="ac-lv-btn">
        {m.editorAddDimension}
      </button>
    </form>
  );
}
