import type { TaskLink } from "@agent-console/contracts/sdd";
import { statusTone } from "./display";
import { formatMessage, resolveMessages } from "./messages";
import { ToneChip } from "./ToneChip";

export interface TaskRunChipsProps {
  links: readonly TaskLink[] | undefined;
  /** 눌러서 열 수 있는 연결 종류(`TaskLink.kind`). 앱이 라우트 데이터에서 준다. 목록에 없는 종류는 누를 수 없는 일반 칩. */
  openableKinds?: readonly string[];
  onOpen?: (link: TaskLink) => void;
  /** 연결 상태(실행 상태 등) → 라벨·톤. 없으면 원문 + 중립. */
  statuses?: readonly { id: string; label?: string | null; tone?: string | null; done?: boolean }[];
  /** 보일 칩 수 상한(넘으면 `+n`). 기본 3 */
  max?: number;
  messages?: Readonly<Record<string, string>>;
}

/** 작업에 이어진 실행 칩 줄. 종류·상태 이름은 데이터이고 모르는 종류는 `ref` 원문의 일반 칩이다. */
export function TaskRunChips({ links, openableKinds = [], onOpen, statuses, max = 3, messages }: TaskRunChipsProps) {
  const text = resolveMessages(messages);
  const all = links ?? [];
  if (all.length === 0) return null;
  const shown = all.slice(0, max);
  const rest = all.length - shown.length;
  return (
    <span className="ac-sdd-links">
      {shown.map((link) => {
        const st = link.status ? statusTone(link.status, statuses) : null;
        const label = st ? formatMessage(text["tasks.runChip"], { ref: link.ref, status: st.label }) : link.ref;
        const key = `${link.integration}:${link.kind}:${link.ref}`;
        const openable = onOpen !== undefined && openableKinds.includes(link.kind);
        return openable ? (
          <button key={key} type="button" className="ac-sdd-chip-button" aria-label={formatMessage(text["tasks.runChip.open"], { ref: link.ref })} title={label} onClick={() => onOpen(link)}>
            <ToneChip label={label} tone={st?.tone} />
          </button>
        ) : (
          <ToneChip key={key} label={label} tone={st?.tone} />
        );
      })}
      {rest > 0 ? <span className="ac-sdd-field ac-sdd-num">{formatMessage(text["tasks.moreFields"], { n: rest })}</span> : null}
    </span>
  );
}
