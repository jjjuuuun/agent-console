import { useRef, useState, type KeyboardEvent } from "react";
import type { ExportSelection } from "@agent-console/contracts";
import { Banner, Button, ConfirmDialog, Dialog } from "@agent-console/ui";
import { useApiQuery } from "../../app/queries";
import { saveBlob } from "../../lib/download";
import { isImeKeyEvent } from "../../lib/ime";
import { DestinationStep } from "./DestinationStep";
import { ExporterStep } from "./ExporterStep";
import { ItemsStep } from "./ItemsStep";
import { IssueRows } from "./PlanParts";
import { PreviewStep } from "./PreviewStep";
import { ResultStep } from "./ResultStep";
import { overwriteCount } from "./exportLogic";
import { ITEM_SOURCES, sourceKind } from "./exportSources";
import { exportMessages as t } from "./messages";
import { useExportFlow, type Step } from "./useExportFlow";
import "./exports.css";

export interface ExportDialogProps {
  /** 미리 담을 항목(현재 화면의 정의). 비어 있으면 ②에서 고른다 */
  initialItems: readonly ExportSelection[];
  onClose: () => void;
  /** 편집 화면에 저장 안 된 변경이 있다(안내 + [먼저 저장]) */
  dirty?: boolean;
  onSave?: () => void;
  /** 서버 정보 화면 링크(형식이 하나도 없을 때 안내 옆에 붙는다) */
  infoLink?: React.ReactNode;
  /** 다운로드 구현 주입(기본: 브라우저 `<a download>`) */
  download?: (blob: Blob, filename: string) => void;
}

const STEP_KEYS = ["exporter", "items", "preview", "destination"] as const;

/**
 * 내보내기 위저드(형식 -> 항목·옵션 -> 미리보기 -> 내보낼 곳 -> 결과). 정의를 바꾸지 않는 읽기 작업이다.
 * 형식·옵션은 서버 디스크립터(`GET /exporters`)로 그리고, 덮어쓰기는 확인을 거친다(끌 수 없음).
 */
