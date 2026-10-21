import { useId, useMemo, useState } from "react";
import type { LogDashboard } from "@agent-console/contracts/logs";
import { layoutFlow, widgetSize } from "./layout";
import { fmt, mergeMessages, type DeepPartial, type LogViewMessages } from "./messages";

export interface TemplateApplyRequest {
  mode: "new" | "append";
  templateId: string;
  /** mode가 new일 때의 제목. */
  title?: string;
}

export interface TemplatePickerProps {
  templates: readonly LogDashboard[];
  /** 현재 대시보드에 위젯을 덧붙일 수 있는지(열려 있는 대시보드가 있을 때). */
  canAppend: boolean;
  onApply: (req: TemplateApplyRequest) => void;
  onCancel?: () => void;
  /** 내부 `<form>`의 id. 앱의 다이얼로그 하단 버튼이 `<button type="submit" form={formId}>`로 제출한다. 없으면 useId 값. */
  formId?: string;
  /** 취소·적용 버튼을 이 컴포넌트 안에 그릴지(기본 true, 단독 사용용). 다이얼로그 `actions`에 버튼을 두는 앱은 false. */
  showActions?: boolean;
  /** 현재 서버가 모르는 위젯 종류의 수(레지스트리 기준, 앱이 계산). */
  unknownKinds: (template: LogDashboard) => number;
  /** 빈 대시보드 만들기(템플릿이 0개일 때의 대안 버튼). */
  onCreateBlank?: () => void;
  messages?: DeepPartial<LogViewMessages>;
}

/** 템플릿 선택: 목록 + 위젯 제목·축소 도면 미리보기. 실제 집계를 호출하지 않는다. */
export function TemplatePicker(props: TemplatePickerProps) {
  const { templates, canAppend, onApply, onCancel, unknownKinds, onCreateBlank, formId, showActions = true } = props;
  const m = useMemo(() => mergeMessages(props.messages), [props.messages]);
  const uid = useId();
  const formDomId = formId ?? `${uid}-form`;
  const [selectedId, setSelectedId] = useState<string | undefined>(templates[0]?.id);
  const [mode, setMode] = useState<"new" | "append">("new");
  const selected = templates.find((t) => t.id === selectedId) ?? templates[0];
  const [titleEdit, setTitleEdit] = useState<{ id: string; title: string } | null>(null);
  const title = titleEdit && titleEdit.id === selected?.id ? titleEdit.title : (selected?.title ?? "");

  if (templates.length === 0) {
    return (
      <div className="ac-lv-empty" role="status">
        <p>{m.templateNone}</p>
        {onCreateBlank ? (
          <button type="button" className="ac-lv-btn" onClick={onCreateBlank}>
            {m.templateBlank}
          </button>
        ) : null}
      </div>
    );
  }
  const widgets = selected?.widgets ?? [];
  const placements = layoutFlow(widgets, 12, (w) => widgetSize(w));
  const rows = Math.max(1, ...placements.map((p) => p.row + p.h));
  return (
    <form
      id={formDomId}
      className="ac-lv-templates"
      aria-label={m.templateTitle}
      onSubmit={(e) => {
        e.preventDefault();
        if (selected) onApply(mode === "new" ? { mode, templateId: selected.id, title } : { mode, templateId: selected.id });
      }}
    >
      <ul role="listbox" aria-label={m.templateTitle} className="ac-lv-templatelist">
        {templates.map((t) => {
          const unknown = unknownKinds(t);
          return (
            <li key={t.id} role="option" aria-selected={t.id === selected?.id}>
              <button type="button" onClick={() => setSelectedId(t.id)}>
                <strong className="ac-lv-ellipsis">{t.title}</strong>
                <span className="ac-lv-muted">{fmt(m.templateWidgets, { n: t.widgets?.length ?? 0 })}</span>
                {unknown > 0 ? <span className="ac-lv-chip" data-tone="warning">{fmt(m.templateUnknown, { n: unknown })}</span> : null}
              </button>
            </li>
          );
        })}
      </ul>
      <div className="ac-lv-templatepreview">
        <ul className="ac-lv-plain">
          {widgets.map((w) => (
            <li key={w.id} className="ac-lv-ellipsis">{w.title ?? w.id}</li>
          ))}
        </ul>
        <div className="ac-lv-miniplan" role="img" aria-label={selected?.title} style={{ aspectRatio: `12 / ${rows}` }}>
          {placements.map((p) => {
            const w = widgets.find((x) => x.id === p.id);
            return (
              <span key={p.id} className="ac-lv-ellipsis" style={{ left: `${(p.col / 12) * 100}%`, top: `${(p.row / rows) * 100}%`, width: `${(p.w / 12) * 100}%`, height: `${(p.h / rows) * 100}%` }}>
                {w?.title ?? ""}
              </span>
            );
          })}
        </div>
        <fieldset className="ac-lv-modes">
          <label className="ac-choice ac-lv-choice">
            <input type="radio" name={`${uid}-mode`} checked={mode === "new"} onChange={() => setMode("new")} />
            <span>{m.templateNew}</span>
          </label>
          {canAppend ? (
            <label className="ac-choice ac-lv-choice">
              <input type="radio" name={`${uid}-mode`} checked={mode === "append"} onChange={() => setMode("append")} />
              <span>{m.templateAppend}</span>
            </label>
          ) : null}
          {mode === "new" ? (
            <label className="ac-lv-field">
              {m.templateName}
              <input className="ac-lv-input" value={title} onChange={(e) => selected && setTitleEdit({ id: selected.id, title: e.target.value })} />
            </label>
          ) : null}
        </fieldset>
        {showActions ? (
          <div className="ac-lv-row-actions">
            {onCancel ? (
              <button type="button" className="ac-lv-btn" onClick={onCancel}>
                {m.editorCancel}
              </button>
            ) : null}
            <button type="submit" className="ac-lv-btn" data-primary>
              {m.templateApply}
            </button>
          </div>
        ) : null}
      </div>
    </form>
  );
}
