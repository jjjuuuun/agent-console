import { describe, expect, it, vi } from "vitest";
import { createApiClients, type FeatureSignal } from "./apiClients";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

function setup(response: () => Response) {
  const signals: FeatureSignal[] = [];
  const fetch = vi.fn(async () => response());
  const clients = createApiClients({ baseUrl: "http://x", fetch, onFeatureSignal: (s) => signals.push(s) });
  return { clients, signals, fetch };
}

describe("기능 REST 신호(404 / 409 feature_unavailable)", () => {
  it("409 feature_unavailable이면 module·port를 담은 unavailable 신호를 내고, 응답 본문은 호출자가 그대로 읽는다", async () => {
    const env = { error: { code: "feature_unavailable", message: "m", details: { module: "mod-x", port: "UsagePort" } } };
    const { clients, signals } = setup(() => json(409, env));
    await expect(clients.rest.listModules()).rejects.toBeDefined();
    expect(signals).toEqual([{ kind: "unavailable", module: "mod-x", port: "UsagePort" }]);
  });

  it("다른 409(예: 충돌)는 신호가 없다", async () => {
    const { clients, signals } = setup(() => json(409, { error: { code: "conflict", message: "m" } }));
    await expect(clients.rest.listModules()).rejects.toBeDefined();
    expect(signals).toEqual([]);
  });

  it("/modules 자체의 404는 신호가 없다(옛 서버 fail-open은 따로 처리)", async () => {
    const { clients, signals } = setup(() => json(404, { error: { code: "not_found", message: "m" } }));
    await clients.rest.listModules().catch(() => undefined);
    expect(signals).toEqual([]);
  });
});
