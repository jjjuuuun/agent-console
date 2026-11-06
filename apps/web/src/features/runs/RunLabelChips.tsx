import { useState } from "react";
import { Link } from "react-router";
import { Popover } from "@agent-console/ui";
import { runsMessages as t } from "./messages";
import type { LabelChipModel, LabelChips } from "./runLabels";

/** 칩 최대 개수(넘으면 `+N` 팝오버). 화면 규칙 상수다. */
const MAX_CHIPS = 3;

function Chip({ chip }: { chip: LabelChipModel }) {
  return (
    <span className="runs-label-chip" data-testid="run-label-chip">
      {chip.segments.map((s, i) => {
        const body = (
          <>
            <span className="runs-label-title">{s.title}</span> <strong className="ac-ellipsis runs-label-value">{s.value}</strong>
          </>
        );
        return (
          <span key={`${s.title}:${s.value}`} className="runs-label-seg">
            {i > 0 ? <span aria-hidden="true"> · </span> : null}
            {s.href === undefined ? body : <Link to={s.href}>{body}</Link>}
          </span>
        );
      })}
    </span>
  );
}

export interface RunLabelChipsProps {
  model: LabelChips;
}

/**
 * 실행 상세 머리의 라벨 칩. 규칙에 있는 라벨은 `{이름} {값}` 칩(같은 그룹은 `·`로 한 칩), 규칙에 없는 라벨은 `라벨 n` 한 칩으로 묶어 팝오버 표로 보인다.
 * 라벨이 없는 실행에는 아무것도 그리지 않는다.
 */
export function RunLabelChips({ model }: RunLabelChipsProps) {
  const [open, setOpen] = useState(false);
  const extra = Object.entries(model.unmatched);
  if (model.chips.length === 0 && extra.length === 0) return null;
  const shown = model.chips.slice(0, MAX_CHIPS);
  const hidden = model.chips.slice(MAX_CHIPS);
  return (
    <span className="runs-labels" data-testid="run-labels">
      {shown.map((c) => <Chip key={c.id} chip={c} />)}
      {hidden.length > 0 || extra.length > 0 ? (
        <Popover
          open={open}
          onOpenChange={setOpen}
          panelLabel={t.labels.more(hidden.length + extra.length)}
          renderTrigger={(trigger) => (
            <button type="button" {...trigger} className="ac-btn runs-label-more" data-variant="ghost" data-size="sm">
              {hidden.length > 0 ? `+${hidden.length}` : t.labels.more(extra.length)} <span aria-hidden="true">▾</span>
            </button>
          )}
        >
          {hidden.map((c) => <div key={c.id}><Chip chip={c} /></div>)}
          {extra.length === 0 ? null : (
            <table className="runs-labels-table" aria-label={t.labels.more(extra.length)}>
              <thead><tr><th scope="col">{t.labels.tableKey}</th><th scope="col">{t.labels.tableValue}</th></tr></thead>
              <tbody>{extra.map(([k, v]) => <tr key={k}><td className="app-mono">{k}</td><td>{v}</td></tr>)}</tbody>
            </table>
          )}
        </Popover>
      ) : null}
    </span>
  );
}
