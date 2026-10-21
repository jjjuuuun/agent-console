import type { GraphEditorMessages } from "../messages";
import { defaultMessages, format } from "../messages";
import type { TeamSharedProps } from "../types";

export interface TeamSharedBarProps extends TeamSharedProps {
  messages?: GraphEditorMessages;
  /** 읽기 전용이면 [붙이기]·× 없음 */
  readOnly?: boolean;
}

/** 캔버스 상단 "팀 공용" 띠: 칩(선택·제거) + [붙이기] + 상속 개수 링크. 선은 그리지 않는다. */
export function TeamSharedBar(props: TeamSharedBarProps) {
  const m = props.messages ?? defaultMessages;
  return (
    <div className="ac-ge-shared" role="group" aria-label={m.teamSharedTitle}>
      <span className="ac-ge-shared-title">{m.teamSharedTitle}</span>
      {props.items.length === 0 && <span className="ac-ge-shared-empty">{m.teamSharedEmpty}</span>}
      {props.items.map((c) => (
        <span key={c.key} className="ac-ge-shared-chip">
          <button type="button" className="ac-ge-shared-chip-main" onClick={() => props.onSelect?.(c.key)} title={c.title}>
            {c.iconText !== undefined && <span aria-hidden="true">{c.iconText} </span>}
            <span className="ac-ellipsis">{c.title}</span>
            {c.modeText !== undefined && <span className="ac-ge-shared-mode"> ({c.modeText})</span>}
          </button>
          {!props.readOnly && props.onRemove !== undefined && (
            <button type="button" className="ac-ge-shared-remove" aria-label={format(m.teamSharedRemove, { title: c.title })} onClick={() => props.onRemove?.(c.key)}>
              ×
            </button>
          )}
        </span>
      ))}
      {!props.readOnly && props.onAdd !== undefined && (
        <button type="button" className="ac-ge-btn" onClick={props.onAdd}>
          {m.teamSharedAdd}
        </button>
      )}
      {props.inheritedCount !== undefined && props.inheritedCount > 0 && (
        <button type="button" className="ac-ge-shared-inherited" onClick={props.onOpenInherited} disabled={props.onOpenInherited === undefined}>
          {format(m.teamSharedInherited, { n: props.inheritedCount })}
        </button>
      )}
    </div>
  );
}
