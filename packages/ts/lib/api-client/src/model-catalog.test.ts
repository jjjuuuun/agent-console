import { describe, expect, it } from "vitest";
import { ApiError, createRestClient, type FetchLike } from "./index";

// 백엔드·모델 id는 전부 임의 값이다.
function server(routes: Record<string, { status?: number; body?: unknown }>) {
  const urls: string[] = [];
  const fn: FetchLike = (url) => {
    urls.push(url);
    const path = url.replace("http://h/api/v1", "");
    const r = routes[path] ?? { status: 404, body: { error: { code: "not_found", message: "nope" } } };
    return Promise.resolve(new Response(JSON.stringify(r.body ?? {}), { status: r.status ?? 200 }));
  };
  return { urls, rest: createRestClient({ baseUrl: "http://h", fetch: fn }) };
}

const catalog = { backend_id: "b 1", models: [{ id: "m-1", sources: ["discovered"] }], discovery: { state: "ok", fetched_at: 5 } };

describe("getBackendModelCatalog", () => {
  it("model-catalog 경로를 부르고 refresh는 ?refresh=true로 보낸다", async () => {
    const { rest, urls } = server({ "/backends/b%201/model-catalog": { body: catalog }, "/backends/b%201/model-catalog?refresh=true": { body: catalog } });
    expect(await rest.getBackendModelCatalog("b 1")).toEqual(catalog);
    await rest.getBackendModelCatalog("b 1", { refresh: true });
    expect(urls.map((u) => u.replace("http://h/api/v1", ""))).toEqual(["/backends/b%201/model-catalog", "/backends/b%201/model-catalog?refresh=true"]);
  });

  it("실패 상태도 200 본문 그대로 돌려준다", async () => {
    const failed = { backend_id: "b", models: [], discovery: { state: "failed", issues: [{ code: "x", message: "m", severity: "warning" }] } };
    const { rest } = server({ "/backends/b/model-catalog": { body: failed } });
    expect((await rest.getBackendModelCatalog("b")).discovery?.state).toBe("failed");
  });

  it("경로가 404(옛 서버)면 /models로 대체하고 discovery는 null", async () => {
    const { rest, urls } = server({ "/backends/b/models": { body: [{ id: "m-9" }] } });
    expect(await rest.getBackendModelCatalog("b", { refresh: true })).toEqual({ backend_id: "b", models: [{ id: "m-9" }], discovery: null });
    expect(urls).toHaveLength(2);
  });

  it("두 경로 모두 404면 ApiError, 404가 아닌 오류는 대체하지 않는다", async () => {
    const none = server({});
    expect(await none.rest.getBackendModelCatalog("b").catch((e: unknown) => e)).toBeInstanceOf(ApiError);
    const boom = server({ "/backends/b/model-catalog": { status: 500, body: { error: { code: "internal", message: "x" } } } });
    const e = (await boom.rest.getBackendModelCatalog("b").catch((x: unknown) => x)) as ApiError;
    expect(e.status).toBe(500);
    expect(boom.urls).toHaveLength(1);
  });
});
