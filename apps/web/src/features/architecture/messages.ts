import type { Translate } from "@agent-console/i18n";
import { useMessageTable } from "../../i18n";

/** 구조도 화면의 앱 층 문구(`screen-architecture.md` §12). 칸 이름·연결 라벨·설명·프로필 제목은 서버 데이터라 여기 없다. 그림 안쪽 문구는 `@agent-console/arch-view`가 가진다. */
export function createArchMessages(t: Translate) {
  return {
    segment: t("segment"),
    region: t("region"),
    profile: t("profile"),
    breadcrumb: {
      label: t("breadcrumb.label"),
      root: t("breadcrumb.root"),
      up: t("breadcrumb.up"),
      folded: t("breadcrumb.folded"),
    },
    status: {
      events: (n: number) => t("status.events", { n }),
      wholeRange: t("status.wholeRange"),
      unassigned: (n: number) => t("status.unassigned", { n }),
      unassignedView: t("status.unassignedView"),
      unavailable: (n: number) => t("status.unavailable", { n }),
      live: t("status.live"),
      liveUpdated: (time: string) => t("status.liveUpdated", { time }),
      reflected: (n: number) => t("status.reflected", { n }),
      laneBasis: (name: string) => t("status.laneBasis", { name }),
      loading: t("status.loading"),
      refreshing: t("status.refreshing"),
      unavailableOpen: t("status.unavailableOpen"),
      unavailableClose: t("status.unavailableClose"),
      unavailableItem: (item: string, reason: string) => (reason === "" ? item : t("status.unavailableItem", { item, reason })),
    },
    chip: {
      cell: (name: string) => t("chip.cell", { name }),
      edge: (label: string) => t("chip.edge", { label }),
      group: (cell: string, group: string) => t("chip.group", { cell, group }),
      unassigned: t("chip.unassigned"),
      clear: t("chip.clear"),
      drillClear: (label: string) => t("chip.drillClear", { label }),
    },
    noName: t("noName"),
    unassigned: t("unassigned"),
    toast: {
      notCollected: t("toast.notCollected"),
      structural: t("toast.structural"),
      pickGroup: t("toast.pickGroup"),
      rejected: (message: string) => message,
    },
    table: {
      only: (name: string, n: number) => t("table.only", { name, n }),
      partial: (name: string, n: number, k: number) => t("table.partial", { name, n, k }),
      loading: (name: string) => t("table.loading", { name }),
      zero: (name: string) => t("table.zero", { name }),
    },
    /** 서버 안내(`view.notes`)는 서버가 만든 문구를 그대로 쓰고, 설정으로 가는 단추만 앱이 단다. */
    banner: {
      openSettings: t("banner.openSettings"),
    },
    empty: {
      rules: {
        title: t("empty.rules.title"),
        body: t("empty.rules.body"),
        action: t("empty.rules.action"),
      },
      noEvents: {
        title: t("empty.noEvents.title"),
        body: t("empty.noEvents.body"),
        action: t("empty.noEvents.action"),
      },
      noSource: {
        title: t("empty.noSource.title"),
        body: (kinds: string) => (kinds === "" ? t("empty.noSource.bodyNoKinds") : t("empty.noSource.body", { kinds })),
        action: t("empty.noSource.action"),
      },
      tooBig: {
        title: t("empty.tooBig.title"),
        body: (n: number | undefined, max: number | undefined) =>
          n !== undefined && max !== undefined ? t("empty.tooBig.body", { n, max }) : t("empty.tooBig.bodyGeneric"),
        action: t("empty.tooBig.action"),
      },
      error: {
        title: t("empty.error.title"),
        action: t("empty.error.action"),
      },
      profileError: {
        title: t("empty.profileError.title"),
        action: t("empty.profileError.action"),
      },
    },
    runTab: {
      explain: t("runTab.explain"),
      includeChildren: t("runTab.includeChildren"),
      on: t("runTab.on"),
      off: t("runTab.off"),
      rootLabel: t("runTab.rootLabel"),
      scopeRun: t("runTab.scopeRun"),
      scopeTree: t("runTab.scopeTree"),
      splitLabel: t("runTab.splitLabel"),
    },
    dialog: {
      title: (profile: string, scope: string) => t("dialog.title", { profile, scope }),
      close: t("dialog.close"),
      expand: t("dialog.expand"),
    },
    /** 구조도 분리 창(새 창으로 분리, 다시 합치기) */
    popout: {
      open: t("popout.open"),
      openHelp: t("popout.openHelp"),
      focus: t("popout.focus"),
      redock: t("popout.redock"),
      detachedTitle: t("popout.detachedTitle"),
      detachedBody: t("popout.detachedBody"),
      pendingTitle: t("popout.pendingTitle"),
      pendingBody: t("popout.pendingBody"),
      dock: t("popout.dock"),
      blocked: t("popout.blocked"),
      unsupported: t("popout.unsupported"),
      windowTitle: (label: string) => t("popout.windowTitle", { label }),
      standalone: t("popout.standalone"),
      needArch: t("popout.needArch"),
      needKey: t("popout.needKey"),
      closeWindow: t("popout.closeWindow"),
    },
    aria: {
      live: t("aria.live"),
    },
  };
}
export type ArchMessages = ReturnType<typeof createArchMessages>;

/** 현재 언어의 `architecture` 문구(렌더 때 만든다). */
export function useArchMessages(): ArchMessages {
  return useMessageTable("architecture", createArchMessages);
}
