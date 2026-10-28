import type { ReactElement } from "react";

import type { Translate } from "./messages";
import type { FolderPickStatus } from "./types";

/** 선택 흐름의 화면 단계. `idle`은 아직 아무것도 하지 않음, `waiting`은 OS 선택 창 대기, 나머지는 `FolderPickStatus`와 같다. */
export type FolderSelectPhase = "idle" | "waiting" | FolderPickStatus;

export interface FolderPickStatusProps {
  id: string;
  t: Translate;
  phase: FolderSelectPhase;
  /** 대기가 길어져 hint를 진하게 하고 [앱 안에서 찾아보기]를 보일 때. */
  escapeVisible: boolean;
  /** `unavailable`·`failed`의 원인 문구(있으면 "자세히"로 접어 둔다). */
  reason: string | null;
  disabled?: boolean;
  onRetry: () => void;
  onUseBrowser: () => void;
}

/**
 * 선택 흐름 상태 줄. 항상 렌더되는 `role="status"` 영역이라 문구가 바뀌면 스크린 리더가 알린다.
 * `picked`·`idle`은 비어 있다(결과는 선택한 폴더 상자와 확인 결과가 보여 준다).
 */
export function FolderPickStatusLine({ id, t, phase, escapeVisible, reason, disabled, onRetry, onUseBrowser }: FolderPickStatusProps): ReactElement {
  const btn = (label: string, onClick: () => void, key: string) => (
    <button key={key} type="button" className="ac-fp-btn" data-size="sm" onClick={onClick} disabled={disabled}>{label}</button>
  );
  let body: ReactElement | null = null;
  let tone: "info" | "warning" | "danger" | null = null;
  switch (phase) {
    case "waiting":
      body = (
        <>
          <span className="ac-fp-pick-hint" data-strong={escapeVisible ? "true" : undefined}>{t("folder.pick.waiting_hint")}</span>
          {escapeVisible ? btn(t("folder.pick.use_browser"), onUseBrowser, "browser") : null}
        </>
      );
      break;
    case "cancelled":
      body = <span className="ac-fp-pick-hint">{t("folder.pick.cancelled")}</span>;
      break;
    case "unavailable":
    case "failed":
      tone = phase === "failed" ? "danger" : "info";
      body = (
        <>
          <span>{t(phase === "failed" ? "folder.pick.failed" : "folder.pick.unavailable")}</span>
          {reason ? (
            <details className="ac-fp-pick-reason">
              <summary>{t("folder.pick.reason")}</summary>
              <span className="ac-fp-mono ac-mono-wrap">{reason}</span>
            </details>
          ) : null}
          {phase === "failed" ? btn(t("folder.pick.retry"), onRetry, "retry") : null}
        </>
      );
      break;
    case "busy":
    case "timeout":
      tone = "warning";
      body = (
        <>
          <span>{t(phase === "busy" ? "folder.pick.busy" : "folder.pick.timeout")}</span>
          <span className="ac-fp-pick-actions">
            {btn(t("folder.pick.retry"), onRetry, "retry")}
            {btn(t("folder.pick.use_browser"), onUseBrowser, "browser")}
          </span>
        </>
      );
      break;
    case "idle":
    case "picked":
      break;
  }
  return (
    <div id={id} className="ac-fp-pick-status" role="status" aria-live="polite" data-phase={phase} data-tone={tone ?? undefined}>
      {body}
    </div>
  );
}
