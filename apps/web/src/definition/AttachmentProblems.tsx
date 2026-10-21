import type { ResourceAttachment } from "@agent-console/contracts";
import { hasMaskedSecret } from "../lib/attachmentProblems";
import { messages as m } from "../app/messages";

export interface AttachmentProblemsProps {
  attachments: readonly ResourceAttachment[];
  /** 첨부 번호 -> 서버 오류 메시지 */
  errors?: Readonly<Record<number, readonly string[]>>;
  /** 오류 줄 앞에 붙일 이름 */
  titleOf: (attachment: ResourceAttachment, index: number) => string;
}

/** 첨부 목록 아래의 오류·안내 줄: 서버 오류(평문 비밀 등)와, 가려진 비밀(`***`)을 비밀 참조로 바꾸라는 안내. */
export function AttachmentProblems({ attachments, errors, titleOf }: AttachmentProblemsProps) {
  const rows = attachments.flatMap((a, i) => {
    const messages = [...(errors?.[i] ?? []), ...(hasMaskedSecret(a) ? [m.definition.attachProblems.masked] : [])];
    return messages.length === 0 ? [] : [{ key: `${i}:${a.ref}`, title: titleOf(a, i), messages }];
  });
  if (rows.length === 0) return null;
  return (
    <ul className="app-field-error" role="alert" aria-label={m.definition.attachProblems.label}>
      {rows.map((r) => (
        <li key={r.key}>
          {r.title}: {r.messages.join(" / ")}
        </li>
      ))}
    </ul>
  );
}
