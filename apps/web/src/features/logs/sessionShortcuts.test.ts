import { describe, expect, it } from "vitest";
import { isPlainCharCombo } from "@agent-console/ui";
import { buildSessionShortcuts, type SessionShortcutActions } from "./sessionShortcuts";

const noop = () => undefined;
const actions: SessionShortcutActions = {
  refresh: noop, scan: noop, playToggle: noop, stepBack: noop, stepForward: noop, slower: noop, faster: noop, errorsOnly: noop, toggleFlow: noop,
  flowView: noop, toggleView: noop, sessionInfo: noop, viewMenu: noop, toggleDetail: noop, focusSearch: noop, focusChips: noop,
};

describe("세션 상세 단축키 배열(5.7R.32 AC-7)", () => {
  const defs = buildSessionShortcuts(actions);
  it("같은 키가 두 번 나오지 않고 id도 겹치지 않는다(공통 범위와 세션 범위를 함께 본다)", () => {
    const keys = defs.map((d) => d.keys.toLowerCase());
    expect(new Set(keys).size).toBe(keys.length);
    expect(new Set(defs.map((d) => d.id)).size).toBe(defs.length);
  });
  it("새 키 A·I·O·Shift+R이 있고 기존 키가 그대로 남아 있다", () => {
    const byKey = new Map(defs.map((d) => [d.keys, d.id]));
    for (const k of ["a", "i", "o", "Shift+R", "r", "k", ",", ".", "[", "]", "e", "t", "v", "d", "/", "f"]) expect(byKey.has(k), k).toBe(true);
  });
  it("A·I·O는 글자 하나 키라 입력창 안에서는 동작하지 않는다(레지스트리가 plain 키로 취급)", () => {
    for (const d of defs.filter((x) => ["a", "i", "o"].includes(x.keys))) expect(isPlainCharCombo(d.keys)).toBe(true);
  });
});
