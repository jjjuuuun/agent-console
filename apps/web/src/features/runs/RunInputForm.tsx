import { useId, useLayoutEffect, useRef } from "react";
import type { PortDef } from "@agent-console/contracts";
import { SchemaForm, type JsonSchema } from "@agent-console/schema-form";
import { portKind, portLabel, portRequired, type InputValues } from "./runInputLib";
import { runStartMessages as t } from "./runStartMessages";

export interface RunInputFormProps {
  /** 구성의 입력 포트 목록(`Graph.inputs`). 칸은 이것에서만 만든다 */
  ports: readonly PortDef[];
  values: InputValues;
  onChange: (name: string, value: unknown) => void;
  /** 포트 이름 → 오류 문구(검증·서버 오류). 보이기로 한 칸만 넘긴다 */
  errors?: Readonly<Record<string, string>>;
  /** 칸을 벗어났을 때(검증 시점) */
  onBlurPort?: (name: string) => void;
  disabled?: boolean;
  /** IME 조합 중인지 판정하는 필요는 없다: Enter는 줄바꿈이고 제출은 상위가 Ctrl+Enter로 받는다 */
  idPrefix?: string;
}

const MIN_ROWS = 4;
const MAX_ROWS = 12;

function GrowTextarea({ id, value, onChange, onBlur, disabled, invalid, describedBy, mono }: { id: string; value: string; onChange(v: string): void; onBlur(): void; disabled: boolean; invalid: boolean; describedBy: string | undefined; mono?: boolean }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (el === null) return;
    const line = Number.parseFloat(getComputedStyle(el).lineHeight) || 20;
    el.style.height = "auto";
    // 최소 4줄·최대 12줄, 넘으면 스크롤
    el.style.height = `${Math.min(Math.max(el.scrollHeight, line * MIN_ROWS), line * MAX_ROWS)}px`;
  }, [value]);
  return (
    <textarea
      ref={ref}
      id={id}
      className="ac-input run-input-area"
      data-mono={mono === true ? "true" : undefined}
      rows={MIN_ROWS}
      value={value}
      disabled={disabled}
      aria-invalid={invalid ? "true" : undefined}
      aria-describedby={describedBy}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onBlur}
    />
  );
}

/**
 * 실행 입력 칸(screen-run-start §3.2). 포트 목록에서 칸을 그린다: 스키마 없음 = 멀티라인, 스키마 있음 = 스키마 폼,
 * 그릴 수 없는 스키마 = JSON 직접 입력. 포트 0개면 안내 한 줄. 값·오류는 모두 props(API 호출 없음).
 */
export function RunInputForm({ ports, values, onChange, errors = {}, onBlurPort, disabled = false, idPrefix }: RunInputFormProps) {
  const auto = useId();
  const uid = idPrefix ?? auto;
  if (ports.length === 0) return <p className="app-muted run-input-none">{t.inputNone}</p>;
  return (
    <div className="run-inputs">
      {ports.map((port, i) => {
        const kind = portKind(port);
        const id = `${uid}-${i}`;
        const err = errors[port.name];
        const helpId = port.description ? `${id}-help` : undefined;
        const errId = err === undefined ? undefined : `${id}-err`;
        const describedBy = [helpId, errId].filter(Boolean).join(" ") || undefined;
        const required = portRequired(port);
        const label = portLabel(port);
        return (
          <div className="app-field run-input-port" key={port.name} data-port={port.name} onBlur={kind === "schema" ? () => onBlurPort?.(port.name) : undefined}>
            <label htmlFor={kind === "schema" ? undefined : id} id={`${id}-label`}>
              {label}
              {required ? <span aria-hidden="true"> *</span> : null}
              {required ? <span className="ac-sr-only"> ({t.inputRequired})</span> : null}
            </label>
            {port.description ? <span id={helpId} className="app-muted run-input-help">{port.description}</span> : null}
            {kind === "schema" ? (
              <div role="group" aria-labelledby={`${id}-label`} aria-describedby={describedBy}>
                <SchemaForm
                  schema={port.schema as JsonSchema}
                  value={values[port.name]}
                  onChange={(v) => onChange(port.name, v)}
                  disabled={disabled}
                  idPrefix={id}
                  rawJsonToggle={false}
                  xui={false}
                />
              </div>
            ) : (
              <>
                <GrowTextarea
                  id={id}
                  mono={kind === "json"}
                  value={typeof values[port.name] === "string" ? (values[port.name] as string) : ""}
                  onChange={(v) => onChange(port.name, v)}
                  onBlur={() => onBlurPort?.(port.name)}
                  disabled={disabled}
                  invalid={err !== undefined}
                  describedBy={describedBy}
                />
                {kind === "json" ? <span className="app-muted run-input-help">{t.inputUnknownType}</span> : null}
              </>
            )}
            {err === undefined ? null : <span id={errId} className="run-input-error" role="alert">{err}</span>}
          </div>
        );
      })}
    </div>
  );
}
