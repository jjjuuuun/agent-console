/**
 * 실행 시작 결과 안내(작업·계획 탭 공통): 관문이면 `GateNotice`(문서 열기·규칙에서 보기), 실패면 오류 배너(+ [가져와서 실행]).
 * 한 번에 하나만 보인다. 문구는 서버가 준 것을 그대로 쓰고, 이 컴포넌트는 종류만 가른다.
 */
import { Banner, Button } from "@agent-console/ui";
import { GateNotice } from "@agent-console/sdd-view";
import type { SddGateBlockedDetails } from "@agent-console/contracts/sdd";
import { sddMessages as m, viewMessages } from "./messages";
import type { TaskRunner } from "./useTaskRunner";

export interface RunNoticeViewProps {
  runner: TaskRunner;
  /** 러너 밖에서 온 관문(예: 상태 바꾸기 관문). 러너 안내가 있으면 러너가 우선한다 */
  extraGate?: SddGateBlockedDetails | null;
  onDismissExtra?: () => void;
  documentTitles: Readonly<Record<string, string>>;
  onOpenDocument: (documentId: string) => void;
  onOpenRules: () => void;
  /** 프로젝트가 있을 때만 [가져와서 실행]을 보인다 */
  canImport: boolean;
}

export function RunNoticeView({ runner, extraGate = null, onDismissExtra, documentTitles, onOpenDocument, onOpenRules, canImport }: RunNoticeViewProps) {
  const notice = runner.notice;
  const gate = notice?.kind === "gate" ? notice.details : extraGate;
  return (
    <>
      {gate === null ? null : (
        <GateNotice
          details={gate}
          documentTitles={documentTitles}
          onOpenDocument={onOpenDocument}
          onDismiss={() => { onDismissExtra?.(); runner.dismiss(); }}
          actions={<button type="button" className="app-link-btn" onClick={onOpenRules}>{m.gate.openRules}</button>}
          messages={viewMessages}
        />
      )}
      {notice?.kind === "error" ? (
        <Banner
          tone={notice.view?.tone ?? "danger"}
          data-testid="sdd-run-error"
          actions={
            <>
              {canImport && notice.view?.fix === "importAndRun" && notice.view.notImported?.inLibrary === true ? (
                <Button size="sm" variant="primary" onClick={() => runner.importAndRun(notice)}>{m.run.importAndRun}</Button>
              ) : null}
              <Button size="sm" onClick={runner.dismiss}>{m.run.dismiss}</Button>
            </>
          }
        >
          {notice.message}
        </Banner>
      ) : null}
    </>
  );
}
