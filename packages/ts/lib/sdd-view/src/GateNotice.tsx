import type { SddGateBlockedDetails } from "@agent-console/contracts/sdd";
import type { ReactNode } from "react";
import { formatMessage, resolveMessages } from "./messages";

export interface GateNoticeProps {
  /** 422 `sdd.gate_blocked`의 `details`. */
  details: SddGateBlockedDetails;
  /** 관문 문구가 details에 없을 때 쓸 글(서버 `SpecGate.message`). */
  message?: string;
  /** 문서 id → 사람이 읽는 이름. 없으면 id 원문. */
  documentTitles?: Readonly<Record<string, string>>;
  /** 확인할 문서를 열 때. 주면 문서 이름이 버튼이 된다. */
  onOpenDocument?: (documentId: string) => void;
  onDismiss?: () => void;
  /** 추가 동작(예: [가져와서 실행]) 자리. */
  actions?: ReactNode;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/**
 * 관문에 막혔다는 안내. 문구는 서버가 준 `message`를 그대로 보이고, 관문 id·문서 id는 데이터다.
 * `details.document_ids`(서버가 조건에서 뽑은 문서)를 바로 열 수 있게 한다.
 */
export function GateNotice({ details, message, documentTitles, onOpenDocument, onDismiss, actions, messages, className }: GateNoticeProps) {
  const text = resolveMessages(messages);
  const body = details.message && details.message !== "" ? details.message : message && message !== "" ? message : formatMessage(text["gate.fallback"], { id: details.gate_id });
  const docs = details.document_ids ?? [];
  return (
    <div className={`ac-sdd-root ac-sdd-notice${className ? ` ${className}` : ""}`} role="alert" data-tone="warning" data-gate={details.gate_id}>
      <p className="ac-sdd-notice-title">{text["gate.title"]}</p>
      <p>{body}</p>
      {docs.length > 0 ? (
        <div className="ac-sdd-notice-docs">
          <span className="ac-sdd-muted">{text["gate.documents"]}</span>
          {docs.map((id) => {
            const title = documentTitles?.[id] ?? id;
            return onOpenDocument ? (
              <button key={id} type="button" className="ac-sdd-link" aria-label={formatMessage(text["gate.openDocument"], { title })} onClick={() => onOpenDocument(id)}>
                {title}
              </button>
            ) : (
              <span key={id}>{title}</span>
            );
          })}
        </div>
      ) : null}
      {actions || onDismiss ? (
        <div className="ac-sdd-notice-actions">
          {actions}
          {onDismiss ? (
            <button type="button" className="ac-sdd-btn" onClick={onDismiss}>
              {text["gate.dismiss"]}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
