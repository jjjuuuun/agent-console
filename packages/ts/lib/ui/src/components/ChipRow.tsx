import { useState } from "react";
import { Icon } from "./Icon";
import { Popover } from "./Popover";
import { joinClass } from "./Status";
import { useOverflowFit } from "./useOverflowFit";

export interface ChipItem {
  id: string;
  label: string;
  /** 전체 값 툴팁. 기본은 `label`. */
  title?: string;
  /** 아이콘 레지스트리 이름(데이터). */
  icon?: string;
  tone?: "info" | "warning" | "danger" | "success";
  /** 활성·선택 칩. 줄이 모자라도 항상 보이는 쪽에 둔다. */
  active?: boolean;
  /** 있으면 칩이 버튼이 된다. */
  onSelect?: (id: string) => void;
}

export interface ChipRowProps {
  chips: readonly ChipItem[];
  /** 줄 접근성 이름(`role=group`). */
  ariaLabel: string;
  /** `+N` 버튼의 접근성 이름. 기본 "N개 더 보기". */
  moreLabel?: (hiddenCount: number) => string;
  className?: string;
}

const defaultMoreLabel = (n: number) => `${n}개 더 보기`;

function Chip({ chip }: { chip: ChipItem }) {
  const content = (
    <>
      {chip.icon === undefined ? null : <Icon name={chip.icon} size={12} />}
      <span className="ac-chip-label ac-ellipsis">{chip.label}</span>
    </>
  );
  const common = { className: "ac-chip", title: chip.title ?? chip.label, "data-tone": chip.tone, "data-active": chip.active ? "true" : undefined } as const;
  return chip.onSelect === undefined ? (
    <span {...common}>{content}</span>
  ) : (
    <button {...common} type="button" aria-pressed={chip.active ?? undefined} onClick={() => chip.onSelect?.(chip.id)}>
      {content}
    </button>
  );
}

/**
 * 한 줄 칩 목록. 폭에 다 안 들어가면 넘치는 칩을 숨기고 끝에 `+N` 버튼을 둔다(누르면 숨은 칩 전체 팝오버).
 * 칩 한 개는 `--ac-chip-max-w`에서 말줄임. 활성 칩은 항상 보인다. 표현 전용: 칩 목록·문구는 호출자 데이터.
 */
export function ChipRow({ chips, ariaLabel, moreLabel = defaultMoreLabel, className }: ChipRowProps) {
  const [open, setOpen] = useState(false);
  const keys = chips.map((c) => c.id);
  const { rootRef, moreRef, itemRef, hidden } = useOverflowFit({ keys, priorityKeys: chips.filter((c) => c.active).map((c) => c.id), gap: 6, fallbackMoreWidth: 44 });
  const hiddenChips = chips.filter((c) => hidden.has(c.id));
  return (
    <div ref={rootRef} role="group" aria-label={ariaLabel} className={joinClass("ac-chiprow", className)}>
      <div className="ac-chiprow-track">
        {chips.map((chip) => (
          <span key={chip.id} ref={itemRef(chip.id)} className="ac-chiprow-item" data-hidden={hidden.has(chip.id) ? "true" : undefined}>
            <Chip chip={chip} />
          </span>
        ))}
      </div>
      {hiddenChips.length === 0 ? null : (
        <span ref={moreRef} className="ac-chiprow-more">
          <Popover
            open={open}
            onOpenChange={setOpen}
            panelLabel={moreLabel(hiddenChips.length)}
            align="end"
            renderTrigger={(props) => (
              <button {...props} type="button" className="ac-chip ac-chip-more" aria-label={moreLabel(hiddenChips.length)} title={moreLabel(hiddenChips.length)}>
                +{hiddenChips.length}
              </button>
            )}
          >
            <ul className="ac-chiprow-list">
              {hiddenChips.map((chip) => (
                <li key={chip.id}>
                  <Chip chip={chip} />
                </li>
              ))}
            </ul>
          </Popover>
        </span>
      )}
    </div>
  );
}

