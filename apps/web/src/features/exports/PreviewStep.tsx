import type { ExportPlan } from "@agent-console/contracts";
import { Button } from "@agent-console/ui";
import { ErrorBlock } from "../../app/ErrorBlock";
import { describeError } from "../../app/errors";
import { FilesView, PlanSummaryLine } from "./PlanParts";
import { exportMessages as t } from "./messages";

export interface PreviewStepProps {
  plan: ExportPlan | undefined;
  loading: boolean;
  fetching: boolean;
  error: Error | null;
  onRetry: () => void;
  onBack: () => void;
}

/** ③ 미리보기: 파일 목록(경로·크기·동작)과 요약. 경고는 다이얼로그 아래쪽 영역에 모아 보인다. 파일 내용은 오지 않는다. */
export function PreviewStep({ plan, loading, fetching, error, onRetry, onBack }: PreviewStepProps) {
  if (loading || (plan === undefined && error === null)) {
    return (
      <div className="app-skeleton" role="status" aria-busy="true" aria-label={t.preview.loading}>
        {Array.from({ length: 6 }, (_, i) => (
          <span key={i} className="app-skeleton-row" aria-hidden="true" />
        ))}
      </div>
    );
  }
  if (plan === undefined && error !== null) {
    const view = describeError(error, t.preview.failed);
    return <ErrorBlock title={t.preview.failed} message={view.message} fix={view.fix} retryLabel={t.preview.retry} onRetry={onRetry} />;
  }
  const files = plan?.files ?? [];
  if (files.length === 0) {
    return (
      <div className="exp-empty">
        <p className="app-muted">{t.preview.empty}</p>
        <Button onClick={onBack}>{`← ${t.preview.toOptions}`}</Button>
      </div>
    );
  }
  return (
    <div className="exp-preview" aria-busy={fetching}>
      <PlanSummaryLine files={files} />
      {fetching ? <span className="app-muted exp-note" role="status">{t.preview.refreshing}</span> : null}
      <FilesView files={files} />
    </div>
  );
}
