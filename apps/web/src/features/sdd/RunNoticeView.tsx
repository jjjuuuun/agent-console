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
  /**
   * 어느 안내를 이 자리에 그릴지 거른다(작업 키 또는 undefined=작업 없는 안내). 기본은 모두.
   * 작업 탭은 머리에 `(k) => k === undefined`, 행 아래에 `(k) => k === 그 행의 키`를 준다(screen-sdd §7.4).
   */
  accepts?: (taskKey: string | undefined) => boolean;
  /** 러너 밖 관문(`extraGate`)이 속한 작업 키 */
  extraGateTaskKey?: string | undefined;
  /** 프로젝트가 있을 때만 [가져와서 실행]을 보인다 */
  canImport: boolean;
}

export function RunNoticeView({ runner, extraGate = null, onDismissExtra, documentTitles, onOpenDocument, onOpenRules, canImport, accepts = () => true, extraGateTaskKey }: RunNoticeViewProps) {
  const own = runner.notice;
  const notice = own !== null && accepts(own.kind === "gate" ? own.taskKey : own.task.key) ? own : null;
  // 러너의 관문 안내가 있으면 러너가 우선한다(같은 관문을 두 자리에 그리지 않는다)
  const gate = notice?.kind === "gate" ? notice.details : own?.kind === "gate" ? null : extraGate !== null && accepts(extraGateTaskKey) ? extraGate : null;
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
