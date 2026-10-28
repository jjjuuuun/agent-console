import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { StorageProvider } from "../../app/StorageContext";
import { createSafeStorage } from "../../app/storage";
import { LOGS_STORAGE } from "./logsConfig";
import { readTimeMode, useLogTimeMode } from "./useLogTimeMode";

const memory = () => {
  const m = new Map<string, string>();
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k), key: () => null, clear: () => m.clear(), length: 0 } as unknown as Storage;
};

describe("useLogTimeMode", () => {
  it("기본은 날짜·시각이고, 옛 저장값(absolute·relative)을 새 방식으로 옮긴다", () => {
    const s = createSafeStorage(memory());
    expect(readTimeMode(s)).toBe("datetime");
    s.set(LOGS_STORAGE.timeMode, "absolute");
    expect(readTimeMode(s)).toBe("time");
    s.set(LOGS_STORAGE.timeMode, "relative");
    expect(readTimeMode(s)).toBe("elapsed");
    s.set(LOGS_STORAGE.timeMode, "???");
    expect(readTimeMode(s)).toBe("datetime");
  });
  it("한 곳에서 바꾸면 같은 저장소를 쓰는 다른 표도 따라오고 열 폭이 바뀐다", () => {
    const storage = createSafeStorage(memory());
    const wrapper = ({ children }: { children: ReactNode }) => <StorageProvider storage={storage}>{children}</StorageProvider>;
    const a = renderHook(() => useLogTimeMode(), { wrapper });
    const b = renderHook(() => useLogTimeMode(), { wrapper });
    const wide = a.result.current.widths["time"]!;
    act(() => a.result.current.setMode("elapsed"));
    expect(b.result.current.mode).toBe("elapsed");
    expect(b.result.current.widths["time"]!).toBeLessThan(wide);
    expect(storage.get(LOGS_STORAGE.timeMode)).toBe("elapsed");
  });
});
