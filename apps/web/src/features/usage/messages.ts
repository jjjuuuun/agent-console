import type { Tone } from "@agent-console/ui";
import type { Translate } from "@agent-console/i18n";
import { useMessageTable } from "../../i18n";

/** 사용량 화면 문구와 상태·신뢰 등급 표시 표. 창 이름·출처 id는 여기에 없다(서버·설정 데이터). 표에 없는 상태·신뢰 값은 원문 그대로 중립 톤으로 보인다. */
export function createUsageMessages(t: Translate) {
  return {
    title: t("title"),
    /** 연결 안내 패널 안에 들어가는 한 줄(예전 상단 배너를 흡수) */
    hint: t("hint"),
    refresh: t("refresh"),
    refreshing: t("refreshing"),
    lastUpdated: (when: string) => t("lastUpdated", { when }),
    loading: t("loading"),
    loadFailed: t("loadFailed"),
    staleData: t("staleData"),
    /** 상태 값 → 한글 라벨과 칩 톤(칩에만 적용, 게이지 색에는 쓰지 않는다) */
    status: {
      allowed: {
        label: t("status.allowed.label"),
        tone: "success",
      },
      allowed_warning: {
        label: t("status.allowed_warning.label"),
        tone: "warning",
      },
      rejected: {
        label: t("status.rejected.label"),
        tone: "danger",
      },
      // 활동 없음(톤 없음). aria는 접근성 이름. 상태 어휘는 열려 있어 표에 없는 값은 원문으로 보인다.
      idle: {
        label: t("status.idle.label"),
        aria: (window: string) => t("status.idle.aria", { window }),
      },
    } as Record<string, { label: string; tone?: Tone; aria?: (window: string) => string }>,
    /** 신뢰 등급 값 → 한글 라벨 */
    trust: {
      official: t("trust.official"),
      observed: t("trust.observed"),
      estimated: t("trust.estimated"),
      unofficial: t("trust.unofficial"),
    } as Record<string, string>,
    cards: {
      region: t("cards.region"),
      empty: t("cards.empty"),
      emptyBody: t("cards.emptyBody"),
      howToConnect: t("cards.howToConnect"),
      headline: (pct: string) => t("cards.headline", { pct }),
      tokens: (n: string) => t("cards.tokens", { n }),
      noRatio: t("cards.noRatio"),
      noRatioHeadline: t("cards.noRatioHeadline"),
      noValue: t("cards.noValue"),
      resets: (rel: string) => t("cards.resets", { rel }),
      resetsUnderMinute: t("cards.resetsUnderMinute"),
      resetsLine: (rel: string, abs: string) => t("cards.resetsLine", { rel, abs }),
      resetsAt: (abs: string) => t("cards.resetsAt", { abs }),
      /** 기준보다 먼 초기화는 상대 시간 대신 날짜로(사이드바 표시기) */
      resetsOnDate: (date: string) => t("cards.resetsOnDate", { date }),
      resetsPassed: t("cards.resetsPassed"),
      resetsPassedShort: t("cards.resetsPassedShort"),
      observedAt: (rel: string) => t("cards.observedAt", { rel }),
      staleChip: t("cards.staleChip"),
      otherSources: (n: number) => t("cards.otherSources", { n }),
      info: t("cards.info"),
      /** ⓘ 툴팁으로 접힌 줄들 */
      hidden: {
        noLimit: t("cards.hidden.noLimit"),
        resetsUnknown: t("cards.hidden.resetsUnknown"),
        statusOnly: t("cards.hidden.statusOnly"),
        ruleFallback: t("cards.hidden.ruleFallback"),
      },
      ariaLabel: (name: string, value: string, resets: string) => t("cards.ariaLabel", { name, value, resets }),
      gaugeLabel: (name: string) => t("cards.gaugeLabel", { name }),
      sourceLine: (title: string) => title,
    },
    /** 공식이 아닌 등급 묶음 카드 */
    group: {
      title: {
        observed: t("group.title.observed"),
        estimated: t("group.title.estimated"),
        unofficial: t("group.title.unofficial"),
      } as Record<string, string>,
      titleFallback: (trust: string) => t("group.titleFallback", { trust }),
      basisPrimary: t("group.basisPrimary"),
      basisReference: t("group.basisReference"),
      noValueRow: t("group.noValueRow"),
    },
    /** 격자 아래 기준 문구 */
    basis: {
      recentOfficial: t("basis.recentOfficial"),
      configured: t("basis.configured"),
      recent: t("basis.recent"),
    },
    compactTokens: (n: string) => t("compactTokens", { n }),
    nestedNote: t("nestedNote"),
    rollup: {
      title: t("rollup.title"),
      /** 현재 프로젝트가 있을 때(R15.3): 합계는 이 프로젝트 것만, 5시간·주간 창은 계정 전체 */
      titleProject: t("rollup.titleProject"),
      scopeProject: t("rollup.scopeProject"),
      period: t("rollup.period"),
      periods: {
        "today": t("rollup.periods.today"),
        "7d": t("rollup.periods.7d"),
        "30d": t("rollup.periods.30d"),
      } as Record<string, string>,
      view: t("rollup.view"),
      views: {
        agent_id: t("rollup.views.agent_id"),
        graph_id: t("rollup.views.graph_id"),
        model: t("rollup.views.model"),
        day: t("rollup.views.day"),
      } as Record<string, string>,
      unnamed: t("rollup.unnamed"),
      empty: t("rollup.empty"),
      input: t("rollup.input"),
      output: t("rollup.output"),
      noSplit: t("rollup.noSplit"),
      totalOnly: t("rollup.totalOnly"),
      totalOnlyTitle: t("rollup.totalOnlyTitle"),
      costSession: t("rollup.costSession"),
      cost: (usd: string) => t("rollup.cost", { usd }),
      asTable: t("rollup.asTable"),
      asBars: t("rollup.asBars"),
      tableLabel: t("rollup.tableLabel"),
      note: t("rollup.note"),
      columns: {
        name: t("rollup.columns.name"),
        total: t("rollup.columns.total"),
        input: t("rollup.columns.input"),
        output: t("rollup.columns.output"),
        cost: t("rollup.columns.cost"),
        note: t("rollup.columns.note"),
      },
      inOut: (i: string, o: string) => t("rollup.inOut", { i, o }),
      barsLabel: t("rollup.barsLabel"),
    },
    sources: {
      title: t("sources.title"),
      empty: t("sources.empty"),
      enableInSettings: t("sources.enableInSettings"),
      changeInSettings: t("sources.changeInSettings"),
      enabled: t("sources.enabled"),
      disabled: t("sources.disabled"),
      noValue: t("sources.noValue"),
      ok: t("sources.ok"),
      lastSeen: (rel: string) => t("sources.lastSeen", { rel }),
      neverSeen: t("sources.neverSeen"),
      errorLine: (msg: string) => t("sources.errorLine", { msg }),
      setup: t("sources.setup"),
      setupNote: t("sources.setupNote"),
      docs: t("sources.docs"),
      copy: t("sources.copy"),
      loadFailed: t("sources.loadFailed"),
      summary: (total: number, enabled: number) => t("sources.summary", { total, enabled }),
      devOnly: (n: number) => t("sources.devOnly", { n }),
      setupInGuide: t("sources.setupInGuide"),
    },
    setup: {
      region: t("setup.region"),
      summaryEmpty: t("setup.summaryEmpty"),
      summaryMissing: t("setup.summaryMissing"),
      summaryConnected: (when: string) => t("setup.summaryConnected", { when }),
      toggle: t("setup.toggle"),
      tabsLabel: t("setup.tabsLabel"),
      shell: t("setup.shell"),
      copy: t("setup.copy"),
      copied: t("setup.copied"),
      copyFailed: t("setup.copyFailed"),
      codeLabel: (title: string) => t("setup.codeLabel", { title }),
      lastReceived: (when: string) => t("setup.lastReceived", { when }),
      neverReceived: t("setup.neverReceived"),
      recheck: t("setup.recheck"),
      rechecking: t("setup.rechecking"),
    },
    common: {
      none: t("common.none"),
      unknown: t("common.unknown"),
    },
  };
}
export type UsageMessages = ReturnType<typeof createUsageMessages>;

