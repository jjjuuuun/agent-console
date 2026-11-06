import { formatMessage, messageOr, resolveMessages } from "./messages";

export interface RulesSourceBadgeProps {
  /** 값의 출처(`EffectiveSyntax.sources`의 값, 열린 문자열). 이름 문구는 `source.<값>` 키로 바꿀 수 있고 없으면 원문. */
  source: string;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/** 규칙·문법 값이 어디서 왔는지 보이는 작은 배지. 출처 이름은 데이터다. */
export function RulesSourceBadge({ source, messages, className }: RulesSourceBadgeProps) {
  const text = resolveMessages(messages);
  const name = messageOr(text, `source.${source}`, source);
  return (
    <span className={`ac-sdd-source${className ? ` ${className}` : ""}`} data-source={source} title={text["source.tip"]}>
      {formatMessage(text["source.label"], { source: name })}
    </span>
  );
}
