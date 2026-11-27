import { useCallback } from "react";
import { useT, type Translate } from "@agent-console/i18n";
import type { ConnectionStatus } from "@agent-console/api-client";
import type { ThemeChoice } from "@agent-console/ui";
import { useMessageTable } from "../i18n";
import { useOptionalI18n } from "../i18n/AppI18n";

/** 앱 셸(사이드바·빠른 이동·단축키·배너·부팅 알림) 문구 표. */
export const createShellMessages = (t: Translate) => ({
  app: { name: "Agent Console", mainLabel: t("app.mainLabel"), skipToMain: t("app.skipToMain") },
  boot: {
    authExpired: t("boot.authExpired"),
    reload: t("boot.reload"),
    authRegion: t("boot.authRegion"),
    /** 계약 버전 불일치 배너(5.7R.36): 두 값 + 낡은 쪽에 맞는 조치 */
    versionMismatch: (server: string, web: string) => t("boot.versionMismatch", { server, web }),
    versionFixServer: t("boot.versionFixServer"),
    versionFixWeb: t("boot.versionFixWeb"),
    versionFixUnknown: t("boot.versionFixUnknown"),
    versionRegion: t("boot.versionRegion"),
  },
  common: {
    cancel: t("common.cancel"),
    close: t("common.close"),
    retry: t("common.retry"),
    loadMore: t("common.loadMore"),
    loadingMore: t("common.loadingMore"),
    /** 목록이 다른 출처 기록으로 넘어가는 자리의 구분선. 키는 서버가 주는 출처 값, 모르는 값은 값 그대로 보인다 */
    recordSources: { project: t("common.recordSources.project"), app: t("common.recordSources.app") } as Readonly<Record<string, string>>,
    details: t("common.details"),
    requestFailed: t("common.requestFailed"),
    notifications: t("common.notifications"),
    copy: t("common.copy"),
    copied: t("common.copied"),
    refreshing: t("common.refreshing"),
    loadingScreen: t("common.loadingScreen"),
    screenLoadFailed: t("common.screenLoadFailed"),
    screenLoadFailedBody: t("common.screenLoadFailedBody"),
    screenCrashed: t("common.screenCrashed"),
    reload: t("common.reload"),
    refreshFailed: t("common.refreshFailed"),
    yes: t("common.yes"),
    no: t("common.no"),
    none: t("common.none"),
  },
  nav: {
    label: t("nav.label"),
    chat: t("nav.chat"),
    teams: t("nav.teams"),
    agents: t("nav.agents"),
    resources: t("nav.resources"),
    runs: t("nav.runs"),
    memory: t("nav.memory"),
    specs: t("nav.specs"),
    specTemplates: t("nav.specTemplates"),
    wiki: t("nav.wiki"),
    wikiRules: t("nav.wikiRules"),
    usage: t("nav.usage"),
    logs: t("nav.logs"),
    settings: t("nav.settings"),
    /** 사이드바 묶음 제목(`RouteGroupDef.titleKey`) */
    groups: { config: t("nav.groups.config"), run: t("nav.groups.run"), observe: t("nav.groups.observe") },
    disabledToast: (title: string) => t("nav.disabledToast", { title }),
    loadingItems: t("nav.loadingItems"),
  },
  notFound: { title: t("notFound.title"), toHome: t("notFound.toHome") },
  placeholder: {
    body: t("placeholder.body"),
    hint: t("placeholder.hint"),
  },
  connection: {
    /** 상태 글자(설정 → 서버 정보·도움말의 "앱 서버 연결" 줄). "앱 서버" = 이 프로그램을 돌리는 로컬 서버 */
    state: {
      idle: t("connection.state.idle"),
      connecting: t("connection.state.connecting"),
      open: t("connection.state.open"),
      reconnecting: t("connection.state.reconnecting"),
      closed: t("connection.state.closed"),
    } satisfies Record<ConnectionStatus, string>,
    rowLabel: t("connection.rowLabel"),
    note: t("connection.note"),
    line: (state: string, note: string) => t("connection.line", { state, note }),
    banner: {
      connecting: t("connection.banner.connecting"),
      reconnecting: t("connection.banner.reconnecting"),
      closed: t("connection.banner.closed"),
      closedAgain: t("connection.banner.closedAgain"),
      retrying: t("connection.banner.retrying"),
      recovered: t("connection.banner.recovered"),
      retry: t("connection.banner.retry"),
      retryBusy: t("connection.banner.retryBusy"),
      reload: t("connection.banner.reload"),
      region: t("connection.banner.region"),
    },
  },
  theme: {
    names: { dark: t("theme.names.dark"), light: t("theme.names.light"), system: t("theme.names.system") } satisfies Record<ThemeChoice, string>,
    toggle: (current: string, next: string) => t("theme.toggle", { current, next }),
  },
  sidebar: {
    brand: "Agent Console",
    region: t("sidebar.region"),
    brandLink: t("sidebar.brandLink"),
    collapse: t("sidebar.collapse"),
    expand: t("sidebar.expand"),
    /** 접기 버튼: 이름은 고정, 상태는 `aria-expanded`, 툴팁은 단축키를 덧붙인다 */
    toggle: t("sidebar.toggle"),
    toggleTitle: (shortcut: string) => t("sidebar.toggleTitle", { shortcut }),
    quickNav: t("sidebar.quickNav"),
    /** 하단 도구줄 항목 툴팁 `이름 (단축키)` */
    withShortcut: (label: string, shortcut: string) => `${label} (${shortcut})`,
    pendingBadge: (n: number) => t("sidebar.pendingBadge", { n }),
    tools: t("sidebar.tools"),
    drawerClose: t("sidebar.drawerClose"),
  },
  /** 단축키 동작 이름. 키는 `ShortcutDef.titleKey`. */
  shortcuts: {
    paletteOpen: t("shortcuts.paletteOpen"),
    gotoPrefix: (target: string) => t("shortcuts.gotoPrefix", { target }),
    pendingJump: t("shortcuts.pendingJump"),
    chatStop: t("shortcuts.chatStop"),
    chatFocusComposer: t("shortcuts.chatFocusComposer"),
    chatPrev: t("shortcuts.chatPrev"),
    chatNext: t("shortcuts.chatNext"),
    sidebarToggle: t("shortcuts.sidebarToggle"),
    helpOpen: t("shortcuts.helpOpen"),
    projectSwitch: t("shortcuts.projectSwitch"),
    runsSearch: t("shortcuts.runsSearch"),
    settingsSearch: t("shortcuts.settingsSearch"),
    runsFilters: t("shortcuts.runsFilters"),
    runsNew: t("shortcuts.runsNew"),
    runsTab1: t("shortcuts.runsTab1"),
    runsTab2: t("shortcuts.runsTab2"),
    runsTab3: t("shortcuts.runsTab3"),
    runsTab4: t("shortcuts.runsTab4"),
    runsTab5: t("shortcuts.runsTab5"),
    runsTab6: t("shortcuts.runsTab6"),
    runsTab7: t("shortcuts.runsTab7"),
    runsNodeNext: t("shortcuts.runsNodeNext"),
    runsNodePrev: t("shortcuts.runsNodePrev"),
    runsCancel: t("shortcuts.runsCancel"),
    usageRefresh: t("shortcuts.usageRefresh"),
    logsRefresh: t("shortcuts.logsRefresh"),
    logsScan: t("shortcuts.logsScan"),
    logsFocusSearch: t("shortcuts.logsFocusSearch"),
    logsFocusFilter: t("shortcuts.logsFocusFilter"),
    logsPlayToggle: t("shortcuts.logsPlayToggle"),
    logsStepBack: t("shortcuts.logsStepBack"),
    logsStepForward: t("shortcuts.logsStepForward"),
    logsSpeedDown: t("shortcuts.logsSpeedDown"),
    logsSpeedUp: t("shortcuts.logsSpeedUp"),
    logsErrorsOnly: t("shortcuts.logsErrorsOnly"),
    logsToggleFlow: t("shortcuts.logsToggleFlow"),
    logsFlowView: t("shortcuts.logsFlowView"),
    logsToggleView: t("shortcuts.logsToggleView"),
    logsSessionInfo: t("shortcuts.logsSessionInfo"),
    logsViewMenu: t("shortcuts.logsViewMenu"),
    logsToggleDetail: t("shortcuts.logsToggleDetail"),
    logsHandoffToggle: t("shortcuts.logsHandoffToggle"),
    logsEditToggle: t("shortcuts.logsEditToggle"),
    logsAddWidget: t("shortcuts.logsAddWidget"),
    logsPrevDashboard: t("shortcuts.logsPrevDashboard"),
    logsNextDashboard: t("shortcuts.logsNextDashboard"),
    logsUndo: t("shortcuts.logsUndo"),
    logsCategoryFocus: t("shortcuts.logsCategoryFocus"),
    logsRunTab: t("shortcuts.logsRunTab"),
    usagePeek: t("shortcuts.usagePeek"),
    save: t("shortcuts.save"),
    scopeGlobal: t("shortcuts.scopeGlobal"),
    escName: t("shortcuts.escName"),
    escLayers: t("shortcuts.escLayers"),
    plain: t("shortcuts.plain"),
    helpTitle: t("shortcuts.helpTitle"),
    helpThisScreen: t("shortcuts.helpThisScreen"),
    helpGlobal: t("shortcuts.helpGlobal"),
    helpFixed: t("shortcuts.helpFixed"),
    disabled: t("shortcuts.disabled"),
    emptyScreen: t("shortcuts.emptyScreen"),
    replayHints: t("shortcuts.replayHints"),
    replayHintsDone: t("shortcuts.replayHintsDone"),
    replayStart: t("shortcuts.replayStart"),
    sddTaskStatus: t("shortcuts.sddTaskStatus"),
    sddTaskRun: t("shortcuts.sddTaskRun"),
    sddTaskOpen: t("shortcuts.sddTaskOpen"),
    sddTaskMenu: t("shortcuts.sddTaskMenu"),
    sddDocModeEdit: t("shortcuts.sddDocModeEdit"),
    sddDocModePreview: t("shortcuts.sddDocModePreview"),
    sddDocModeSplit: t("shortcuts.sddDocModeSplit"),
    sddDocPrev: t("shortcuts.sddDocPrev"),
    sddDocNext: t("shortcuts.sddDocNext"),
    sddDocGoto: t("shortcuts.sddDocGoto"),
    wikiNew: t("shortcuts.wikiNew"),
    wikiSearch: t("shortcuts.wikiSearch"),
    wikiEdit: t("shortcuts.wikiEdit"),
    wikiModeEdit: t("shortcuts.wikiModeEdit"),
    wikiModeView: t("shortcuts.wikiModeView"),
    wikiModeSplit: t("shortcuts.wikiModeSplit"),
    wikiPanel: t("shortcuts.wikiPanel"),
    wikiTree: t("shortcuts.wikiTree"),
    wikiPrev: t("shortcuts.wikiPrev"),
    wikiNext: t("shortcuts.wikiNext"),
    wikiInsertLink: t("shortcuts.wikiInsertLink"),
    libNew: t("shortcuts.libNew"),
    libSearch: t("shortcuts.libSearch"),
    libRename: t("shortcuts.libRename"),
    libDelete: t("shortcuts.libDelete"),
    libView: t("shortcuts.libView"),
    libMove: t("shortcuts.libMove"),
    libLabels: t("shortcuts.libLabels"),
    libStartChat: t("shortcuts.libStartChat"),
    libValidate: t("shortcuts.libValidate"),
    libPanelTab: t("shortcuts.libPanelTab"),
    libAddMenu: t("shortcuts.libAddMenu"),
    libTogglePreview: t("shortcuts.libTogglePreview"),
    libToggleEntry: t("shortcuts.libToggleEntry"),
    libToggleExit: t("shortcuts.libToggleExit"),
    libToggleAsk: t("shortcuts.libToggleAsk"),
    libOpenParent: t("shortcuts.libOpenParent"),
    libEditEdge: t("shortcuts.libEditEdge"),
    runsParent: t("shortcuts.runsParent"),
    runsOpenChild: t("shortcuts.runsOpenChild"),
    runsRunPrev: t("shortcuts.runsRunPrev"),
    runsRunNext: t("shortcuts.runsRunNext"),
  },
  palette: {
    title: t("palette.title"),
    inputLabel: t("palette.inputLabel"),
    placeholder: t("palette.placeholder"),
    empty: t("palette.empty"),
    loading: t("palette.loading"),
    groups: { screens: t("palette.groups.screens"), conversations: t("palette.groups.conversations"), teams: t("palette.groups.teams"), agents: t("palette.groups.agents"), resources: t("palette.groups.resources"), runs: t("palette.groups.runs"), actions: t("palette.groups.actions"), recent: t("palette.groups.recent") },
    pending: t("palette.pending"),
    /** "언어 바꾸기…" 명령이 여는 언어 목록 */
    language: { title: t("palette.language.title"), inputLabel: t("palette.language.inputLabel"), placeholder: t("palette.language.placeholder"), auto: t("palette.language.auto"), current: t("palette.language.current"), partial: t("palette.language.partial"), empty: t("palette.language.empty") },
    actions: {
      themeCycle: t("palette.actions.themeCycle"),
      sidebarToggle: t("palette.actions.sidebarToggle"),
      jumpPending: t("palette.actions.jumpPending"),
      usagePeek: t("palette.actions.usagePeek"),
      chatNew: t("palette.actions.chatNew"),
      runNew: t("palette.actions.runNew"),
      libTeamNew: t("palette.actions.libTeamNew"),
      libAgentNew: t("palette.actions.libAgentNew"),
      libResourceNew: t("palette.actions.libResourceNew"),
      libTeamSave: t("palette.actions.libTeamSave"),
      libTeamValidate: t("palette.actions.libTeamValidate"),
      libTeamStartChat: t("palette.actions.libTeamStartChat"),
      exportCurrent: t("palette.actions.exportCurrent"),
      projectSwitch: t("palette.actions.projectSwitch"),
      projectManage: t("palette.actions.projectManage"),
      projectNew: t("palette.actions.projectNew"),
    },
  },
  /** 실행 상태 이름(서버 값 → 글자). 모르는 값은 호출 쪽이 원문을 쓴다 */
  runStatus: Object.fromEntries(["queued", "running", "paused", "waiting", "completed", "failed", "cancelled", "interrupted"].map((k) => [k, t(`runStatus.${k}`)])) as Record<string, string>,
  pending: {
    none: t("pending.none"),
    live: (n: number) => t("pending.live", { n }),
  },
  pwa: {
    updateAvailable: t("pwa.updateAvailable"),
    updateNow: t("pwa.updateNow"),
    updateConfirmTitle: t("pwa.updateConfirmTitle"),
    updateConfirmBody: t("pwa.updateConfirmBody"),
    updateConfirmYes: t("pwa.updateConfirmYes"),
  },
} as const);

