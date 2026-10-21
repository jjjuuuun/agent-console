import { useState } from "react";
import type { LogWidget } from "@agent-console/contracts/logs";
import { fmt, type LogViewMessages } from "../messages";

export interface UnknownWidgetProps {
  widget: LogWidget;
  editing?: boolean;
  /** 편집 모드의 [JSON으로 편집]. 없으면 버튼 없음(앱이 TextEditor 대화상자를 연결). */
  onEditJson?: (widget: LogWidget) => void;
  onRemove?: (widget: LogWidget) => void;
  messages: LogViewMessages;
}

/** 레지스트리에 없는 종류의 자리 표시. 설정은 그대로 보존되고 집계 요청은 보내지 않는다. */
export function UnknownWidget({ widget, editing = false, onEditJson, onRemove, messages: m }: UnknownWidgetProps) {
  const [open, setOpen] = useState(false);
  return (
    <div className="ac-lv-unknown" data-kind={widget.kind}>
      <p>
        <span aria-hidden="true">⚠ </span>
        <strong>{fmt(m.unknownWidget, { kind: widget.kind })}</strong>
      </p>
      <p className="ac-lv-muted">{m.unknownWidgetHint}</p>
      <button type="button" className="ac-lv-linkbtn" aria-expanded={open} onClick={() => setOpen(!open)}>
        {m.unknownWidgetJson}
      </button>
      {open ? <pre className="ac-lv-mono-wrap">{JSON.stringify({ query: widget.query, options: widget.options }, null, 2)}</pre> : null}
      {editing ? (
        <div className="ac-lv-row-actions">
          {onEditJson ? (
            <button type="button" className="ac-lv-btn" onClick={() => onEditJson(widget)}>
              {m.editJson}
            </button>
          ) : null}
          {onRemove ? (
            <button type="button" className="ac-lv-btn" onClick={() => onRemove(widget)}>
              {m.widgetRemove}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
