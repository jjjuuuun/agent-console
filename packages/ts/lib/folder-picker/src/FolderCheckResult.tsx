import { type ReactElement, type ReactNode } from "react";

import type { FolderCheckState } from "./checkState";
import type { Translate } from "./messages";
import { middleEllipsis } from "./middleEllipsis";
import { useAfter } from "./useAfter";
import { withDir } from "./withDir";

export interface FolderCheckResultProps {
  state: FolderCheckState;
  t: Translate;
  /** 결과 영역 id. 입력의 `aria-describedby`가 가리킨다. */
  id: string;
  /** [이 경로에 폴더 만들기]. */
  onCreate?: () => void;
  creating?: boolean;
  /** [다시 확인]. */
  onRecheck?: () => void;
  /** [열기]·[그 프로젝트 열기]. */
  onOpenProject?: (projectId: string) => void;
  /** 앱이 프로젝트 구성을 담는 폴더 이름(문구의 `{dir}`, 고정폭으로 그린다). 없으면 `{dir}` 문구를 쓰지 않는다. */
  configDir?: string;
  /** 확인 중 표시를 미루는 시간(ms). 기본 150. */
  checkingDelayMs?: number;
}

const OVERLAP_PATH_CELLS = 40;

/**
 * 폴더 확인 결과 영역. 고정 높이(최소 44px) + `role="status"` `aria-live="polite"`라 상태가 바뀌어도 아래가 움직이지 않는다.
 * 문구는 `t`로 받고, 버튼은 콜백이 있을 때만 그린다.
 */
export function FolderCheckResult({ state, t, id, onCreate, creating, onRecheck, onOpenProject, configDir, checkingDelayMs = 150 }: FolderCheckResultProps): ReactElement {
  const showChecking = useAfter(state.group === "checking", checkingDelayMs);
  const visible = state.tone !== null && (state.group !== "checking" || showChecking);
  const c = state.check;
  const outcome = state.outcome;

  let body: ReactNode = null;
  let actions: ReactNode = null;
  let why: ReactNode = null;
  if (visible) {
    const saved = c?.path ?? null;
    const savedLines =
      saved !== null ? (
        <>
          <span className="ac-fp-saved"><span className="ac-fp-saved-label">{t("folder.check.saved_as")}</span> <span className="ac-fp-mono ac-mono-wrap">{saved}</span></span>
          {state.forInput !== null && saved !== state.forInput.trim() ? <span className="ac-fp-line">{t("folder.check.saved_as_diff", { path: saved })}</span> : null}
        </>
      ) : null;
    const btn = (label: string, onClick: (() => void) | undefined, key: string, disabled = false) =>
      onClick ? (
        <button key={key} type="button" className="ac-fp-btn" onClick={onClick} disabled={disabled}>{label}</button>
      ) : null;
    switch (state.id) {
      case "checking": body = <span>{t("folder.check.checking")}</span>; break;
      case "ok": body = <><span className="ac-fp-line">{t("folder.check.ok")}</span>{savedLines}</>; break;
      case "ok_readonly":
        body = (
          <>
            <span className="ac-fp-line">{configDir ? withDir(t("folder.check.readonly_config"), configDir) : t("folder.check.readonly")}</span>
            {savedLines}
          </>
        );
        break;
      case "manifest_found": {
        const m = c?.manifest;
        const detail = `${m?.name ? t("folder.check.manifest_detail_name", { name: m.name }) : ""}${m?.count != null ? t("folder.check.manifest_detail_count", { n: m.count }) : ""}`;
        body = <><span className="ac-fp-line">{t("folder.check.manifest_found", { detail })}</span>{savedLines}</>;
        break;
      }
      case "manifest_invalid": body = <><span className="ac-fp-line">{t("folder.check.manifest_invalid")}</span>{savedLines}</>; break;
      case "missing":
        body = <span className="ac-fp-line">{t("folder.check.missing")}</span>;
        actions = btn(creating ? t("folder.check.creating") : t("folder.check.create"), onCreate, "create", creating === true);
        break;
      case "missing_parent": body = <span>{t("folder.check.missing_parent")}</span>; break;
      case "not_directory": body = <span>{t("folder.check.not_directory")}</span>; break;
      case "no_access": body = <span>{t("folder.check.no_access")}</span>; break;
      case "invalid": {
        const specific = c?.problem ? `folder.check.invalid.${c.problem}` : "";
        const text = specific && t(specific) !== specific ? t(specific) : t("folder.check.invalid");
        body = <span>{text}</span>;
        break;
      }
      case "same_path":
        body = <span>{t("folder.check.same_path")}</span>;
        actions = btn(t("folder.check.recheck"), onRecheck, "recheck");
        break;
      case "remote_disabled": body = <span>{t("folder.check.remote_disabled")}</span>; break;
      case "error":
        body = <span>{t("folder.check.error")}</span>;
        actions = btn(t("folder.check.recheck"), onRecheck, "recheck");
        break;
      case "taken":
      case "taken_archived":
        if (outcome?.kind === "taken") {
          body = <span>{t(state.id === "taken" ? "folder.check.taken" : "folder.check.taken_archived", { name: outcome.name })}</span>;
          if (state.id === "taken") actions = btn(t("folder.check.taken_open"), onOpenProject ? () => onOpenProject(outcome.projectId) : undefined, "open");
        }
        break;
      case "overlap_parent":
      case "overlap_child":
        if (outcome?.kind === "overlap") {
          body = <span>{t(state.id === "overlap_parent" ? "folder.check.overlap_parent" : "folder.check.overlap_child", { name: outcome.name, path: middleEllipsis(outcome.path, OVERLAP_PATH_CELLS) })}</span>;
          actions = btn(t("folder.check.overlap_open"), onOpenProject ? () => onOpenProject(outcome.projectId) : undefined, "open");
          why = <span className="ac-fp-why">{t("folder.check.overlap_why")}</span>;
        }
        break;
      case "idle": break;
    }
  }

  return (
    <div id={id} className="ac-fp-result" role="status" aria-live="polite" data-state={visible ? state.id : "idle"} data-group={state.group}>
      {visible && state.tone ? (
        <div className="ac-fp-banner" data-tone={state.tone}>
          <span className="ac-fp-banner-icon" aria-hidden="true" />
          <div className="ac-fp-banner-body">
            {body}
            {why}
          </div>
          {actions ? <div className="ac-fp-banner-actions">{actions}</div> : null}
        </div>
      ) : null}
    </div>
  );
}
