import { useEffect, useRef } from "react";
import { Button, useToast } from "@agent-console/ui";
import { formatBytes } from "../../lib/bytes";
import { FilesView, IssueRows, PlanSummaryLine } from "./PlanParts";
import { exportMessages as t } from "./messages";
import type { Outcome } from "./useExportFlow";

export interface ResultStepProps {
  outcome: Outcome;
  onClose: () => void;
  onAgain: () => void;
}

/** ⑤ 결과: 파일별 동작 배지 + 요약 + 경고 재표시. 제목에 포커스가 간다(스크린리더에 완료를 알림). */
export function ResultStep({ outcome, onClose, onAgain }: ResultStepProps) {
  const heading = useRef<HTMLHeadingElement>(null);
  const toast = useToast();
  useEffect(() => {
    heading.current?.focus();
  }, []);
  if (outcome.kind === "archive") {
    return (
      <div className="exp-result">
        <h3 ref={heading} tabIndex={-1} className="app-block-title">
          {t.result.title}
        </h3>
        <p role="status">{t.result.archiveDone(outcome.filename, formatBytes(outcome.size))}</p>
        <div className="exp-result-actions">
          <Button onClick={onAgain}>{t.result.again}</Button>
          <Button variant="primary" onClick={onClose}>
            {t.close}
          </Button>
        </div>
      </div>
    );
  }
  const files = outcome.result.files ?? [];
  const skipped = files.filter((f) => f.action === "skip").length;
  const where = `${outcome.rootLabel}${outcome.path ? ` (${outcome.path})` : ""}`;
  return (
    <div className="exp-result">
      <h3 ref={heading} tabIndex={-1} className="app-block-title">
        {t.result.title}
      </h3>
      <p role="status" className="ac-num">
        {t.result.summary(files.length - skipped, skipped)}
      </p>
      <p className="app-wrap">
        <span className="app-muted">{t.result.where}: </span>
        <span className="lib-mono">{where}</span>{" "}
        <button
          type="button"
          className="app-link-btn"
          onClick={() => void navigator.clipboard?.writeText(outcome.path || outcome.rootLabel).then(() => toast({ tone: "success", text: t.result.copied }))}
        >
          {t.result.copyPath}
        </button>
      </p>
      <IssueRows issues={outcome.result.warnings ?? []} ariaLabel={t.warningsRegion} />
      <PlanSummaryLine files={files} />
      <FilesView files={files} ariaLabel={t.result.files} />
      <div className="exp-result-actions">
        <Button onClick={onAgain}>{t.result.again}</Button>
        <Button variant="primary" onClick={onClose}>
          {t.close}
        </Button>
      </div>
    </div>
  );
}
