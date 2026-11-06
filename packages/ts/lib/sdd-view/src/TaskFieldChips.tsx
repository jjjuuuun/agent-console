import { formatMessage, resolveMessages } from "./messages";

export interface TaskFieldChipsProps {
  /** 작업 줄의 필드(키·값은 사용자 문법이 정한 데이터). */
  fields: Readonly<Record<string, string>> | undefined;
  /** 보일 칩 수 상한(넘으면 `+n`). 기본 3 */
  max?: number;
  messages?: Readonly<Record<string, string>>;
}

/** 작업 필드 칩 줄. 키 이름은 데이터이므로 `키: 값` 그대로 보인다. 비면 아무것도 그리지 않는다. */
export function TaskFieldChips({ fields, max = 3, messages }: TaskFieldChipsProps) {
  const text = resolveMessages(messages);
  const entries = Object.entries(fields ?? {}).filter(([, v]) => v !== "");
  if (entries.length === 0) return null;
  const shown = entries.slice(0, max);
  const rest = entries.length - shown.length;
  return (
    <span className="ac-sdd-fields">
      {shown.map(([k, v]) => (
        <span key={k} className="ac-sdd-field" title={`${k}: ${v}`}>
          <span className="ac-sdd-muted">{k}</span> <span className="ac-sdd-ellipsis">{v}</span>
        </span>
      ))}
      {rest > 0 ? (
        <span className="ac-sdd-field ac-sdd-num" title={entries.slice(max).map(([k, v]) => `${k}: ${v}`).join("\n")}>
          {formatMessage(text["tasks.moreFields"], { n: rest })}
        </span>
      ) : null}
    </span>
  );
}
