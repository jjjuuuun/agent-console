import { useRef, type KeyboardEvent } from "react";
import type { ExporterDescriptor } from "@agent-console/contracts";
import { Tag } from "@agent-console/ui";
import { ErrorBlock } from "../../app/ErrorBlock";
import { kindLabel } from "./exportSources";
import { exportMessages as t } from "./messages";

export interface ExporterStepProps {
  loading: boolean;
  error: Error | null;
  exporters: readonly ExporterDescriptor[];
  selectedId: string | undefined;
  onSelect: (id: string) => void;
  onRetry: () => void;
  /** 서버 정보 화면 링크(없으면 안내 문구만) */
  infoLink?: React.ReactNode;
}

/** ① 형식 고르기: `GET /exporters` 카드 목록(라디오). 카드가 1개여도 단계를 건너뛰지 않는다. */
export function ExporterStep({ loading, error, exporters, selectedId, onSelect, onRetry, infoLink }: ExporterStepProps) {
  const refs = useRef(new Map<string, HTMLDivElement>());
  if (loading) {
    return (
      <div className="app-skeleton" role="status" aria-busy="true" aria-label={t.exporter.loading}>
        {[0, 1].map((i) => (
          <span key={i} className="app-skeleton-row exp-card-skel" aria-hidden="true" />
        ))}
      </div>
    );
  }
  if (error !== null) return <ErrorBlock title={t.exporter.failed} message={error.message} retryLabel={t.exporter.retry} onRetry={onRetry} />;
  if (exporters.length === 0) {
    return (
      <p className="app-muted">
        {t.exporter.empty} {infoLink}
      </p>
    );
  }
  const onKey = (e: KeyboardEvent, index: number) => {
    let next: number | undefined;
    if (e.key === "ArrowDown" || e.key === "ArrowRight") next = (index + 1) % exporters.length;
    else if (e.key === "ArrowUp" || e.key === "ArrowLeft") next = (index - 1 + exporters.length) % exporters.length;
    if (next === undefined) return;
    e.preventDefault();
    const target = exporters[next];
    if (target === undefined) return;
    onSelect(target.id);
    refs.current.get(target.id)?.focus();
  };
  const tabbable = exporters.some((x) => x.id === selectedId) ? selectedId : exporters[0]?.id;
  return (
    <div role="radiogroup" aria-label={t.exporter.label} className="exp-cards">
      {exporters.map((e, i) => {
        const checked = e.id === selectedId;
        return (
          <div
            key={e.id}
            ref={(el) => {
              if (el) refs.current.set(e.id, el);
              else refs.current.delete(e.id);
            }}
            role="radio"
            aria-checked={checked}
            tabIndex={e.id === tabbable ? 0 : -1}
            className="exp-card"
            data-checked={checked ? "true" : undefined}
            onClick={() => onSelect(e.id)}
            onKeyDown={(ev) => {
              if (ev.key === " " || ev.key === "Enter") {
                ev.preventDefault();
                onSelect(e.id);
              } else onKey(ev, i);
            }}
          >
            <span className="exp-card-title">{e.title}</span>
            {e.description ? <span className="exp-card-desc app-muted">{e.description}</span> : null}
            <span className="exp-card-kinds" aria-label={t.exporter.kindsLabel}>
              {(e.kinds ?? []).map((k) => (
                <Tag key={k}>{kindLabel(k)}</Tag>
              ))}
            </span>
          </div>
        );
      })}
    </div>
  );
}
