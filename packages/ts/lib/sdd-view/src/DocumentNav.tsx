import type { SpecDocumentSummary } from "@agent-console/contracts/sdd";
import { formatMessage, resolveMessages } from "./messages";
import { DocumentStateChip } from "@agent-console/markdown-doc";

export interface DocumentNavProps {
  documents: readonly SpecDocumentSummary[];
  selectedId?: string | null;
  onSelect?: (document: SpecDocumentSummary) => void;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/** 스펙 안 문서 목록(문서 탭 왼쪽). 문서 이름은 `title`, 상태는 서버가 푼 `state_label`·`tone`이다. */
export function DocumentNav({ documents, selectedId, onSelect, messages, className }: DocumentNavProps) {
  const text = resolveMessages(messages);
  if (documents.length === 0) {
    return (
      <p className={`ac-sdd-root ac-sdd-muted${className ? ` ${className}` : ""}`} role="status">
        {text["docs.empty"]}
      </p>
    );
  }
  return (
    <nav className={`ac-sdd-root ac-sdd-docnav${className ? ` ${className}` : ""}`} aria-label={text["docs.nav"]}>
      <ul role="list">
        {documents.map((doc) => {
          const selected = doc.id === selectedId;
          const title = doc.title && doc.title !== "" ? doc.title : doc.id;
          return (
            <li key={doc.id}>
              <button
                type="button"
                className="ac-sdd-docnav-item"
                data-selected={selected || undefined}
                aria-current={selected ? "page" : undefined}
                aria-label={doc.state ? `${title}, ${formatMessage(text["docs.state"], { state: doc.state_label ?? doc.state })}` : title}
                onClick={() => onSelect?.(doc)}
              >
                <span className="ac-sdd-ellipsis">{title}</span>
                <DocumentStateChip state={doc.state ?? null} label={doc.state_label ?? null} tone={doc.tone ?? null} />
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
