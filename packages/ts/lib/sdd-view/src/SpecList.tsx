import type { SpecSummary } from "@agent-console/contracts/sdd";
import { useRef, type ReactNode } from "react";
import { useVirtualRows } from "./hooks";
import { formatMessage, resolveMessages } from "./messages";
import { progressRatio } from "./stages";
import { DocumentStateChip } from "./ToneChip";

export const SPEC_ROW_HEIGHT = 64;

export interface SpecListProps {
  specs: readonly SpecSummary[];
  selectedId?: string | null;
  onOpen?: (spec: SpecSummary) => void;
  loading?: boolean;
  /** 빈 상태에 붙이는 버튼(새 스펙·폴더에서 가져오기 등). 앱이 준다. */
  emptyActions?: ReactNode;
  /** 시각 표시(앱의 시간 서식). 없으면 ISO 날짜. */
  formatTime?: (epochSeconds: number) => string;
  /** 목록 높이(px 또는 'fill') */
  height?: number | "fill";
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

function defaultTime(seconds: number): string {
  return new Date(seconds * 1000).toISOString().slice(0, 10);
}

/** 스펙 목록(가상 목록). 진행·지금 단계·문서 상태·준비된 작업 수를 한 줄에 보인다. 스펙 이름·문서 종류는 데이터다. */
export function SpecList({ specs, selectedId, onOpen, loading = false, emptyActions, formatTime = defaultTime, height = "fill", messages, className }: SpecListProps) {
  const text = resolveMessages(messages);
  const scrollRef = useRef<HTMLDivElement>(null);
  const virtual = useVirtualRows({ count: specs.length, rowHeight: SPEC_ROW_HEIGHT, scrollRef });
  if (specs.length === 0) {
    return (
      <div className={`ac-sdd-root ac-sdd-empty${className ? ` ${className}` : ""}`} role="status">
        <p className="ac-sdd-empty-title">{loading ? text["common.loading"] : text["specs.empty.title"]}</p>
        {loading ? null : <p className="ac-sdd-muted">{text["specs.empty.body"]}</p>}
        {loading ? null : emptyActions}
      </div>
    );
  }
  return (
    <div
      ref={scrollRef}
      className={`ac-sdd-root ac-sdd-scroll${className ? ` ${className}` : ""}`}
      style={{ height: height === "fill" ? "100%" : height }}
      aria-busy={loading || undefined}
    >
      <ul className="ac-sdd-vlist" role="list" aria-label={text["specs.list"]} style={{ height: virtual.getTotalSize() }}>
        {virtual.getVirtualItems().map((item) => {
          const spec = specs[item.index] as SpecSummary;
          const total = spec.tasks_total ?? 0;
          const done = spec.tasks_done ?? 0;
          const selected = spec.id === selectedId;
          return (
            <li
              key={spec.id}
              className="ac-sdd-vrow"
              style={{ transform: `translateY(${item.start}px)`, height: SPEC_ROW_HEIGHT }}
              aria-setsize={specs.length}
              aria-posinset={item.index + 1}
            >
              <button type="button" className="ac-sdd-spec" data-selected={selected || undefined} aria-current={selected ? "true" : undefined} onClick={() => onOpen?.(spec)}>
                <span className="ac-sdd-spec-main">
                  <span className="ac-sdd-spec-name ac-sdd-ellipsis">{spec.name && spec.name !== "" ? spec.name : spec.id}</span>
                  {spec.directory ? <span className="ac-sdd-mono ac-sdd-muted ac-sdd-ellipsis">{spec.directory}</span> : null}
                </span>
                <span className="ac-sdd-spec-progress">
                  <span
                    className="ac-sdd-progress"
                    role="progressbar"
                    aria-label={total > 0 ? formatMessage(text["specs.progress"], { done, total }) : text["specs.noTasks"]}
                    aria-valuemin={0}
                    aria-valuemax={Math.max(total, 1)}
                    aria-valuenow={done}
                  >
                    <span className="ac-sdd-progress-fill" style={{ width: `${progressRatio(done, total) * 100}%` }} />
                  </span>
                  <span className="ac-sdd-muted ac-sdd-num">{total > 0 ? formatMessage(text["specs.progress"], { done, total }) : text["specs.noTasks"]}</span>
                </span>
                <span className="ac-sdd-spec-meta">
                  {(spec.ready ?? 0) > 0 ? <span className="ac-sdd-num">{formatMessage(text["specs.ready"], { n: spec.ready ?? 0 })}</span> : null}
                  {spec.current_stage ? <span className="ac-sdd-muted ac-sdd-ellipsis">{formatMessage(text["specs.stage"], { stage: spec.current_stage.title ?? spec.current_stage.id })}</span> : null}
                  {spec.updated_at ? <span className="ac-sdd-muted">{formatMessage(text["specs.updated"], { time: formatTime(spec.updated_at) })}</span> : null}
                  {(spec.issues ?? 0) > 0 ? <span className="ac-sdd-num" data-tone="warning">{formatMessage(text["specs.issues"], { n: spec.issues ?? 0 })}</span> : null}
                </span>
                <span className="ac-sdd-spec-docs">
                  {(spec.documents ?? []).map((d) => (
                    <DocumentStateChip key={d.id} state={d.state ?? null} label={d.state_label ?? null} tone={d.tone ?? null} />
                  ))}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