export function ExportDialog({ initialItems, onClose, dirty = false, onSave, infoLink, download = saveBlob }: ExportDialogProps) {
  const flow = useExportFlow(initialItems, download);
  const names = useApiQuery(
    ["list", "export-names"],
    async (rest) => {
      const map = new Map<string, string>();
      await Promise.all(
        ITEM_SOURCES.map(async (s) => {
          const kind = sourceKind(s);
          if (kind === undefined) return;
          for (const r of await s.load(rest)) map.set(`${kind}:${r.id}`, r.name);
        }),
      );
      return map;
    },
    { retry: false },
  );
  const nameOf = (item: ExportSelection) => names.data?.get(`${item.kind}:${item.id}`) ?? item.id;
  const [warningsOpen, setWarningsOpen] = useState(true);
  const [confirmOverwrite, setConfirmOverwrite] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const warnings = flow.plan.data?.warnings ?? [];
  const planFiles = flow.plan.data?.files;
  const inFlow = flow.step <= 4;
  const folderReady = flow.destination === "archive" || (flow.rootId !== "" && flow.subdirProblem === undefined);
  const needsOverwriteConfirm = flow.destination === "folder" && flow.onConflict === "overwrite" && overwriteCount(planFiles ?? []) > 0;

  const startRun = () => {
    if (needsOverwriteConfirm) setConfirmOverwrite(true);
    else void flow.run();
  };
  const primary = () => {
    if (flow.step === 4) startRun();
    else flow.next();
  };
  const onKeyDown = (e: KeyboardEvent) => {
    if (isImeKeyEvent(e) || !inFlow) return;
    if (e.key === "Enter" && e.ctrlKey && e.shiftKey) {
      e.preventDefault();
      flow.prev();
    } else if (e.key === "Enter" && e.ctrlKey) {
      e.preventDefault();
      if (flow.step === 4 ? folderReady && !flow.busy : flow.canNext) primary();
    }
  };

  const optionErrors = flow.planErrors?.options ?? [];
  const itemErrors = flow.planErrors?.items ?? new Map<number, string>();
  const serverOther = flow.planErrors?.other ?? [];

  const steps = (
    <ol className="exp-steps" aria-label={t.stepsLabel}>
      {STEP_KEYS.map((key, i) => {
        const n = (i + 1) as Step;
        const current = flow.step === n;
        const reachable = inFlow && n < flow.step && !flow.busy;
        return (
          <li key={key} aria-current={current ? "step" : undefined} data-state={current ? "current" : n < flow.step ? "done" : "todo"}>
            <button type="button" className="exp-step" disabled={!reachable} onClick={() => flow.goTo(n)}>
              <span className="exp-step-no" aria-hidden="true">{n}</span> {t.steps[key]}
            </button>
          </li>
        );
      })}
    </ol>
  );

  return (
    <>
      <Dialog
        open
        wide
        title={t.title}
        onClose={flow.busy ? () => {} : onClose}
        actions={
          inFlow ? (
            <>
              {warnings.length > 0 && flow.step >= 3 ? (
                <Button className="exp-warn-toggle" aria-expanded={warningsOpen} onClick={() => setWarningsOpen(!warningsOpen)}>
                  {t.warningsToggle(warnings.length)} {warningsOpen ? "▲" : "▼"}
                </Button>
              ) : null}
              <span className="app-spacer" />
              <Button disabled={flow.step === 1 || flow.busy} onClick={flow.prev} title="Ctrl+Shift+Enter">
                {t.prev}
              </Button>
              <Button
                variant="primary"
                loading={flow.busy}
                disabled={flow.step === 4 ? !folderReady || flow.plan.data === undefined : !flow.canNext}
                title={flow.step < 4 ? (flow.nextReason ?? "Ctrl+Enter") : "Ctrl+Enter"}
                onClick={primary}
              >
                {flow.step === 4 ? t.doExport : t.next}
              </Button>
            </>
          ) : undefined
        }
      >
        <div ref={rootRef} className="exp-root" onKeyDown={onKeyDown}>
          {inFlow ? steps : null}
          {dirty && inFlow ? (
            <Banner tone="info" actions={onSave ? <Button size="sm" onClick={onSave}>{t.saveFirst}</Button> : undefined}>
              {t.unsavedInfo}
            </Banner>
          ) : null}
          {flow.planErrors !== undefined && flow.step === 2 && (optionErrors.length > 0 || itemErrors.size > 0) ? (
            <Banner tone="warning">{t.preview.routedBack}</Banner>
          ) : null}
          {serverOther.length > 0 && inFlow ? <IssueRows issues={serverOther.map((m) => ({ severity: "error" as const, code: "", message: m }))} ariaLabel={t.warningsRegion} /> : null}
          {flow.step >= 3 && inFlow && warnings.length > 0 && warningsOpen ? (
            <div role="status" aria-label={t.warningsRegion}>
              <IssueRows issues={warnings} ariaLabel={t.warningsRegion} />
            </div>
          ) : null}
          {flow.step === 1 ? (
            <ExporterStep
              loading={flow.exporters.loading}
              error={flow.exporters.error}
              exporters={flow.exporters.data}
              selectedId={flow.exporter?.id}
              onSelect={flow.chooseExporter}
              onRetry={flow.exporters.refetch}
              infoLink={infoLink}
            />
          ) : null}
          {flow.step === 2 && flow.exporter !== undefined ? (
            <ItemsStep
              exporter={flow.exporter}
              items={flow.items}
              nameOf={nameOf}
              itemErrors={itemErrors}
              onAdd={flow.addItem}
              onRemove={flow.removeItem}
              options={flow.options}
              onOptionsChange={flow.setOptions}
              optionErrors={optionErrors}
            />
          ) : null}
          {flow.step === 3 ? (
            <PreviewStep plan={flow.plan.data} loading={flow.plan.loading} fetching={flow.plan.fetching} error={flow.plan.error} onRetry={flow.plan.refetch} onBack={() => flow.goTo(2)} />
          ) : null}
          {flow.step === 4 ? (
            <DestinationStep
              destination={flow.destination}
              onDestination={flow.setDestination}
              roots={flow.roots}
              rootId={flow.rootId}
              onRoot={flow.setRootId}
              subdir={flow.subdir}
              onSubdir={flow.setSubdir}
              subdirProblem={flow.subdirProblem}
              subdirServerError={flow.subdirServerError}
              onConflict={flow.onConflict}
              onOnConflict={flow.setOnConflict}
              planFiles={planFiles}
              planFetching={flow.plan.fetching}
              busy={flow.busy}
              error={flow.runError}
            />
          ) : null}
          {flow.step === 5 && flow.outcome !== null ? <ResultStep outcome={flow.outcome} onClose={onClose} onAgain={flow.restart} /> : null}
        </div>
      </Dialog>
      <ConfirmDialog
        open={confirmOverwrite}
        danger
        title={t.overwrite.title}
        confirmLabel={t.overwrite.confirm}
        cancelLabel={t.overwrite.cancel}
        onCancel={() => setConfirmOverwrite(false)}
        onConfirm={() => {
          setConfirmOverwrite(false);
          void flow.run();
        }}
      >
        <p className="ac-text">{t.overwrite.body(overwriteCount(planFiles ?? []))}</p>
      </ConfirmDialog>
    </>
  );
}
