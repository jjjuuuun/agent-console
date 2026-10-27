import { describe, expect, it } from "vitest";
import { createLoginClient } from "./clients/login";
import type { RestIo } from "./io";

function fakeIo(result: unknown = undefined) {
  const calls: { method: string; path: string; body?: unknown }[] = [];
  const io = {
    request: async (method: string, path: string, opts?: { body?: unknown }) => {
      calls.push({ method, path, ...(opts?.body === undefined ? {} : { body: opts.body }) });
      return result;
    },
  } as unknown as RestIo;
  return { io, calls };
}

describe("LoginClient", () => {
  it("시작은 POST /backends/{id}/login, 본문 생략 시 빈 객체, id는 인코딩", async () => {
    const { io, calls } = fakeIo({ session_id: "s1" });
    await createLoginClient(io).startBackendLogin("a/b");
    await createLoginClient(io).startBackendLogin("x", { method_id: "m" });
    expect(calls[0]).toEqual({ method: "POST", path: "/backends/a%2Fb/login", body: {} });
    expect(calls[1]?.body).toEqual({ method_id: "m" });
  });

  it("current는 204(undefined)면 null", async () => {
    expect(await createLoginClient(fakeIo(undefined).io).getCurrentBackendLogin()).toBeNull();
    expect(await createLoginClient(fakeIo({ session_id: "s" }).io).getCurrentBackendLogin()).toEqual({ session_id: "s" });
  });

  it("조회·입력·취소·로그아웃 경로", async () => {
    const { io, calls } = fakeIo({});
    const c = createLoginClient(io);
    await c.getBackendLogin("s 1");
    await c.sendBackendLoginInput("s1", { text: "abc" });
    await c.sendBackendLoginInput("s1", { key: "enter" });
    await c.cancelBackendLogin("s1");
    await c.logoutBackend("be");
    expect(calls.map((x) => `${x.method} ${x.path}`)).toEqual([
      "GET /backends/login/s%201",
      "POST /backends/login/s1/input",
      "POST /backends/login/s1/input",
      "DELETE /backends/login/s1",
      "POST /backends/be/logout",
    ]);
    expect(calls[1]?.body).toEqual({ text: "abc" });
  });
});
