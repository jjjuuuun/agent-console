import type { SchemaFormWidgetProps } from "@agent-console/schema-form";
import { useModule } from "../../modules";
import { MEMORY_ROLE, useMemoryKinds } from "../memory";
import { memorySettingsMessages as t } from "./messages";

/**
 * 리소스 폼의 범위 종류 선택 위젯(`x-ui.widget` = `memory-scope-kind`). 선택지는 서버가 병합한 켜진 범위 종류 목록이고,
 * 목록에 없는 값(지운 종류)은 id를 mono로 보이며 "알 수 없는 범위 종류" 표지를 단다. 메모리 기능이 꺼져 있거나 목록을 못 읽으면
 * 선택 대신 id 직접 입력으로 떨어진다(호출도 하지 않는다 — 꺼진 경우). 값 모양은 문자열이다.
 */
export function ScopeKindWidget(props: SchemaFormWidgetProps) {
  const lookup = useModule(MEMORY_ROLE);
  if (lookup.loading) return <input id={props.id} className="memset-input" disabled value={typeof props.value === "string" ? props.value : ""} aria-label={props.label} readOnly />;
  if (!lookup.active) return <FreeInput {...props} note={t.scopeKindWidget.offHelp} />;
  return <KindSelect {...props} />;
}

function FreeInput({ id, value, onChange, onBlur, label, disabled, readonly, note }: SchemaFormWidgetProps & { note: string }) {
  return (
    <span className="memset-scopekind">
      <input id={id} className="memset-input memset-mono" value={typeof value === "string" ? value : ""} aria-label={label} disabled={disabled || readonly} onBlur={onBlur} onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)} />
      <span className="memset-note app-muted">{note}</span>
    </span>
  );
}

function KindSelect(props: SchemaFormWidgetProps) {
  const { id, value, onChange, onBlur, label, disabled, readonly, required } = props;
  const kinds = useMemoryKinds();
  if (kinds.isError) return <FreeInput {...props} note={t.scopeKindWidget.loadFailed} />;
  const current = typeof value === "string" ? value : "";
  const list = (kinds.data?.kinds ?? []).filter((k) => k.disabled !== true);
  const unknown = current !== "" && kinds.data !== undefined && !list.some((k) => k.kind === current);
  return (
    <span className="memset-scopekind">
      <select id={id} aria-label={label} value={current} disabled={disabled || readonly || kinds.isPending} onBlur={onBlur} onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}>
        {current === "" || !required ? <option value="">{required ? t.scopeKindWidget.placeholder : t.scopeKindWidget.none}</option> : null}
        {unknown ? <option value={current}>{current}</option> : null}
        {list.map((k) => (
          <option key={k.kind} value={k.kind} title={k.description ?? undefined}>{k.label === k.kind ? k.kind : `${k.label} (${k.kind})`}</option>
        ))}
      </select>
      {unknown ? <span className="memset-unknown"><span aria-hidden="true">▲ </span>{t.scopeKindWidget.unknown}</span> : null}
    </span>
  );
}
