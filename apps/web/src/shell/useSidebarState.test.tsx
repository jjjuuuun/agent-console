import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createSafeStorage } from "../app/storage";
import { SIDEBAR_COLLAPSED_KEY, SIDEBAR_NARROW_QUERY, useSidebarState } from "./useSidebarState";

function mockWidth(narrow: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: query === SIDEBAR_NARROW_QUERY ? narrow : false, addEventListener: () => {}, removeEventListener: () => {} }));
}
const store = (initial: Record<string, string> = {}) => {
  const data = new Map(Object.entries(initial));
  return createSafeStorage({ getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v), removeItem: (k: string) => void data.delete(k) } as unknown as Storage);
};

afterEach(() => vi.unstubAllGlobals());

// 접기 초기 상태 규칙(ux-overhaul §2.2): 저장값 -> 없으면 폭 < 1280이면 접힘, 아니면 펼침. 페이지별 규칙은 없다(이 훅은 경로를 모른다).
describe("사이드바 초기 상태 규칙", () => {
  it("저장값이 없으면 넓은 화면은 펼침, 좁은 화면은 접힘(펼치면 드로어)", () => {
    mockWidth(false);
    expect(renderHook(() => useSidebarState(store())).result.current).toMatchObject({ collapsed: false, drawer: false });
    mockWidth(true);
    const narrow = renderHook(() => useSidebarState(store()));
    expect(narrow.result.current).toMatchObject({ collapsed: true, drawer: false });
    act(() => narrow.result.current.setCollapsed(false));
    expect(narrow.result.current).toMatchObject({ collapsed: false, drawer: true });
  });
  it("저장값이 폭보다 우선한다", () => {
    mockWidth(true);
    expect(renderHook(() => useSidebarState(store({ [SIDEBAR_COLLAPSED_KEY]: "0" }))).result.current.collapsed).toBe(false);
    mockWidth(false);
    expect(renderHook(() => useSidebarState(store({ [SIDEBAR_COLLAPSED_KEY]: "1" }))).result.current.collapsed).toBe(true);
  });
  it("접기·펴기는 저장되어 다음 시작에도 같다", () => {
    mockWidth(false);
    const storage = store();
    const first = renderHook(() => useSidebarState(storage));
    act(() => first.result.current.toggle());
    expect(first.result.current.collapsed).toBe(true);
    expect(renderHook(() => useSidebarState(storage)).result.current.collapsed).toBe(true);
  });
  it("기준 폭은 1280px 미만이다", () => {
    expect(SIDEBAR_NARROW_QUERY).toBe("(max-width: 1279px)");
  });
});
