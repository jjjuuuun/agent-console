import type { GraphEditorMessages } from "../messages";
import { defaultMessages, format } from "../messages";
import type { ResourceChip } from "../logic/team";

export interface ResourceChipsProps {
  chips: readonly ResourceChip[];
  /** 보일 최대 칩 수. 넘으면 `+N`. 기본 4 */
  max?: number;
  /** 줄 전체 클릭(앱이 리소스 탭을 연다). 없으면 읽기 전용 */
  onClick?: () => void;
  messages?: GraphEditorMessages;
}

/** 리소스 칩 줄: 종류 아이콘 + 개수. 툴팁에 이름 목록. 캔버스 라이브러리에 의존하지 않는다. */
export function ResourceChips(props: ResourceChipsProps) {
  const m = props.messages ?? defaultMessages;
  const max = props.max ?? 4;
  const shown = props.chips.slice(0, max);
  const rest = props.chips.length - shown.length;
  const body = (
    <>
      {shown.map((c) => (
        <span key={c.key} className="ac-ge-rchip" title={format(m.resourceChipTitle, { title: c.title, count: c.count, names: c.names.join(", ") })}>
          <span className="ac-ge-rchip-icon" aria-hidden="true">{c.iconText}</span>
          <span className="ac-ge-rchip-count">{c.count}</span>
          <span className="ac-ge-sr-only">{format(m.resourceChipTitle, { title: c.title, count: c.count, names: c.names.join(", ") })}</span>
        </span>
      ))}
      {rest > 0 && <span className="ac-ge-rchip" title={props.chips.slice(max).map((c) => c.title).join(", ")}>{format(m.moreResourceChips, { n: rest })}</span>}
    </>
  );
  if (props.onClick === undefined) {
    return <div className="ac-ge-rchips" role="group" aria-label={m.resourceChipsLabel}>{body}</div>;
  }
  return (
    <button type="button" className="ac-ge-rchips ac-ge-rchips--button nodrag" aria-label={m.resourceChipsLabel} onClick={props.onClick}>
      {body}
    </button>
  );
}
