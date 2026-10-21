import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { DelegationStrategyDescriptor, EdgeTypeDescriptor } from "@agent-console/contracts";
import type { GraphEditorMessages } from "../messages";
import { defaultMessages } from "../messages";
import { resolveEdgeStyle } from "../logic/edgeStyle";

/** 후보 한 줄의 추가 정보(호출자가 새 연결의 상황에서 계산한다). */
export interface EdgeKindCandidateInfo {
  /** 있으면 행을 비활성(`aria-disabled`)으로 두고 고를 수 없게 한다. 이 문구가 행 아래에 보이고 시도할 때 라이브로 읽힌다 */
  disabledReason?: string;
  /** 기본 선택. `preselected`보다 앞선다 */
  preferred?: boolean;
  /** 아이콘 이름(`renderIcon`으로 그린다). 생략하면 디스크립터 속성에서 정한다 */
  iconName?: string;
  /** 이 종류로 연결될 포트(예: `결과 → 입력`). 있으면 행에 포트 열로 보인다(노드 몸체에 놓아 연결할 때 포트를 추론한 결과) */
  portsText?: string;
}

export interface EdgeKindDialogProps {
  /** 후보 종류(보통 `candidateEdgeKinds`로 걸러진 것) */
  edgeTypes: readonly EdgeTypeDescriptor[];
  /** 미리 고른 종류(`defaultEdgeKind`가 후보에 있으면 그것, 아니면 첫 항목) */
  preselected: string;
  /** 후보별 추가 정보. 키 = 종류 id */
  info?: Readonly<Record<string, EdgeKindCandidateInfo>>;
  /** 위임 방식 목록(선 패턴 계산용) */
  delegationStrategies?: readonly Pick<DelegationStrategyDescriptor, "id">[];
  /** 아이콘 이름을 그리는 함수(없으면 글자) */
  renderIcon?: (name: string) => ReactNode;
  onConfirm: (kind: string) => void;
  onCancel: () => void;
  messages?: GraphEditorMessages;
}

/**
 * 새 연결의 엣지 종류 선택 UI. 미리 선택된 항목이 있어 Enter만으로 확정된다.
 * 키보드: ↑↓ 이동, 1~9 직접 선택, Enter 확정, Esc 취소. 행마다 선 미리보기(색·점선)와 속성 기반 보조 배지.
 */
export function EdgeKindDialog(props: EdgeKindDialogProps) {
  const m = props.messages ?? defaultMessages;
  const info = props.info ?? {};
  const preferred = props.edgeTypes.find((t) => info[t.id]?.preferred === true && info[t.id]?.disabledReason === undefined)?.id;
  const [kind, setKind] = useState(preferred ?? props.preselected);
  const [note, setNote] = useState("");
  const blocked = (id: string): string | undefined => info[id]?.disabledReason;
  const choose = (id: string): boolean => {
    const reason = blocked(id);
    if (reason !== undefined) {
      setNote(reason);
      return false;
    }
    setNote("");
    setKind(id);
    return true;
  };
  const selectedRef = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    selectedRef.current?.focus();
  }, []);
  return (
    <div className="ac-ge-dialog-backdrop">
      <form
        className="ac-ge-dialog ac-text"
        role="dialog"
        aria-modal="true"
        aria-label={m.edgeKindTitle}
        onSubmit={(e) => {
          e.preventDefault();
          if (blocked(kind) !== undefined) {
            setNote(blocked(kind) as string);
            return;
          }
          props.onConfirm(kind);
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.stopPropagation();
            props.onCancel();
          } else if (/^[1-9]$/.test(e.key)) {
            const picked = props.edgeTypes[Number(e.key) - 1];
            if (picked !== undefined) {
              e.preventDefault();
              choose(picked.id);
            }
          }
        }}
      >
        <h3 className="ac-ge-dialog-title">{m.edgeKindTitle}</h3>
        <div role="radiogroup" aria-label={m.edgeKindTitle} className="ac-ge-dialog-choices">
          {props.edgeTypes.map((t, idx) => {
            const style = resolveEdgeStyle(t, props.delegationStrategies ?? []);
            const reason = blocked(t.id);
            const iconName = info[t.id]?.iconName ?? style.iconName;
            const icon = iconName === undefined ? null : (props.renderIcon?.(iconName) ?? null);
            return (
            <div key={t.id} className="ac-ge-choice-row" aria-disabled={reason !== undefined ? "true" : undefined} data-kind-row={t.id}>
            <label className="ac-ge-choice">
              <input
                type="radio"
                name="ac-ge-edge-kind"
                value={t.id}
                checked={kind === t.id}
                aria-disabled={reason !== undefined ? "true" : undefined}
                ref={kind === t.id ? selectedRef : undefined}
                onChange={() => choose(t.id)}
              />
              <svg className="ac-ge-choice-line" width="24" height="8" viewBox="0 0 24 8" aria-hidden="true" focusable="false">
                <line
                  x1="1" y1="4" x2="23" y2="4" strokeWidth="1.5"
                  style={{ stroke: style.color ?? "var(--ac-edge)", ...(style.dasharray !== undefined ? { strokeDasharray: style.dasharray } : {}), ...(style.linecap !== undefined ? { strokeLinecap: style.linecap } : {}) }}
                />
              </svg>
              {icon !== null && <span className="ac-ge-edge-icon" aria-hidden="true">{icon}</span>}
              <span className="ac-ge-choice-texts">
                <span className="ac-ellipsis" title={t.title}>
                  {t.title}
                </span>
                {t.description && <span className="ac-ge-palette-desc ac-ellipsis" title={t.description}>{t.description}</span>}
                {reason !== undefined && <span className="ac-ge-choice-reason">{reason}</span>}
              </span>
              {info[t.id]?.portsText !== undefined && (
                <span className="ac-ge-choice-ports ac-ellipsis" data-ports-for={t.id} title={info[t.id]?.portsText}>
                  {info[t.id]?.portsText}
                </span>
              )}
            </label>
              {idx < 9 && <kbd className="ac-ge-kbd" aria-hidden="true">{idx + 1}</kbd>}
            </div>
            );
          })}
        </div>
        <p className="ac-ge-dialog-hint">{m.edgeKindHint}</p>
        <p className="ac-ge-choice-reason" role="status" aria-live="polite">{note}</p>
        <div className="ac-ge-dialog-actions">
          <button type="button" className="ac-ge-btn" onClick={props.onCancel}>
            {m.edgeKindCancel}
          </button>
          <button type="submit" className="ac-ge-btn ac-ge-btn--primary">
            {m.edgeKindConfirm}
          </button>
        </div>
      </form>
    </div>
  );
}
