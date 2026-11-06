/**
 * 값이 문자열 하나, 문자열 목록, 이름 → 문자열 표 중 어느 모양이든 같은 틀로 편집하게 하는 필드 껍데기.
 * 항목 하나를 그리는 일은 `renderItem`이 한다(정규식 칸, 값 고르기, 입력 틀 칸). 모양은 스키마 타입에서 정하고 모르면 값 모양을 본다.
 * 서버 이슈는 `ConfigIssuesProvider`로 들어온 것 중 이 필드 아래 것을 항목 옆(경로 `/<번호|이름>`) 또는 필드 아래에 보인다.
 */
import { useState, type ReactNode } from "react";
import type { SchemaFormFieldProps } from "@agent-console/schema-form";
import { Button } from "@agent-console/ui";
import { resolveRef, unwrapNullable, type SchemaNode } from "../../../lib/schemaTools";
import { useConfigIssuesUnder, type ConfigIssue } from "../../delegation";
import { sddMessages as m } from "../messages";
import "./sddWidgets.css";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

export type FieldShape = "scalar" | "list" | "map";

/** 스키마 타입(없으면 값 모양)에서 값 모양을 정한다. */
export function shapeOf(schema: SchemaNode, root: SchemaNode, value: unknown): FieldShape {
  const type = unwrapNullable(resolveRef(schema, root), root).schema["type"];
  const base = Array.isArray(type) ? type.find((t) => t !== "null") : type;
  if (base === "array") return "list";
  if (base === "object") return "map";
  if (base === "string") return "scalar";
  return Array.isArray(value) ? "list" : isObj(value) ? "map" : "scalar";
}

/** 이 필드의 위치. 폼이 알려 준 값을 먼저, 없으면 `ui:options.$pointer`. */
export const pointerOf = (p: Pick<SchemaFormFieldProps, "pointer" | "options">): string | undefined =>
  p.pointer ?? (typeof p.options["$pointer"] === "string" ? p.options["$pointer"] : undefined);

export const rootOf = (p: Pick<SchemaFormFieldProps, "schema" | "options">): SchemaNode => (isObj(p.options["$rootSchema"]) ? (p.options["$rootSchema"] as SchemaNode) : (p.schema as SchemaNode));

/** 서버 이슈 한 줄들(톤 점 + 글). */
export function IssueLines({ issues, id }: { issues: readonly ConfigIssue[]; id?: string }) {
  if (issues.length === 0) return null;
  return (
    <ul className="sdd-w-issues" id={id}>
      {issues.map((i, idx) => (
        <li key={`${i.path}:${idx}`} data-tone={i.severity === "warning" ? "warning" : "danger"}>{i.message}</li>
      ))}
    </ul>
  );
}

export interface ItemRenderArgs {
  id: string;
  value: string;
  onChange(next: string): void;
  disabled: boolean;
  /** 이 항목에 붙은 서버 이슈가 있는가(`aria-invalid` 용) */
  invalid: boolean;
  describedBy: string | undefined;
  /** 항목 이름(접근성 라벨 보강) */
  label: string;
}

export interface ShapedFieldProps {
  field: SchemaFormFieldProps;
  renderItem(args: ItemRenderArgs): ReactNode;
  /** 항목 아래에 덧붙이는 안내(예: 목록에 없는 값 경고). 비어 있으면 없음 */
  itemNote?(value: string): ReactNode;
  /** 필드 아래에 한 번 붙는 것(변수 칩 등) */
  footer?: ReactNode;
}

