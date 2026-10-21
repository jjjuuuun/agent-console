import { useCallback, useRef, useState } from "react";
import type { ContentChange } from "@agent-console/contracts";
import { Button } from "@agent-console/ui";
import { formatBytes } from "../../lib/bytes";
import { LazyTextDiff } from "./LazyTextDiff";
import { versionMessages as t } from "./messages";
import { contentStatus, languageOfPath, textDiffBlocked } from "./versionsLogic";

/** 한 쪽(이전/이후) 파일 내용. 텍스트가 아니면 text가 null. */
export interface SideText {
  text: string | null;
}

export interface ContentChangesProps {
  changes: readonly ContentChange[];
  /** 경로별 크기(바이트). 모르면 undefined */
  sizeOf: (path: string, side: "before" | "after") => number | undefined;
  /** 두 쪽 내용을 읽는다. 한쪽만 있으면(추가/삭제) 없는 쪽은 `{text: ""}` */
  load: (change: ContentChange) => Promise<{ before: SideText; after: SideText }>;
}

type Phase = { name: "idle" } | { name: "loading" } | { name: "error" } | { name: "blocked"; reason: "large" | "binary" } | { name: "ready"; before: string; after: string };

function ContentRow({ change, sizeOf, load }: { change: ContentChange } & Omit<ContentChangesProps, "changes">) {
  const [phase, setPhase] = useState<Phase>({ name: "idle" });
  const [open, setOpen] = useState(false);
  const seq = useRef(0);
  const status = contentStatus(change);
  const sizeBefore = sizeOf(change.path, "before");
  const sizeAfter = sizeOf(change.path, "after");
  const tooLarge = textDiffBlocked([sizeBefore, sizeAfter]) !== undefined;

  const run = useCallback(() => {
    const mine = ++seq.current;
    setPhase({ name: "loading" });
    load(change).then(
      (r) => {
        if (mine !== seq.current) return;
        if (r.before.text === null || r.after.text === null) setPhase({ name: "blocked", reason: "binary" });
        else setPhase({ name: "ready", before: r.before.text, after: r.after.text });
      },
      () => {
        if (mine === seq.current) setPhase({ name: "error" });
      },
    );
  }, [change, load]);

  const toggle = () => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (phase.name === "idle" || phase.name === "error") run();
  };

  return (
    <li className="ver-content-row" data-status={status}>
      <div className="ver-content-head">
        <span className="ver-op">
          <span aria-hidden="true">{t.content.statusIcon[status]}</span> {t.content.status[status]}
        </span>
        <span className="lib-mono app-wrap ver-content-path">{change.path}</span>
        <span className="lib-mono app-muted" title={`${change.before_hash ?? ""} → ${change.after_hash ?? ""}`}>
          {(change.before_hash ?? "").slice(0, 8) || "–"} → {(change.after_hash ?? "").slice(0, 8) || "–"}
        </span>
        <Button size="sm" disabled={tooLarge} aria-expanded={open} onClick={toggle}>
          {open ? t.content.close : t.content.open}
        </Button>
      </div>
      {tooLarge ? <p className="app-muted ver-note">{t.content.tooLarge(formatBytes(sizeBefore), formatBytes(sizeAfter))}</p> : null}
      {open && !tooLarge ? (
        <div className="ver-content-body">
          {phase.name === "loading" ? (
            <div className="app-skeleton" role="status" aria-busy="true" aria-label={t.content.loading}>
              {Array.from({ length: 8 }, (_, i) => (
                <span key={i} className="app-skeleton-row" aria-hidden="true" />
              ))}
            </div>
          ) : null}
          {phase.name === "error" ? (
            <p role="alert" className="ver-error">
              {t.content.failed}{" "}
              <button type="button" className="app-link-btn" onClick={run}>
                {t.content.retry}
              </button>
            </p>
          ) : null}
          {phase.name === "blocked" ? <p className="app-muted ver-note">{t.content.binary}</p> : null}
          {phase.name === "ready" ? (
            <LazyTextDiff
              before={phase.before}
              after={phase.after}
              language={languageOfPath(change.path)}
              ariaLabel={t.content.diffLabel(change.path)}
              messages={{ unchangedLines: t.content.unchangedLines, split: t.content.split, unified: t.content.unified, toolbar: t.content.viewToolbar }}
            />
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

/** 본문 변경 목록(`DefinitionDiff.content_changes`). 행마다 [텍스트 비교 ▸]로 `TextDiff`를 펼친다(크기 > 상한이면 해시만 비교). */
export function ContentChanges({ changes, sizeOf, load }: ContentChangesProps) {
  if (changes.length === 0) return null;
  return (
    <section aria-label={t.content.table} className="ver-content">
      <h3 className="app-block-title">{t.content.title}</h3>
      <ul className="ver-content-list">
        {changes.map((c) => (
          <ContentRow key={c.path} change={c} sizeOf={sizeOf} load={load} />
        ))}
      </ul>
    </section>
  );
}