export type ShellMessages = ReturnType<typeof createShellMessages>;

/** 앱 셸 문구 표(현재 화면 언어). */
export function useShellMessages(): ShellMessages {
  return useMessageTable("shell", createShellMessages);
}

/** `titleKey`를 찾아 볼 묶음(앞에서부터). 키는 묶음 안의 점 표기 경로이고, 모든 묶음에 없으면 키 그대로 돌려준다. */
const LOOKUP_NAMESPACES = ["shell", "modules", "app", "settingsUi"] as const;

/**
 * 라우트·명령·단축키·설정 데이터의 `titleKey`(점 표기 경로)를 현재 화면 언어의 글자로 바꾸는 함수.
 * 셸·모듈·앱·설정 묶음에서 차례로 찾고, 없으면 키 그대로 돌려준다.
 */
export function useLookupMessage(): (key: string) => string {
  const i18n = useOptionalI18n();
  const tShell = useT("shell");
  const tModules = useT("modules");
  const tApp = useT("app");
  const tSettings = useT("settingsUi");
  return useCallback(
    (key) => {
      const translators = [tShell, tModules, tApp, tSettings];
      for (const [i, ns] of LOOKUP_NAMESPACES.entries()) {
        if (i18n?.exists(key, { ns }) === true) return translators[i]!(key);
      }
      return key;
    },
    [i18n, tShell, tModules, tApp, tSettings],
  );
}
