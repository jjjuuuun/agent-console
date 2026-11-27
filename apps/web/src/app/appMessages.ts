import { useCallback, useMemo } from "react";
import type { Issue } from "@agent-console/contracts";
import { issueMessage } from "../lib/issues";
import type { Translate } from "@agent-console/i18n";
import { useMessageTable } from "../i18n";
import { useShellMessages } from "./shellMessages";
import { createModuleTable } from "./moduleMessages";
import { createSettingsTable } from "./settingsUiMessages";

/** 앱 공용 문구 표(백엔드 선택·준비·텍스트 비교·알림·정의 저장·안내·서버 오류 코드). 묶음: `app`. */
export const createAppTable = (t: Translate) => ({
  /** 실행 백엔드 해결 카드(`BackendChooserCard`) */
  backendChooser: {
    title: t("backendChooser.title"),
    lead: (labels: readonly string[]) => (labels.length === 0 ? t("backendChooser.leadNone") : t("backendChooser.lead", { list: labels.join(", ") })),
    explain: t("backendChooser.explain"),
    /** [백엔드 바꾸기]로 연 카드(이미 값이 있는 상태): 문구는 "바꾼다"로, 메시지는 다시 보내지 않는다 */
    leadChange: t("backendChooser.leadChange"),
    explainChange: t("backendChooser.explainChange"),
    group: t("backendChooser.group"),
    saveNote: t("backendChooser.saveNote"),
    perNode: t("backendChooser.perNode"),
    submit: t("backendChooser.submit"),
    submitting: t("backendChooser.submitting"),
    none: t("backendChooser.none"),
    saveFailed: t("backendChooser.saveFailed"),
  },
  /** 실행 백엔드 인증·준비 상태와 [연결 테스트](앱 서버 연결 띠와는 다른 개념, ux-overhaul 15.8). 상태 이름·사유 문구는 서버가 준다 */
  backendReadiness: {
    sectionTitle: t("backendReadiness.sectionTitle"),
    sectionLead: t("backendReadiness.sectionLead"),
    loadFailed: t("backendReadiness.loadFailed"),
    recheck: t("backendReadiness.recheck"),
    recheckBusy: t("backendReadiness.recheckBusy"),
    checkedAt: (when: string) => t("backendReadiness.checkedAt", { when }),
    toneLabel: { ok: t("backendReadiness.toneLabel.ok"), warn: t("backendReadiness.toneLabel.warn"), error: t("backendReadiness.toneLabel.error"), unknown: t("backendReadiness.toneLabel.unknown") } as Readonly<Record<string, string>>,
    unknownSummary: t("backendReadiness.unknownSummary"),
    checks: t("backendReadiness.checks"),
    probeButton: t("backendReadiness.probeButton"),
    probeUnsupported: t("backendReadiness.probeUnsupported"),
    probeRunning: t("backendReadiness.probeRunning"),
    probeDialogTitle: t("backendReadiness.probeDialogTitle"),
    probeDialogBody: t("backendReadiness.probeDialogBody"),
    probeDialogRun: t("backendReadiness.probeDialogRun"),
    probeDialogCancel: t("backendReadiness.probeDialogCancel"),
    probeDialogRemember: t("backendReadiness.probeDialogRemember"),
    probePassed: t("backendReadiness.probePassed"),
    probePassedAgo: (when: string) => t("backendReadiness.probePassedAgo", { when }),
    probeOk: (seconds: string) => t("backendReadiness.probeOk", { seconds }),
    probeOkNoTime: t("backendReadiness.probeOkNoTime"),
    probeCheckedAt: (when: string) => t("backendReadiness.probeCheckedAt", { when }),
    probeFailedTitle: t("backendReadiness.probeFailedTitle"),
    probeRequestFailed: t("backendReadiness.probeRequestFailed"),
    probeDetails: t("backendReadiness.probeDetails"),
    probeReason: t("backendReadiness.probeReason"),
    probeResultLabel: t("backendReadiness.probeResultLabel"),
    chooserWarn: t("backendReadiness.chooserWarn"),
    chipLabel: (title: string, summary: string) => t("backendReadiness.chipLabel", { title, summary }),
    fixesLabel: t("backendReadiness.fixesLabel"),
  },
  /** 텍스트 비교(`TextDiff`) 기본 문구. 앱 루트에서 한 번 주입한다(개별 화면이 따로 주면 그쪽이 우선). */
  textDiff: {
    unchangedLines: t("textDiff.unchangedLines"),
    split: t("textDiff.split"),
    unified: t("textDiff.unified"),
    toolbar: t("textDiff.toolbar"),
    before: t("textDiff.before"),
    after: t("textDiff.after"),
  },
  notifications: {
    title: "Agent Console",
    test: { title: "Agent Console", body: t("notifications.test.body") },
    grant: {
      unsupported: t("notifications.grant.unsupported"),
      insecure: t("notifications.grant.insecure"),
      default: t("notifications.grant.default"),
      granted: t("notifications.grant.granted"),
      denied: t("notifications.grant.denied"),
      deniedHelp: t("notifications.grant.deniedHelp"),
      label: t("notifications.grant.label"),
    },
    request: t("notifications.request"),
    sendTest: t("notifications.sendTest"),
    hearSound: t("notifications.hearSound"),
    needPermission: t("notifications.needPermission"),
    soundLocked: t("notifications.soundLocked"),
    eventsEmpty: t("notifications.eventsEmpty"),
    eventsAdd: t("notifications.eventsAdd"),
    eventsAddButton: t("notifications.eventsAddButton"),
    eventsRemove: (name: string) => t("notifications.eventsRemove", { name }),
    eventsList: t("notifications.eventsList"),
    /** 이벤트 이름 -> 알림 본문 템플릿. 비어 있으면 일반 형식 `{이름} · {요청자}`. 키는 사용자 이벤트가 아니라 문구 데이터 */
    templates: {} as Record<string, string>,
    live: { permissionChanged: (label: string) => t("notifications.live.permissionChanged", { label }) },
  },
  definition: {
    /** 첨부 목록 아래 오류 줄(definition/AttachmentProblems) */
    attachProblems: {
      label: t("definition.attachProblems.label"),
      masked: t("definition.attachProblems.masked"),
    },
    saved: t("definition.saved"),
    dirty: t("definition.dirty"),
    saving: t("definition.saving"),
    failed: t("definition.failed"),
    retry: t("definition.retry"),
    savedToast: t("definition.savedToast"),
    missingVersion: t("definition.missingVersion"),
    /** 저장은 됐지만 서버가 경고한 이슈(`X-Console-Issues`) */
    issues: { title: t("definition.issues.title"), region: t("definition.issues.region"), at: (path: string) => `(${path})`, pathSeparator: " › ", pathIndex: (n: number) => t("definition.issues.pathIndex", { n }) },
    conflict: {
      region: t("definition.conflict.region"),
      title: t("definition.conflict.title"),
      body: t("definition.conflict.body"),
      savedAt: (when: string) => t("definition.conflict.savedAt", { when }),
      loadServer: t("definition.conflict.loadServer"),
      saveCopy: t("definition.conflict.saveCopy"),
      overwrite: t("definition.conflict.overwrite"),
      loadServerTitle: t("definition.conflict.loadServerTitle"),
      loadServerBody: t("definition.conflict.loadServerBody"),
      overwriteTitle: t("definition.conflict.overwriteTitle"),
      overwriteBody: t("definition.conflict.overwriteBody"),
      saveDisabled: t("definition.conflict.saveDisabled"),
    },
    unsaved: {
      title: t("definition.unsaved.title"),
      body: t("definition.unsaved.body"),
      stay: t("definition.unsaved.stay"),
      leave: t("definition.unsaved.leave"),
    },
  },
  hints: { dismiss: t("hints.dismiss") },
  severity: { error: t("severity.error"), warning: t("severity.warning"), info: t("severity.info") } as Record<"error" | "warning" | "info", string>,
  errorByCode: (code: string): string | undefined => {
    const key = `errorByCode.${code}`;
    const text = t(key);
    return text === key ? undefined : text;
  },
  issueValidators: (validator: string): string | undefined => {
    const key = `issueValidators.${validator}`;
    const text = t(key);
    return text === key ? undefined : text;
  },
} as const);

export type AppTable = ReturnType<typeof createAppTable>;

/**
 * 앱 문구 표 전체(셸 + 앱 공용 + 기능 모듈 + 설정 화면 공용). 한 화면 언어로 만든 같은 모양의 객체.
 * 옛 `messages` 객체를 대신한다. 컴포넌트·훅 안에서 부른다.
 */
export function useAppMessages() {
  const shell = useShellMessages();
  const app = useMessageTable("app", createAppTable);
  const modules = useMessageTable("modules", createModuleTable);
  const settings = useMessageTable("settingsUi", createSettingsTable);
  return useMemo(() => ({ ...shell, ...app, ...modules, ...settings }), [shell, app, modules, settings]);
}

export type AppMessages = ReturnType<typeof useAppMessages>;

/** 현재 화면 언어의 검증기 문장이 들어간 `issueMessage`(컴포넌트 안에서 부른다). */
export function useIssueMessage(): (issue: Issue) => string {
  const { issueValidators } = useAppMessages();
  return useCallback((issue) => issueMessage(issue, issueValidators), [issueValidators]);
}
