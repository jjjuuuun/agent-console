import type { ArchitectureChip } from "./useArchitectureController";

export interface ArchitectureChipsProps {
  chips: readonly ArchitectureChip[];
}

/** 필터 줄에 놓는 구조도 칩(아이콘 + 이름 + ✕). 구조도 선택 칩은 하나만, 하위 구조도 단계 칩은 단계 수만큼. */
export function ArchitectureChips({ chips }: ArchitectureChipsProps) {
  return (
    <>
      {chips.map((chip) => (
        <span key={chip.id} className="arch-chip" data-kind={chip.kind} title={chip.label}>
          {chip.kind === "arch" ? <span className="arch-chip-icon" aria-hidden="true" /> : null}
          <span className="arch-chip-label">{chip.label}</span>
          <button type="button" className="arch-chip-x" aria-label={chip.removeLabel} onClick={chip.onRemove}>×</button>
        </span>
      ))}
    </>
  );
}
