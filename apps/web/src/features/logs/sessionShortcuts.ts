import { useShortcuts, type ShortcutDef } from "@agent-console/ui";
import { LOGS_SCOPES } from "./logsConfig";

/** 세션 상세 단축키가 부르는 동작(화면이 채운다). 이름만 있고 동작은 호출자 몫이다. */
export interface SessionShortcutActions {
  refresh(): void;
  scan(): void;
  playToggle(): void;
  stepBack(): void;
  stepForward(): void;
  slower(): void;
  faster(): void;
  errorsOnly(): void;
  toggleFlow(): void;
  /** 흐름 패널의 [레인 | 위임 흐름] 전환 */
  flowView(): void;
  /** 이벤트 ↔ 구조도 뷰 전환 */
  toggleView(): void;
  sessionInfo(): void;
  viewMenu(): void;
  toggleDetail(): void;
  focusSearch(): void;
  focusChips(): void;
}

/**
 * 세션 상세 단축키 표. 단축키 배열을 한 곳에서 만들어 키 중복 검사(`sessionShortcuts.test.ts`)가 같은 배열을 본다.
 * 공통 범위(`logs`)의 `r`·`Shift+R`은 목록·검색과 같은 키이고, 새 키(5.7R.32)는 `a` `i` `o`와 `Shift+R`(세션 상세에 더함)다.
 */
export function buildSessionShortcuts(a: SessionShortcutActions): ShortcutDef[] {
  const s = LOGS_SCOPES.session;
  const c = LOGS_SCOPES.common;
  return [
    { id: "logs.refresh", scope: c, keys: "r", titleKey: "shortcuts.logsRefresh", run: a.refresh },
    { id: "logs.scan", scope: c, keys: "Shift+R", titleKey: "shortcuts.logsScan", run: a.scan },
    { id: "logs.s.play", scope: s, keys: "k", titleKey: "shortcuts.logsPlayToggle", run: a.playToggle },
    { id: "logs.s.prev", scope: s, keys: ",", titleKey: "shortcuts.logsStepBack", run: a.stepBack },
    { id: "logs.s.next", scope: s, keys: ".", titleKey: "shortcuts.logsStepForward", run: a.stepForward },
    { id: "logs.s.slower", scope: s, keys: "[", titleKey: "shortcuts.logsSpeedDown", run: a.slower },
    { id: "logs.s.faster", scope: s, keys: "]", titleKey: "shortcuts.logsSpeedUp", run: a.faster },
    { id: "logs.s.errors", scope: s, keys: "e", titleKey: "shortcuts.logsErrorsOnly", run: a.errorsOnly },
    { id: "logs.s.flow", scope: s, keys: "t", titleKey: "shortcuts.logsToggleFlow", run: a.toggleFlow },
    { id: "logs.s.view", scope: s, keys: "v", titleKey: "shortcuts.logsFlowView", run: a.flowView },
    { id: "logs.s.arch", scope: s, keys: "a", titleKey: "shortcuts.logsToggleView", run: a.toggleView },
    { id: "logs.s.info", scope: s, keys: "i", titleKey: "shortcuts.logsSessionInfo", run: a.sessionInfo },
    { id: "logs.s.viewmenu", scope: s, keys: "o", titleKey: "shortcuts.logsViewMenu", run: a.viewMenu },
    { id: "logs.s.detail", scope: s, keys: "d", titleKey: "shortcuts.logsToggleDetail", run: a.toggleDetail },
    { id: "logs.s.search", scope: s, keys: "/", titleKey: "shortcuts.logsFocusSearch", run: a.focusSearch },
    { id: "logs.s.chips", scope: s, keys: "f", titleKey: "shortcuts.logsCategoryFocus", run: a.focusChips },
  ];
}

/** 세션 상세 단축키 등록(훅). 표는 `buildSessionShortcuts`가 한 곳에서 만든다. */
export function useSessionShortcuts(actions: SessionShortcutActions): void {
  useShortcuts(buildSessionShortcuts(actions));
}
