import { describe, expect, it, vi } from "vitest";
import { waitForOk } from "./ready.mjs";

describe("waitForOk", () => {
  it("연결 거부·503 뒤 200이 되면 true를 돌려주고 그동안 onWait을 부른다", async () => {
    const fetchFn = vi
      .fn()
      .mockRejectedValueOnce(new Error("ECONNREFUSED"))
      .mockResolvedValueOnce({ ok: false, status: 503 })
      .mockResolvedValue({ ok: true, status: 200 });
    const onWait = vi.fn();
    expect(await waitForOk("http://x/health", { fetchFn, sleep: async () => {}, onWait })).toBe(true);
    expect(onWait).toHaveBeenCalledTimes(2);
  });
  it("stop이 참이면 false", async () => {
    const fetchFn = vi.fn().mockRejectedValue(new Error("x"));
    let n = 0;
    expect(await waitForOk("http://x", { fetchFn, sleep: async () => {}, stop: () => n++ > 2 })).toBe(false);
  });
});