/** 현재 언어의 `usage` 문구(렌더 때 만든다). */
export function useUsageMessages(): UsageMessages {
  return useMessageTable("usage", createUsageMessages);
}

/** 사용량 표시기(사이드바 등) 문구. 창 이름·출처 id는 여기에 없다. */
export function createUsageIndicatorMessages(t: Translate) {
  return {
    region: t("region"),
    noData: t("noData"),
    noDataHint: t("noDataHint"),
    toSources: t("toSources"),
    loading: t("loading"),
    loadFailed: t("loadFailed"),
    lastSuccess: (rel: string) => t("lastSuccess", { rel }),
    notObserved: t("notObserved"),
    remainingText: (n: number) => t("remainingText", { n }),
    usedText: (n: number) => t("usedText", { n }),
    spokenRemaining: (n: number) => t("spokenRemaining", { n }),
    spokenUsed: (n: number) => t("spokenUsed", { n }),
    overLimit: (used: number) => t("overLimit", { used }),
    both: (used: number, remaining: number) => t("both", { used, remaining }),
    resets: (rel: string) => t("resets", { rel }),
    resetsOnDate: (date: string) => t("resetsOnDate", { date }),
    resetsPassed: t("resetsPassed"),
    /** 사이드바 초기화 줄: 오늘은 시각만, 다른 날은 요일(또는 날짜)을 앞에 붙인다 */
    resetsClockToday: (time: string) => t("resetsClockToday", { time }),
    resetsClockOther: (day: string, time: string) => t("resetsClockOther", { day, time }),
    oldValue: t("oldValue"),
    stale: t("stale"),
    /** 값이 없는 창의 툴팁·낭독: 사유는 출처가 준 사실 */
    noRatioTitle: (name: string, reason: string) => t("noRatioTitle", { name, reason }),
    approxNote: t("approxNote"),
    unlinked: t("unlinked"),
    unlinkedHint: t("unlinkedHint"),
    openLabel: t("openLabel"),
    summary: (items: string) => t("summary", { items }),
    itemRatio: (name: string, valueText: string, resets: string) => (resets === "" ? t("itemRatio", { name, valueText }) : t("itemRatioResets", { name, valueText, resets })),
    itemOther: (name: string, text: string) => t("itemOther", { name, text }),
    ruleApplied: (at: number, tone: string) => t("ruleApplied", { tone, at }),
    rulePassed: (name: string, at: number) => t("rulePassed", { name, at }),
    peekLive: (summary: string) => summary,
    popoverTitle: t("popoverTitle"),
    updated: (rel: string) => t("updated", { rel }),
    moreWindows: (n: number) => t("moreWindows", { n }),
    sourceErrors: (n: number) => t("sourceErrors", { n }),
    otherSources: (n: number) => t("otherSources", { n }),
    clickToOpen: t("clickToOpen"),
    statusOnlyDetail: t("statusOnlyDetail"),
    tokensDetail: t("tokensDetail"),
    tones: {
      info: t("tones.info"),
      success: t("tones.success"),
      warning: t("tones.warning"),
      danger: t("tones.danger"),
    } as Record<string, string>,
    example: t("example"),
    /** 칩에서 넘친 항목 수 */
    chipMore: (n: number) => t("chipMore", { n }),
    /** 우클릭·Shift+F10 메뉴 */
    menu: {
      label: t("menu.label"),
      open: t("menu.open"),
      refresh: t("menu.refresh"),
      settings: t("menu.settings"),
      hide: t("menu.hide"),
      refreshing: t("menu.refreshing"),
      refreshTooSoon: t("menu.refreshTooSoon"),
      hidden: t("menu.hidden"),
      hideFailed: t("menu.hideFailed"),
    },
    /** 설정 화면 */
    settings: {
      group: t("settings.group"),
      pollNotice: t("settings.pollNotice"),
      enabledOffNote: t("settings.enabledOffNote"),
      placementHelp: t("settings.placementHelp"),
      placements: {
        "sidebar-bottom": t("settings.placements.sidebar-bottom"),
        "sidebar-top": t("settings.placements.sidebar-top"),
        "float-bottom-right": t("settings.placements.float-bottom-right"),
        "float-bottom-left": t("settings.placements.float-bottom-left"),
        "float-top-right": t("settings.placements.float-top-right"),
      } as Record<string, string>,
      placementUnknown: (id: string) => t("settings.placementUnknown", { id }),
      windowsEmpty: t("settings.windowsEmpty"),
      windowRemove: (name: string) => t("settings.windowRemove", { name }),
      windowAdd: t("settings.windowAdd"),
      windowAddPlaceholder: t("settings.windowAddPlaceholder"),
      windowAddFree: t("settings.windowAddFree"),
      windowMissing: t("settings.windowMissing"),
      fields: {
        label: t("settings.fields.label"),
        value: t("settings.fields.value"),
        gauge: t("settings.fields.gauge"),
        reset: t("settings.fields.reset"),
        trust: t("settings.fields.trust"),
        observed: t("settings.fields.observed"),
      } as Record<string, string>,
      fieldUnknown: (id: string) => t("settings.fieldUnknown", { id }),
      fieldUp: (name: string) => t("settings.fieldUp", { name }),
      fieldDown: (name: string) => t("settings.fieldDown", { name }),
      modes: {
        remaining: t("settings.modes.remaining"),
        used: t("settings.modes.used"),
      } as Record<string, string>,
      ruleAt: t("settings.ruleAt"),
      ruleTone: t("settings.ruleTone"),
      ruleRemove: t("settings.ruleRemove"),
      ruleAdd: t("settings.ruleAdd"),
      ruleNote: t("settings.ruleNote"),
      ruleDuplicate: t("settings.ruleDuplicate"),
      ruleToneUnknown: (id: string) => t("settings.ruleToneUnknown", { id }),
      preview: t("settings.preview"),
      previewExpanded: t("settings.previewExpanded"),
      previewRail: t("settings.previewRail"),
      sampleNames: [t("settings.sampleName1"), t("settings.sampleName2")] as readonly string[],
    },
  };
}
export type UsageIndicatorMessages = ReturnType<typeof createUsageIndicatorMessages>;

/** 현재 언어의 `usageIndicator` 문구(렌더 때 만든다). */
export function useUsageIndicatorMessages(): UsageIndicatorMessages {
  return useMessageTable("usageIndicator", createUsageIndicatorMessages);
}