const segEscape = (s: string) => s.replace(/~/g, "~0").replace(/\//g, "~1");

export function ShapedField({ field, renderItem, itemNote, footer }: ShapedFieldProps) {
  const { id, value, onChange, label, disabled, readonly } = field;
  const locked = disabled || readonly;
  const root = rootOf(field);
  const shape = shapeOf(field.schema as SchemaNode, root, value);
  const issues = useConfigIssuesUnder(pointerOf(field));
  const [newKey, setNewKey] = useState("");
  const list = Array.isArray(value) ? value.map((v) => (typeof v === "string" ? v : "")) : [];
  const map = isObj(value) ? Object.entries(value).map(([k, v]) => [k, typeof v === "string" ? v : ""] as const) : [];
  const issuesAt = (seg: string) => issues.filter((i) => i.path === `/${seg}` || i.path.startsWith(`/${seg}/`));
  const rowSegs = new Set(shape === "list" ? list.map((_, i) => `/${i}`) : shape === "map" ? map.map(([k]) => `/${segEscape(k)}`) : []);
  const rest = shape === "scalar" ? issues : issues.filter((i) => ![...rowSegs].some((s) => i.path === s || i.path.startsWith(`${s}/`)));
  const noteId = `${id}-issues`;

  const row = (rowId: string, rowLabel: string, val: string, seg: string, set: (v: string) => void, extra?: ReactNode) => {
    const mine = issuesAt(seg);
    const itemIssueId = `${rowId}-issues`;
    return (
      <div className="sdd-w-row" key={rowId}>
        <div className="sdd-w-row-main">
          {extra}
          {renderItem({ id: rowId, value: val, onChange: set, disabled: locked, invalid: mine.some((i) => i.severity !== "warning"), describedBy: mine.length > 0 ? itemIssueId : undefined, label: rowLabel })}
          {itemNote?.(val)}
          <IssueLines issues={mine} id={itemIssueId} />
        </div>
      </div>
    );
  };

  return (
    <div className="sdd-w-field" {...(shape === "scalar" ? {} : { role: "group", "aria-label": label })}>
      <span className="sdd-w-label" aria-hidden={shape === "scalar" || undefined}>{label}</span>
      {shape === "scalar"
        ? (
          <div className="sdd-w-row-main">
            {renderItem({ id, value: typeof value === "string" ? value : "", onChange: (v) => onChange(v === "" ? null : v), disabled: locked, invalid: issues.some((i) => i.severity !== "warning"), describedBy: issues.length > 0 ? noteId : undefined, label })}
            {itemNote?.(typeof value === "string" ? value : "")}
          </div>
        )
        : shape === "list"
          ? (
            <>
              {list.map((v, i) => (
                <div className="sdd-w-line" key={i}>
                  {row(`${id}-${i}`, `${label} ${i + 1}`, v, String(i), (next) => onChange(list.map((x, j) => (j === i ? next : x))))}
                  <Button size="sm" disabled={locked} aria-label={m.widgets.removeItem(`${label} ${i + 1}`)} onClick={() => { const next = list.filter((_, j) => j !== i); onChange(next.length === 0 ? null : next); }}>{m.widgets.remove}</Button>
                </div>
              ))}
              <div><Button size="sm" disabled={locked} onClick={() => onChange([...list, ""])}>{m.widgets.add}</Button></div>
            </>
          )
          : (
            <>
              {map.map(([k, v]) => (
                <div className="sdd-w-line" key={k}>
                  {row(`${id}-${k}`, `${label} ${k}`, v, segEscape(k), (next) => onChange(Object.fromEntries(map.map(([kk, vv]) => [kk, kk === k ? next : vv]))), <span className="sdd-w-key sdd-mono">{k}</span>)}
                  <Button size="sm" disabled={locked} aria-label={m.widgets.removeItem(k)} onClick={() => { const next = Object.fromEntries(map.filter(([kk]) => kk !== k)); onChange(Object.keys(next).length === 0 ? null : next); }}>{m.widgets.remove}</Button>
                </div>
              ))}
              <div className="sdd-w-line">
                <input className="ac-input sdd-mono" aria-label={m.widgets.newKey} placeholder={m.widgets.newKey} value={newKey} disabled={locked} onChange={(e) => setNewKey(e.target.value)} />
                <Button size="sm" disabled={locked || newKey.trim() === "" || map.some(([k]) => k === newKey.trim())} onClick={() => { onChange(Object.fromEntries([...map, [newKey.trim(), ""]])); setNewKey(""); }}>{m.widgets.addEntry}</Button>
              </div>
            </>
          )}
      <IssueLines issues={rest} id={noteId} />
      {footer}
    </div>
  );
}
